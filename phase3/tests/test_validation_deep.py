"""Targeted tests to lift phase3/codexforge/validation.py coverage (was 38%)."""
import sys
sys.path.insert(0, "/Users/venkataswaraswamy/Desktop/agentic_core/phase0")
from codexforge.validation import ValidationHarness, PlaywrightScaffold


class FakeSandbox:
    """Simulates a sandbox whose pytest run returns RED or GREEN on demand."""
    def __init__(self, exit_code):
        self._exit = exit_code
    def run_command(self, cmd):
        return {"exit_code": self._exit, "stdout": f"ran: {cmd}", "stderr": ""}


def test_verify_red_state_true_when_exit_nonzero():
    h = ValidationHarness(FakeSandbox(exit_code=1))
    is_red, out = h.verify_red_state("tests/test_x.py")
    assert is_red is True
    assert "ran:" in out


def test_verify_red_state_false_when_exit_zero():
    h = ValidationHarness(FakeSandbox(exit_code=0))
    is_red, _ = h.verify_red_state("tests/test_x.py")
    assert is_red is False


def test_verify_green_state_true_when_exit_zero():
    h = ValidationHarness(FakeSandbox(exit_code=0))
    is_green, out = h.verify_green_state("tests/test_x.py")
    assert is_green is True


def test_verify_green_state_false_when_exit_nonzero():
    h = ValidationHarness(FakeSandbox(exit_code=2))
    is_green, _ = h.verify_green_state("tests/test_x.py")
    assert is_green is False


def test_playwright_mock_flow_runs_and_logs():
    pw = PlaywrightScaffold(mock_mode=True)
    assert pw.playwright_available is False
    res = pw.run_e2e_flow("https://example.com", [("click", "#btn"), ("type", "#user|alice")])
    assert res["success"] is True
    assert res["title"] == "Mock Application Landing Page"
    assert any("Click" in a for a in res["actions"])


def test_wait_for_condition_returns_true_when_met():
    pw = PlaywrightScaffold(mock_mode=True)
    assert pw.wait_for_condition(lambda: True, timeout_seconds=0.5) is True


def test_wait_for_condition_returns_false_on_timeout():
    pw = PlaywrightScaffold(mock_mode=True)
    assert pw.wait_for_condition(lambda: False, timeout_seconds=0.2, poll_interval=0.05) is False
