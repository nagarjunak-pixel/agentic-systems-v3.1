import pytest
from unittest.mock import MagicMock
from codexforge.advisor_editor import AdvisorEditorEngine

def test_advisor_editor_rejects_and_accepts():
    mock_model_router = MagicMock()
    
    # We will simulate a sequence of route calls:
    # 1. Editor writes initial code (code_generation call)
    # 2. Advisor rejects it (validation call)
    # 3. Editor revises code (code_generation call)
    # 4. Advisor approves it (validation call)
    
    route_responses = [
        # Editor call 1
        "```python\ndef divide(a, b):\n    return a / b\n```",
        # Advisor call 1
        "DECISION: REJECTED\nREASON: missing check for division by zero constraint.",
        # Editor call 2
        "```python\ndef divide(a, b):\n    if b == 0:\n        return 0\n    return a / b\n```",
        # Advisor call 2
        "DECISION: APPROVED\nREASON: code matches all constraints."
    ]
    
    def mock_route(task_type, prompt):
        return route_responses.pop(0)
        
    mock_model_router.route.side_effect = mock_route
    
    engine = AdvisorEditorEngine(mock_model_router)
    success, final_code = engine.run_loop(
        "math_utils.py",
        "def divide(a, b): pass",
        "def test_divide(): assert divide(1, 0) == 0",
        "ZeroDivisionError",
        "Must not raise ZeroDivisionError, return 0 if divisor is 0",
        max_attempts=3
    )
    
    assert success is True
    assert "if b == 0:" in final_code
    assert mock_model_router.route.call_count == 4
