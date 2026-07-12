import os
import json
import pytest
import shutil
import tempfile
from typing import Dict, Any

# Phase 0 & Phase 1 & Phase 2 core imports
from core.memory.engine import MemoryEngine
from core.wammr.router import ModelRouter
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.vault import CredentialVault
from wmg.gateway import WebhookMessagingGateway

# Phase 4 brandstream imports
from brandstream.brandstream_core import BrandStreamAI

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

def test_full_pipeline_wiring(memory_engine, credential_vault):
    # 1. Initialize BudgetManager
    budget_manager = BudgetManager(global_limit=5000, memory_engine=memory_engine)
    budget_manager.set_agent_limit("reviewer", 1000)
    budget_manager.set_agent_limit("oracle", 2000)
    budget_manager.set_agent_limit("localization", 1000)

    # 2. Write dummy routing config for ModelRouter
    wammr_config = {
        "routing_matrix": {
            "validation": {
                "primary_model": "gpt-4o",
                "fallback_model": "claude-3-5-sonnet",
                "timeout_ms": 5000,
                "max_retries": 1
            },
            "code_generation": {
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
    
    # Configure mock LLM client responses
    def mock_llm_client(model: str, prompt: str, timeout: float) -> str:
        # Match prompt keywords to see what tool is requesting LLM service
        prompt_lower = prompt.lower()
        if "mlm semantic reviewer" in prompt_lower:
            return json.dumps({
                "cleaned_title": "Cleaned Acme Campaign",
                "pruned_tags": ["acme", "promo"],
                "quality_score": 0.9,
                "valid_spatial_bounds": True,
                "pruned": False
            })
        elif "promotional video script" in prompt_lower:
            return json.dumps({
                "narration": "Welcome to our campaign. We offer premium styling and absolute compliance.",
                "storyboard": [
                    {"frame": 1, "visual": "Intro splash screen", "audio": "Welcome to our campaign."},
                    {"frame": 2, "visual": "System dashboard graphics", "audio": "We offer premium styling and absolute compliance."}
                ],
                "style_reference": "layout: split-screen, aspect_ratio: 16:9, text_position: [0.1, 0.2, 0.8, 0.5], weathering: clean"
            })
        elif "factual deviations" in prompt_lower:
            return "DECISION: APPROVED\nREASON: ALLOWED"
        elif "translate the following promotional text" in prompt_lower:
            if "FR" in prompt:
                return "Bienvenue dans notre campagne."
            elif "ES" in prompt:
                return "Bienvenido a nuestra campaña."
            return f"Translated: {prompt}"
        return "Generic mock response"

    router.client_override = mock_llm_client

    # 3. Setup GuardrailChecker
    # Write a dummy nemo_config file so checker doesn't warn
    nemo_config_path = os.path.join(memory_engine.root_dir, "nemo_config.yaml")
    with open(nemo_config_path, "w") as f:
        f.write("rails:\n  - name: input_safety\n")
    guardrail_checker = GuardrailChecker(nemo_config_path)

    # 4. Setup WebhookMessagingGateway
    wmg_gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    wmg_gateway.establish_connection("brandstream_publish_conn", "slack", 1000)

    # 5. Initialize BrandStreamAI Coordinator
    bs_system = BrandStreamAI(
        memory_engine=memory_engine,
        model_router=router,
        budget_manager=budget_manager,
        guardrail_checker=guardrail_checker,
        wmg_gateway=wmg_gateway,
        connection_id="brandstream_publish_conn"
    )

    # Run full integrated process
    url = "https://acme-competitor-campaign.example.com"
    name = "acme"
    locales = ["FR", "ES"]
    
    result = bs_system.process_competitor_campaign(url, name, locales)
    
    # Assertions
    assert result["status"] == "success"
    assert result["campaign_name"] == "acme"
    assert "draft" in result
    assert result["draft"]["narration"] == "Welcome to our campaign. We offer premium styling and absolute compliance."
    
    # Check that spatial blueprint was extracted correctly via analyzer
    blueprint = result["draft"]["visual_blueprint"]
    assert blueprint["layout"] == "split-screen"
    assert blueprint["aspect_ratio"] == "16:9"
    assert blueprint["coordinates"] == [0.1, 0.2, 0.8, 0.5]
    
    # Check localized translations generated by router / fallback translation logic
    assert "FR" in result["localized"]
    assert "ES" in result["localized"]
    
    # Verify that results are saved in MemoryEngine
    saved_result_file = os.path.join(memory_engine.root_dir, f"campaigns/{name}_result.json")
    assert os.path.exists(saved_result_file)
    with open(saved_result_file, "r") as f:
        saved_data = json.load(f)
    assert saved_data["name"] == "acme"
    assert saved_data["original_narration"] == result["draft"]["narration"]

    # Verify token usage is registered on BudgetManager
    assert budget_manager.get_usage("reviewer") > 0
    assert budget_manager.get_usage("oracle") > 0
    assert budget_manager.get_usage("localization") > 0
