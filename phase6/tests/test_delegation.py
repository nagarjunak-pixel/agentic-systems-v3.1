import os
import json
import pytest
import shutil
import tempfile
import asyncio
from typing import Dict, Any, List

# Core imports
from core.memory.engine import MemoryEngine
from core.wammr.router import ModelRouter
from abtm.budget import BudgetManager

# Phase 6 imports
from voice.delegation.controller import VoiceDelegationController

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
    router.client_override = lambda model, prompt, timeout: f"Reasoning response for {prompt}"
    return router

@pytest.fixture
def budget_manager(memory_engine):
    bm = BudgetManager(global_limit=10000, memory_engine=memory_engine)
    bm.set_agent_limit("voice_delegation", 3000)
    return bm

@pytest.fixture
def delegation_controller(wammr_router, budget_manager):
    return VoiceDelegationController(wammr_router, budget_manager)

def test_delegation_progress_tokens(delegation_controller):
    async def run_test():
        progress_messages: List[Dict[str, Any]] = []
        
        async def mock_send_callback(message: Dict[str, Any]):
            progress_messages.append(message)

        # Trigger reasoning with a 4.5 seconds delay (which is > 3.0s limit)
        prompt = "Show me the performance charts."
        response = await delegation_controller.execute_reasoning_with_progress(
            prompt=prompt,
            websocket_send_callback=mock_send_callback,
            reasoning_delay=4.5
        )
        
        assert response == f"Reasoning response for {prompt}"
        
        # Assert progress tokens were emitted
        assert len(progress_messages) > 0
        first_token_payload = progress_messages[0]
        assert first_token_payload["type"] == "progress"
        assert first_token_payload["token"] in ["thinking...", "accessing knowledge base..."]

    asyncio.run(run_test())

def test_delegation_no_progress_tokens_for_fast_reasoning(delegation_controller):
    async def run_test():
        progress_messages: List[Dict[str, Any]] = []
        
        async def mock_send_callback(message: Dict[str, Any]):
            progress_messages.append(message)

        # Fast query
        prompt = "Fast hello"
        response = await delegation_controller.execute_reasoning_with_progress(
            prompt=prompt,
            websocket_send_callback=mock_send_callback,
            reasoning_delay=0.0
        )
        
        assert response == f"Reasoning response for {prompt}"
        assert len(progress_messages) == 0

    asyncio.run(run_test())

def test_ui_card_generator(delegation_controller):
    # 1. Product Recap Card
    product_data = {
        "product_name": "UltraSynth Pro Voice Gateway",
        "price": "$299/mo",
        "description": "High-fidelity, ultra-low-latency voice synthesis engine."
    }
    card = delegation_controller.generate_ui_card("product_recap", product_data)
    assert card["card_type"] == "product_recap"
    assert card["title"] == "Product Recap"
    assert card["data"]["product_name"] == "UltraSynth Pro Voice Gateway"
    assert card["data"]["price"] == "$299/mo"
    assert "timestamp" in card

    # 2. Poll Card
    poll_data = {
        "question": "Is the voice quality realistic?",
        "options": ["Excellent", "Good", "Needs Improvement"]
    }
    card = delegation_controller.generate_ui_card("poll", poll_data)
    assert card["card_type"] == "poll"
    assert card["title"] == "Poll"
    assert card["data"]["question"] == "Is the voice quality realistic?"
    assert card["data"]["options"] == ["Excellent", "Good", "Needs Improvement"]

    # 3. Custom Card schema fallback
    custom_data = {"custom_field": "custom_value"}
    card = delegation_controller.generate_ui_card("custom_type", custom_data)
    assert card["card_type"] == "custom_type"
    assert card["data"]["custom_field"] == "custom_value"
