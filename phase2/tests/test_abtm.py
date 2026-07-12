import os
import json
import time
import pytest
import shutil
import tempfile
from typing import Dict, Any

# Imports from Phase 0 and Phase 2
from core.memory.engine import MemoryEngine
from core.orchestrator.broker import TemporalEventBroker
from core.wammr.router import ModelRouter
from abtm.budget import BudgetManager, BudgetExceededError
from abtm.runaway import RunawayGuard
from abtm.metrics import MetricReporter
from abtm.optimizer import CronOptimizer

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
def event_broker():
    broker = TemporalEventBroker()
    yield broker
    broker.shutdown()

class MockRouter:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def route(self, task_type: str, prompt: str) -> str:
        self.calls += 1
        return self.response

def test_budget_enforcement(memory_engine):
    # Setup manager: global=100 tokens, agent1=50 tokens
    manager = BudgetManager(global_limit=100, memory_engine=memory_engine)
    manager.set_agent_limit("agent1", 50)
    
    # Check limit check
    assert manager.check_budget("agent1", 10) is True
    
    # Record usage within limits
    manager.record_usage("agent1", 30)
    assert manager.get_usage("agent1") == 30
    
    # Record usage that exceeds agent limit
    with pytest.raises(BudgetExceededError) as exc_info:
        manager.record_usage("agent1", 30)
    assert "token budget exceeded" in str(exc_info.value)
    
    # Record usage that exceeds global limit
    manager.set_agent_limit("agent2", 100)
    manager.record_usage("agent2", 60) # total global now = 30 (agent1) + 60 (agent2) = 90
    
    with pytest.raises(BudgetExceededError) as exc_info_global:
        manager.record_usage("agent2", 20) # exceeds global limit of 100
    assert "Global token budget exceeded" in str(exc_info_global.value)

def test_wrap_router_call(memory_engine):
    manager = BudgetManager(global_limit=1000, memory_engine=memory_engine)
    manager.set_agent_limit("agent_test", 100)
    
    mock_router = MockRouter("Response from model")
    prompt = "Simple question"
    
    # wrap_router_call
    res = manager.wrap_router_call(mock_router, "agent_test", "code_gen", prompt)
    assert res == "Response from model"
    assert mock_router.calls == 1
    
    # Token estimation
    usage = manager.get_usage("agent_test")
    assert usage > 0
    assert usage == (len(prompt) // 4) + (len(res) // 4)

def test_runaway_guard(event_broker):
    guard = RunawayGuard(event_broker, check_interval_seconds=0.1)
    
    paused = False
    killed = False
    
    def on_pause():
        nonlocal paused
        paused = True
        
    def on_kill():
        nonlocal killed
        killed = True
        
    # Register agent with max idle time of 0.2s
    guard.register_agent("agent_loop", max_idle_seconds=0.2, on_pause=on_pause, on_kill=on_kill)
    
    # Ping once to establish baseline
    guard.ping_agent("agent_loop")
    
    # Sleep and wait for status to become PAUSED (max 1.0s)
    for _ in range(20):
        if paused:
            break
        time.sleep(0.05)
        
    assert paused is True
    assert killed is False
    assert guard.get_agent_status("agent_loop") == "PAUSED"
    
    # Wait for status to become KILLED (max 1.0s)
    for _ in range(20):
        if killed:
            break
        time.sleep(0.05)
        
    assert killed is True
    assert guard.get_agent_status("agent_loop") == "KILLED"
    
    # Deregister
    guard.deregister_agent("agent_loop")
    assert guard.get_agent_status("agent_loop") is None

def test_runaway_guard_ping_prevents_kill(event_broker):
    guard = RunawayGuard(event_broker, check_interval_seconds=0.05)
    
    paused = False
    killed = False
    
    def on_pause():
        nonlocal paused
        paused = True
        
    def on_kill():
        nonlocal killed
        killed = True
        
    # Register with 0.3s limit
    guard.register_agent("agent_ping", max_idle_seconds=0.3, on_pause=on_pause, on_kill=on_kill)
    
    # Ping
    for _ in range(3):
        time.sleep(0.08)
        guard.ping_agent("agent_ping")
        
    # Ensure not killed
    assert killed is False
    # Clean up
    guard.deregister_agent("agent_ping")

def test_outcome_metrics(memory_engine):
    reporter = MetricReporter(memory_engine)
    
    # Record a successful outcome
    metric = reporter.report_metric(
        task_id="task_123",
        agent_id="agent_123",
        outcome_type="code_generation",
        success=True,
        roi_value_usd=50.0,
        cost_usd=2.5,
        details={"loc_changed": 120}
    )
    
    assert metric["success"] is True
    assert metric["efficiency_ratio"] == 20.0 # 50 / 2.5
    
    # Check that file was created and written
    log_path = os.path.join(memory_engine.root_dir, "audit/business_metrics.jsonl")
    assert os.path.exists(log_path)
    
    with open(log_path, "r") as f:
        lines = f.readlines()
        
    assert len(lines) == 1
    saved_entry = json.loads(lines[0])
    assert saved_entry["task_id"] == "task_123"
    assert saved_entry["efficiency_ratio"] == 20.0

def test_cron_optimizer(memory_engine):
    # Setup metrics
    reporter = MetricReporter(memory_engine)
    # Write 6 successful outcomes for a task type to trigger optimizer threshold
    for i in range(6):
        reporter.report_metric(
            task_id=f"t_{i}",
            agent_id="agent_opt",
            outcome_type="media_synthesis",
            success=True,
            roi_value_usd=10.0,
            cost_usd=2.0
        )
        
    # Write a dummy WAMMR config file
    wammr_config = {
        "routing_matrix": {
            "media_synthesis": {
                "primary_model": "gpt-4o",
                "fallback_model": "claude-3",
                "timeout_ms": 5000,
                "max_retries": 3,
                "concurrency_limit": 2
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
        
    optimizer = CronOptimizer(memory_engine, wammr_config_path=config_path)
    
    # Register standard optimizer hook
    optimizer.register_optimizer_hook(
        "wammr_tune",
        optimizer.wammr_router_optimizer_hook
    )
    
    # Run optimizer
    results = optimizer.execute_optimizations()
    assert "wammr_tune" in results
    assert results["wammr_tune"]["status"] == "success"
    
    output = results["wammr_tune"]["output"]
    assert output["analyzed_tasks"] == 1
    assert output["action_taken"] == "tuned_wammr_timeouts"
    
    # Verify that the timeout_ms in the WAMMR config file was reduced (tuned)
    with open(config_path, "r") as f:
        updated_config = json.load(f)
    assert updated_config["routing_matrix"]["media_synthesis"]["timeout_ms"] < 5000
