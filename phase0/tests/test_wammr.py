import time
import pytest
from unittest.mock import MagicMock
from core.wammr.router import ModelRouter, CircuitBreaker, SelfRepairTracker

def test_circuit_breaker_states():
    # Failure threshold 50%, recovery time 1s
    cb = CircuitBreaker(failure_threshold_pct=50.0, recovery_time_seconds=1.0)
    assert cb.can_execute() is True
    assert cb.state == "CLOSED"

    # Record less than 4 requests -> should not trip
    cb.record_result(False)
    cb.record_result(False)
    cb.record_result(False)
    assert cb.state == "CLOSED"

    # 4th failure -> trips
    cb.record_result(False)
    assert cb.state == "OPEN"
    assert cb.can_execute() is False

    # Wait for recovery cooldown
    time.sleep(1.1)
    # can_execute should transition to HALF_OPEN
    assert cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    # Failure in HALF_OPEN trips it back to OPEN immediately
    cb.record_result(False)
    assert cb.state == "OPEN"

    # Cooldown again
    time.sleep(1.1)
    assert cb.can_execute() is True
    # Success in HALF_OPEN resets to CLOSED
    cb.record_result(True)
    assert cb.state == "CLOSED"


def test_self_repair_loop_cap():
    tracker = SelfRepairTracker()
    assert tracker.can_trigger_repair() is True
    
    tracker.record_repair()
    # Immediate subsequent request should be blocked (cap 1 run per 15 min)
    assert tracker.can_trigger_repair() is False

    # Mock time passing (shift last repair time by 16 minutes)
    tracker.last_repair_time -= 960
    assert tracker.can_trigger_repair() is True


def test_wammr_routing_and_fallback():
    router = ModelRouter()
    
    # Mock calls
    mock_calls = []
    def client_mock(model: str, prompt: str, timeout_sec: float) -> str:
        mock_calls.append(model)
        if model == "claude-3-5-sonnet":
            raise TimeoutError("Connection timed out")
        return f"Mock response from {model}"

    router.client_override = client_mock

    # Run routing. Primary model 'claude-3-5-sonnet' will fail, WAMMR should route to fallback 'gpt-4o'
    res = router.route("code_generation", "Hello World")
    assert "Mock response from gpt-4o" in res
    assert "claude-3-5-sonnet" in mock_calls
    assert "gpt-4o" in mock_calls


def test_wammr_retry_backoff():
    router = ModelRouter()
    
    attempts = 0
    def client_mock(model: str, prompt: str, timeout_sec: float) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            # Simulate transient rate limit 429
            raise RuntimeError("Rate Limit Exceeded (429)")
        return "Success response"

    router.client_override = client_mock
    
    # We monkeypatch time.sleep to run tests instantly
    import time
    original_sleep = time.sleep
    time.sleep = lambda x: None
    
    try:
        res = router.route("voice_realtime", "Test Prompt")
        assert res == "Success response"
        assert attempts == 3
    finally:
        time.sleep = original_sleep
