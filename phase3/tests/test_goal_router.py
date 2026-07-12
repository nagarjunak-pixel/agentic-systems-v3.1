import pytest
from unittest.mock import MagicMock
from codexforge.goal_router import GoalRouter, KanbanTask, ParallelAgentCoordinator

def test_goal_router_parses_goal():
    mock_sandbox = MagicMock()
    mock_model_router = MagicMock()
    
    # Model router returns tasks list
    mock_model_router.route.return_value = (
        "1. Write failing test\n"
        "2. Verify RED state\n"
        "3. Implement fix\n"
        "4. Verify GREEN state"
    )
    
    router = GoalRouter(mock_sandbox, mock_model_router)
    tasks = router.parse_goal("/goal Fix division by zero error")
    
    assert len(tasks) == 4
    assert tasks[0].task_id == "task_1"
    assert tasks[0].description == "Write failing test"
    assert tasks[0].status == "todo"
    
    # Verify manager-worker boundary: GoalRouter never called sandbox.run_command directly during parsing
    assert mock_sandbox.run_command.call_count == 0

def test_goal_router_executes_tasks():
    mock_sandbox = MagicMock()
    mock_model_router = MagicMock()
    
    router = GoalRouter(mock_sandbox, mock_model_router)
    router.tasks = [
        KanbanTask(task_id="task_1", description="Task 1"),
        KanbanTask(task_id="task_2", description="Task 2")
    ]
    
    callback_calls = []
    def dummy_callback(task):
        callback_calls.append(task)
        return True, "Success"
        
    success = router.execute_tasks(dummy_callback)
    
    assert success is True
    assert len(callback_calls) == 2
    assert router.tasks[0].status == "done"
    assert router.tasks[1].status == "done"
    
    # Verify manager-worker boundary: GoalRouter never executed commands directly
    assert mock_sandbox.run_command.call_count == 0

def test_parallel_agent_coordinator():
    mock_sandbox = MagicMock()
    mock_model_router = MagicMock()
    
    # Set mock outputs
    mock_sandbox.run_command.return_value = {"exit_code": 0, "stdout": "Compilation OK", "stderr": ""}
    mock_model_router.route.return_value = "APPROVED: code logic is sound."
    
    coordinator = ParallelAgentCoordinator(mock_sandbox, mock_model_router)
    res = coordinator.coordinate_validation("app.py", "def main(): pass", "test_app.py", "Fix main")
    
    assert res["all_passed"] is True
    assert "syntax-checker" in res["sub_agents"]
    assert "logic-critic" in res["sub_agents"]
    assert "test-runner" in res["sub_agents"]
    assert res["sub_agents"]["syntax-checker"]["success"] is True
    assert res["sub_agents"]["logic-critic"]["success"] is True
    assert res["sub_agents"]["test-runner"]["success"] is True
