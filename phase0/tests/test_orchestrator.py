import time
import pytest
from unittest.mock import MagicMock
from core.wammr.router import ModelRouter
from core.memory.engine import MemoryEngine
from core.orchestrator.broker import TemporalEventBroker
from core.orchestrator.hitl import HITLGateway
from core.orchestrator.loop import PlannerBuilderJudgeLoop

@pytest.fixture
def core_components():
    router = ModelRouter()
    # Mock route to avoid real API dependencies in test runs
    router.client_override = lambda m, p, t: "Mock Response"
    
    memory = MemoryEngine("/Users/venkataswaraswamy/Desktop/agentic_core/phase0/tests/temp_orch_memory")
    broker = TemporalEventBroker()
    hitl = HITLGateway()
    
    yield router, memory, broker, hitl
    
    memory.shutdown()
    broker.shutdown()

def test_planner_builder_judge_success(core_components):
    router, memory, broker, hitl = core_components
    loop = PlannerBuilderJudgeLoop(router, memory, broker, hitl)

    # Ingest standard goal, verify it plans and finishes successfully
    success = loop.run_goal("goal-1", "Standard success path")
    assert success is True
    assert len(loop.active_tasks) == 2
    assert all(t["status"] == "done" for t in loop.active_tasks)


def test_self_repair_pathway(core_components):
    router, memory, broker, hitl = core_components
    loop = PlannerBuilderJudgeLoop(router, memory, broker, hitl)

    # Force the task to fail its initial check, triggering self-repair
    # The default self-repair mock returns True (success)
    failed_task = {
        "task_id": "goal-2-t1",
        "title": "Config task with self-repair success",
        "status": "todo",
        "attempt_count": 0,
        "force_fail": True
    }
    
    loop.active_tasks = [failed_task]
    success = loop._execute_task_lifecycle(failed_task)
    assert success is True
    assert failed_task["attempt_count"] == 2  # 1 for initial fail, 1 for self-repair run


def test_hitl_escalation_pathway(core_components):
    router, memory, broker, hitl = core_components
    loop = PlannerBuilderJudgeLoop(router, memory, broker, hitl)

    # Force task to fail initial run, and force self-repair execution to fail as well
    failed_task = {
        "task_id": "goal-3-t1",
        "title": "Task with repair fail -> HITL escalation",
        "status": "todo",
        "attempt_count": 0,
        "force_fail": True,
        "force_fail_repair": True
    }
    
    # Configure HITL gateway with mock decision to retry, which should pass on the next attempt
    hitl.set_mock_decision("goal-3-t1", {"action": "retry", "parameters": {}, "notes": "Human approved retry"})
    
    loop.active_tasks = [failed_task]
    # Execute loop
    success = loop.run_goal("goal-3", "HITL retry scenario")
    assert success is True
    # Status of the task should be resolved to done
    assert loop.active_tasks[0]["status"] == "done"
    assert hitl.get_escalation_status("goal-3-t1")["status"] == "resolved"


def test_temporal_event_broker(core_components):
    router, memory, broker, hitl = core_components

    # 1. Timer Wakeup Test
    timer_fired = False
    def on_timer():
        nonlocal timer_fired
        timer_fired = True

    broker.register_timer(delay_seconds=0.2, task_id="task-timer", callback=on_timer)
    # Verify timer hasn't fired yet
    assert timer_fired is False
    # Wait for timer to trigger
    time.sleep(0.3)
    assert timer_fired is True

    # 2. File Watcher Wakeup Test
    file_watcher_fired = False
    def on_file_change(path):
        nonlocal file_watcher_fired
        file_watcher_fired = True
        assert path == "mock_file.py"

    broker.register_file_watcher(filepath="mock_file.py", task_id="task-file", callback=on_file_change)
    assert file_watcher_fired is False
    broker.trigger_file_change("mock_file.py")
    assert file_watcher_fired is True

    # 3. Webhook Wakeup Test
    webhook_fired = False
    def on_webhook(payload):
        nonlocal webhook_fired
        webhook_fired = True
        assert payload.get("event") == "push"

    broker.register_webhook(webhook_id="webhook-01", task_id="task-webhook", callback=on_webhook)
    assert webhook_fired is False
    broker.trigger_webhook_receive("webhook-01", {"event": "push"})
    assert webhook_fired is True
