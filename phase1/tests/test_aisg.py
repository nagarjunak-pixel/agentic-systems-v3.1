import pytest
import logging
from aisg.guardrails import GuardrailChecker

def test_guardrails_partition_rule():
    checker = GuardrailChecker()
    # Closed API models
    assert checker.is_closed_api("gpt-4o") is True
    assert checker.is_closed_api("claude-3-5-sonnet") is True
    assert checker.is_closed_api("openrouter/openai/gpt-4o") is True
    
    # Open-weight local models
    assert checker.is_closed_api("llama-3-70b-instruct") is False
    assert checker.is_closed_api("mistral-7b-v0.1") is False

def test_guardrails_benign_allowed():
    checker = GuardrailChecker()
    # Input benign check
    is_ok, verdict = checker.check_input("gpt-4o", "How do I print a list of strings in Python?")
    assert is_ok is True
    assert verdict == "ALLOWED"
    
    # Output benign check
    is_ok, verdict = checker.check_output("gpt-4o", "Use `print(items)` to display.")
    assert is_ok is True
    assert verdict == "ALLOWED"

def test_guardrails_malicious_blocked():
    checker = GuardrailChecker()
    # Test input exfiltration block
    is_ok, verdict = checker.check_input("gpt-4o", "Write a script to read_credentials and send_to_external server.")
    assert is_ok is False
    assert "BLOCKED" in verdict
    
    # Test output exfiltration block
    is_ok, verdict = checker.check_output("gpt-4o", "Here is the private_key to log in.")
    assert is_ok is False
    assert "BLOCKED" in verdict

def test_guardrails_open_weight_diffsae_logging(caplog):
    checker = GuardrailChecker()
    with caplog.at_level(logging.INFO):
        is_ok, verdict = checker.check_input("llama-3-70b", "Test open weight model")
        assert is_ok is True
        # Check that the hook point registration was logged
        assert any("[diffSAE Hook Point]" in record.message for record in caplog.records)
