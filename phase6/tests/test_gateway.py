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
    
    # Configure client override for offline/mock test execution
    def mock_override(model, prompt, timeout):
        if "interrupted" in prompt.lower() or "recovery" in prompt.lower():
            return "Pardon the interruption. Please continue."
        if "blocked" in prompt.lower():
            return "private_key = secret_value"
        return f"Mocked WAMMR response for prompt: {prompt}"
        
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
    bm = BudgetManager(global_limit=10000, memory_engine=memory_engine)
    bm.set_agent_limit("voice_gateway", 3000)
    bm.set_agent_limit("voice_delegation", 3000)
    return bm

@pytest.fixture
def wmg_gateway(credential_vault, memory_engine):
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    gateway.establish_connection("brandstream_publish_conn", "slack", 2000)
    return gateway

@pytest.fixture
def delegation_controller(wammr_router, budget_manager):
    return VoiceDelegationController(wammr_router, budget_manager)

def test_websocket_gateway_normal_turn(
    wammr_router, guardrail_checker, budget_manager, wmg_gateway, delegation_controller
):
    async def run_test():
        port = 8766
        server = VoiceGatewayServer(
            model_router=wammr_router,
            guardrail_checker=guardrail_checker,
            budget_manager=budget_manager,
            wmg_gateway=wmg_gateway,
            delegation_controller=delegation_controller,
            host="127.0.0.1",
            port=port,
            mock_mode=True
        )
        
        await server.start()
        
        try:
            uri = f"ws://127.0.0.1:{port}"
            async with websockets.connect(uri) as websocket:
                # Send normal turn
                payload = {
                    "type": "text_input",
                    "text": "Hello, BrandStream gateway"
                }
                await websocket.send(json.dumps(payload))
                
                # Wait for response
                raw_response = await websocket.recv()
                resp = json.loads(raw_response)
                
                # Assertions
                assert resp["type"] == "voice_response"
                assert "text" in resp
                assert "audio_manifest" in resp
                assert "latency_ms" in resp
                assert resp["latency_compliant"] is True
                assert resp["audio_manifest"]["transcript"] == resp["text"]
                assert resp["latency_ms"] < 100.0
                
        finally:
            await server.stop()

    asyncio.run(run_test())

def test_websocket_gateway_interruption_detection(
    wammr_router, guardrail_checker, budget_manager, wmg_gateway, delegation_controller
):
    async def run_test():
        port = 8767
        server = VoiceGatewayServer(
            model_router=wammr_router,
            guardrail_checker=guardrail_checker,
            budget_manager=budget_manager,
            wmg_gateway=wmg_gateway,
            delegation_controller=delegation_controller,
            host="127.0.0.1",
            port=port,
            mock_mode=True
        )
        
        await server.start()
        
        try:
            uri = f"ws://127.0.0.1:{port}"
            async with websockets.connect(uri) as websocket:
                # Send turn with a 4.0s reasoning delay to simulate heavy processing
                payload = {
                    "type": "text_input",
                    "text": "Complex query requiring reasoning",
                    "reasoning_delay": 4.0
                }
                await websocket.send(json.dumps(payload))
                
                # Give it a brief moment to start and enter outbound/processing state
                await asyncio.sleep(0.5)
                
                # While it is processing, user speaks / interrupts
                interruption_payload = {
                    "type": "audio_frame",
                    "transcript": "Wait, let me change that query"
                }
                await websocket.send(json.dumps(interruption_payload))
                
                # We expect to receive an interruption acknowledgement response first
                raw_ack = await websocket.recv()
                ack = json.loads(raw_ack)
                assert ack["type"] == "interruption_acknowledged"
                assert "User interruption detected" in ack["message"]
                
                # Then we expect the re-planned recovery response from the server
                raw_replan = await websocket.recv()
                replan = json.loads(raw_replan)
                assert replan["type"] == "replan_response"
                assert "Pardon the interruption" in replan["text"]
                
        finally:
            await server.stop()

    asyncio.run(run_test())
