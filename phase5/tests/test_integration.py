import os
import json
import pytest
import shutil
import tempfile
from typing import Dict, Any

# Phase 0, 1, 2 core imports
from core.memory.engine import MemoryEngine
from core.wammr.router import ModelRouter
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.vault import CredentialVault
from wmg.gateway import WebhookMessagingGateway

# Phase 5 pipeline imports
from media.pipeline import MediaSynthesisPipeline

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

def test_full_synthesis_pipeline_integration(memory_engine, credential_vault):
    # 1. Setup BudgetManager
    budget_manager = BudgetManager(global_limit=10000, memory_engine=memory_engine)
    budget_manager.set_agent_limit("synthesizer", 3000)

    # 2. Write dummy routing config for ModelRouter
    wammr_config = {
        "routing_matrix": {
            "validation": {
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

    # 3. Setup GuardrailChecker (dummy config)
    nemo_config_path = os.path.join(memory_engine.root_dir, "nemo_config.yaml")
    with open(nemo_config_path, "w") as f:
        f.write("rails:\n  - name: input_safety\n")
    guardrail_checker = GuardrailChecker(nemo_config_path)

    # 4. Setup WebhookMessagingGateway
    wmg_gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    wmg_gateway.establish_connection("brandstream_publish_conn", "slack", 2000)

    # 5. Initialize MediaSynthesisPipeline
    pipeline = MediaSynthesisPipeline(
        model_router=router,
        guardrail_checker=guardrail_checker,
        budget_manager=budget_manager,
        wmg_gateway=wmg_gateway,
        connection_id="brandstream_publish_conn",
        mock=True
    )

    # Phase 4 outputs (narration, storyboard, visual_blueprint)
    narration = "Welcome to BrandStream! Discover the power of automated video styling and compliance."
    storyboard = [
        {"frame": 1, "visual": "Intro animated title with logo display", "audio": "Welcome to BrandStream!"},
        {"frame": 2, "visual": "Split screen layout showing system graphs", "audio": "Discover the power of automated video styling and compliance."}
    ]
    visual_blueprint = {
        "layout": "split-screen",
        "aspect_ratio": "16:9",
        "coordinates": [0.1, 0.2, 0.9, 0.8],
        "weathering": "clean"
    }
    
    # Plausible skeleton pose coordinates mapping
    skeleton_pose = {
        "nose": [0.5, 0.15],
        "left_shoulder": [0.4, 0.3],
        "right_shoulder": [0.6, 0.3],
        "left_hip": [0.45, 0.6],
        "right_hip": [0.55, 0.6],
        "left_ankle": [0.45, 0.9],
        "right_ankle": [0.55, 0.9]
    }

    # Run Integration
    final_manifest = pipeline.run_pipeline(
        storyboard=storyboard,
        narration=narration,
        visual_blueprint=visual_blueprint,
        skeleton_pose_data=skeleton_pose,
        recipient_channel="operator_channel"
    )

    # Assertions
    assert "prompt_id" in final_manifest
    assert "media_files" in final_manifest
    assert len(final_manifest["media_files"]) == 2
    
    # Check Transcode values are recorded
    assert "final_video_url" in final_manifest
    assert final_manifest["final_video_url"].startswith("https://s3.amazonaws.com/")
    assert final_manifest["transcode_job_id"].startswith("job_")
    
    # Three.js transitions registered
    assert "threejs_render_task_id" in final_manifest
    assert final_manifest["threejs_render_task_id"].startswith("render_task_")

    # C2PA Provenance block verified
    assert "c2pa_provenance" in final_manifest
    c2pa = final_manifest["c2pa_provenance"]
    assert c2pa["signer"] == "BrandStream AI Content Signer"
    assert c2pa["c2pa_version"] == "1.3"
    assert "combined_asset_hash" in c2pa["assertions"]
    assert c2pa["assertions"]["rights"] == "Copyright (c) 2026 BrandStream AI. Opt-in UGC asserted."
    
    # Assert budget was recorded
    assert budget_manager.get_usage("synthesizer") > 0
