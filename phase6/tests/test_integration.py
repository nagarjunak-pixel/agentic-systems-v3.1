import os
import json
import pytest
import shutil
import tempfile
import asyncio
import websockets
from typing import Dict, Any

# Core imports
from core.memory.engine import MemoryEngine
from core.wammr.router import ModelRouter
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.vault import CredentialVault
from wmg.gateway import WebhookMessagingGateway

# Phase 4 and 5 imports
from brandstream.creative.oracle import CreativeDirector
from media.pipeline import MediaSynthesisPipeline

# Phase 6 imports
from voice.delegation.controller import VoiceDelegationController
from voice.gateway.websocket import VoiceGatewayServer

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

@pytest.fixture
def memory_engine(temp_dir):
    engine = MemoryEngine(temp_dir)
    yield engine
    engine.shutdown()

@pytest.fixture
def credential_vault():
    secrets = {
        "slack": {"token": "xoxb-slack-secret-token"},
        "teams": {"webhook_url": "https://outlook.office.com/webhook/teams-secret"},
        "whatsapp": {"token": "eaag-whatsapp-secret-token"}
    }
    vault = CredentialVault(secrets)
    return vault

@pytest.fixture
def wammr_router(memory_engine):
    wammr_config = {
        "routing_matrix": {
            "voice_realtime": {
                "primary_model": "gpt-4o",
                "fallback_model": "claude-3-5-sonnet",
                "timeout_ms": 5000,
                "max_retries": 1
            },
            "creative_generation": {
                "primary_model": "gpt-4o",
                "fallback_model": "claude-3-5-sonnet",
                "timeout_ms": 10000,
                "max_retries": 1
            }
        },
        "circuit_breakers": {
            "failure_threshold_pct": 50,
            "recovery_time_seconds": 30,
            "health_check_interval_seconds": 10
        }
    }
    config_path = os.path.join(memory_engine.root_dir, "routing_config.json")
    with open(config_path, "w") as f:
        json.dump(wammr_config, f)
        
    router = ModelRouter(config_path)
    
    # Simple offline client mock override
    def mock_override(model, prompt, timeout):
        if "re-plan" in prompt.lower() or "recovery" in prompt.lower():
            return "Pardon the interruption, let's re-plan."
        return "Standard mock routing response text."
        
    router.client_override = mock_override
    return router

@pytest.fixture
def guardrail_checker(memory_engine):
    nemo_config_path = os.path.join(memory_engine.root_dir, "nemo_config.yaml")
    with open(nemo_config_path, "w") as f:
        f.write("rails:\n  - name: input_safety\n")
    return GuardrailChecker(nemo_config_path)

@pytest.fixture
def budget_manager(memory_engine):
    bm = BudgetManager(global_limit=20000, memory_engine=memory_engine)
    bm.set_agent_limit("voice_gateway", 5000)
    bm.set_agent_limit("voice_delegation", 5000)
    bm.set_agent_limit("synthesizer", 5000)
    return bm

@pytest.fixture
def wmg_gateway(credential_vault, memory_engine):
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    gateway.establish_connection("brandstream_publish_conn", "slack", 5000)
    return gateway

def test_full_voice_media_integration_turn(
    memory_engine, wammr_router, guardrail_checker, budget_manager, wmg_gateway
):
    async def run_test():
        # 1. Setup Phase 4 Creative Director and generate a localized copywriting asset
        creative_director = CreativeDirector(wammr_router, budget_manager)
        original_copy = "Experience the speed of automated brand marketing with BrandStream AI!"
        locales = ["es-ES", "fr-FR"]
        
        # Translate and generate localized copy variants
        localized_copy_variants = creative_director.localization.translate_copy(original_copy, locales)
        assert "ES-ES" in localized_copy_variants
        assert "FR-FR" in localized_copy_variants
        
        # Save localized variants file under the memory-engine backed workspace
        campaign_file = "campaigns/promo_localized.json"
        memory_engine.write_file_sync(
            campaign_file,
            json.dumps({"original": original_copy, "localized": localized_copy_variants}, indent=2)
        )

        # 2. Setup Phase 5 MediaSynthesisPipeline
        media_pipeline = MediaSynthesisPipeline(
            model_router=wammr_router,
            guardrail_checker=guardrail_checker,
            budget_manager=budget_manager,
            wmg_gateway=wmg_gateway,
            connection_id="brandstream_publish_conn",
            mock=True
        )

        # 3. Setup Phase 6 Voice Delegation Controller
        delegation_controller = VoiceDelegationController(wammr_router, budget_manager)

        # 4. Setup Phase 6 Voice Gateway Server
        port = 8769
        server = VoiceGatewayServer(
            model_router=wammr_router,
            guardrail_checker=guardrail_checker,
            budget_manager=budget_manager,
            wmg_gateway=wmg_gateway,
            delegation_controller=delegation_controller,
            media_pipeline=media_pipeline,
            host="127.0.0.1",
            port=port,
            connection_id="brandstream_publish_conn",
            mock_mode=True
        )
        
        await server.start()

        try:
            uri = f"ws://127.0.0.1:{port}"
            async with websockets.connect(uri) as websocket:
                # Client triggers voice turn requesting video synthesis and references localized copy
                payload = {
                    "type": "text_input",
                    "text": "Please render the campaign video for es-ES locale.",
                    "media_requested": True
                }
                await websocket.send(json.dumps(payload))
                
                # Wait for turn response manifest
                raw_response = await websocket.recv()
                resp = json.loads(raw_response)
                
                # Assertions on Voice Turn response
                assert resp["type"] == "voice_response"
                assert "text" in resp
                assert "audio_manifest" in resp
                assert "latency_ms" in resp
                
                # Assert Phase 5 media_manifest is embedded correctly
                assert "media_manifest" in resp
                media = resp["media_manifest"]
                
                assert "final_video_url" in media
                assert media["final_video_url"].startswith("https://s3.amazonaws.com/")
                assert "transcode_job_id" in media
                assert "threejs_render_task_id" in media
                assert "c2pa_provenance" in media
                
                # Assert C2PA signature conforms to compliance specs
                c2pa = media["c2pa_provenance"]
                assert c2pa["signer"] == "BrandStream AI Content Signer"
                assert c2pa["assertions"]["rights"] == "Copyright (c) 2026 BrandStream AI. Opt-in UGC asserted."
                
                # Assert Token Budget has recorded the usage across components
                assert budget_manager.get_usage("voice_gateway") > 0
                assert budget_manager.get_usage("voice_delegation") > 0
                assert budget_manager.get_usage("synthesizer") > 0
                
        finally:
            await server.stop()

    asyncio.run(run_test())
