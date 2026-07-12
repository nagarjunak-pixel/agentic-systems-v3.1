import pytest
import os
import json
from unittest.mock import MagicMock

# CodexForge components
from codexforge.orchestrator import CodexForgeOrchestrator

# Core components
from core.wammr.router import ModelRouter
from core.memory.engine import MemoryEngine
from ses.sandbox import DockerSandbox
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.vault import CredentialVault
from wmg.gateway import WebhookMessagingGateway

def test_codex_forge_tdd_integration(tmp_path):
    # 1. Setup workspace structure
    workspace_dir = tmp_path / "workspace"
    os.makedirs(workspace_dir, exist_ok=True)
    
    buggy_file = workspace_dir / "buggy_divide.py"
    with open(buggy_file, "w") as f:
        f.write("def divide(a, b):\n    return a / b\n")
        
    test_file = workspace_dir / "test_buggy_divide.py"
    
    # 2. Setup core dependencies
    # Create mock routing config
    routing_config_file = tmp_path / "routing_config.json"
    routing_config_data = {
        "routing_matrix": {
            "code_generation": {
                "primary_model": "claude-3-5-sonnet",
                "fallback_model": "gpt-4o",
                "timeout_ms": 5000,
                "max_retries": 1
            },
            "validation": {
                "primary_model": "claude-3-5-sonnet",
                "fallback_model": "gpt-4o",
                "timeout_ms": 5000,
                "max_retries": 1
            }
        },
        "circuit_breakers": {
            "failure_threshold_pct": 50,
            "recovery_time_seconds": 60
        }
    }
    with open(routing_config_file, "w") as f:
        json.dump(routing_config_data, f)
        
    model_router = ModelRouter(config_path=str(routing_config_file))
    
    # Setup mock routing calls
    route_responses = [
        # 1. Goal parsing task list split
        "1. Write failing test\n2. Implement fix\n3. Run parallel validation",
        # 2. Test generation
        "```python\nimport pytest\nfrom buggy_divide import divide\ndef test_divide_zero():\n    assert divide(10, 0) == 0\n```",
        # 3. Editor fix generation
        "```python\ndef divide(a, b):\n    if b == 0:\n        return 0\n    return a / b\n```",
        # 4. Advisor approval audit
        "DECISION: APPROVED\nREASON: Safe fix against division by zero",
        # 5. Logic critic validation
        "APPROVED: Logic is correct."
    ]
    def mock_route_call(task_type, prompt):
        return route_responses.pop(0)
    model_router.route = mock_route_call
    
    # Memory Engine (Phase 0)
    memory_dir = tmp_path / "memory"
    memory_engine = MemoryEngine(root_dir=str(memory_dir))
    
    # Sandbox (Phase 1, mock=True to keep it simple and offline)
    sandbox = DockerSandbox(workspace_dir=str(workspace_dir))
    
    # Mock run_command inside sandbox to return failure on first test run (RED)
    # and success on second test run (GREEN)
    sandbox_run_count = 0
    def mock_run_command(cmd, env_vars=None, mock=True):
        nonlocal sandbox_run_count
        sandbox_run_count += 1
        
        if "pytest" in cmd:
            if sandbox_run_count == 1:
                # RED state verification failure
                return {
                    "exit_code": 1,
                    "stdout": "FAIL: ZeroDivisionError",
                    "stderr": "",
                    "duration": 0.1,
                    "is_mocked": True
                }
            else:
                # GREEN state verification success
                return {
                    "exit_code": 0,
                    "stdout": "PASS: test_divide_zero passed",
                    "stderr": "",
                    "duration": 0.1,
                    "is_mocked": True
                }
        elif "py_compile" in cmd:
            return {
                "exit_code": 0,
                "stdout": "Compilation OK",
                "stderr": "",
                "duration": 0.1,
                "is_mocked": True
            }
            
        return {
            "exit_code": 0,
            "stdout": "Executed",
            "stderr": "",
            "duration": 0.1,
            "is_mocked": True
        }
        
    sandbox.run_command = mock_run_command
    
    # Guardrail Checker (Phase 1)
    nemo_config_file = tmp_path / "nemo_config.yaml"
    with open(nemo_config_file, "w") as f:
        f.write("security:\n  blocked_phrases: []\n")
    guardrail_checker = GuardrailChecker(config_path=str(nemo_config_file))
    
    # Budget Manager (Phase 2)
    budget_manager = BudgetManager(global_limit=10000, memory_engine=memory_engine)
    
    # Webhook Messaging Gateway (Phase 2)
    vault = CredentialVault({"slack": {"token": "xoxb-mock-token-for-testing"}})
    wmg = WebhookMessagingGateway(vault, memory_engine=memory_engine)
    wmg.establish_connection(connection_id="dev-conn", platform="slack", token_limit=5000)
    
    # 3. Instantiate and run orchestrator
    orchestrator = CodexForgeOrchestrator(
        workspace_dir=str(workspace_dir),
        model_router=model_router,
        sandbox=sandbox,
        memory_engine=memory_engine,
        guardrail_checker=guardrail_checker,
        budget_manager=budget_manager,
        wmg=wmg,
        connection_id="dev-conn"
    )
    
    success = orchestrator.execute_goal(
        goal_command="/goal Fix buggy divide function",
        target_file_rel="buggy_divide.py",
        test_file_rel="test_buggy_divide.py",
        constraints="No ZeroDivisionError, return 0 if b is 0"
    )
    
    # 4. Assert success and correctness
    assert success is True
    
    # Check if file was modified
    with open(buggy_file, "r") as f:
        updated_code = f.read()
    assert "if b == 0:" in updated_code
    
    # Check if budget state was updated
    assert budget_manager.global_usage > 0
    
    # Check if memory handoff exists
    assert os.path.exists(memory_dir / "codexforge" / "handoff_state.json")
    
    # Clean up memory writer thread to avoid open threads hanging pytest
    memory_engine.shutdown()
