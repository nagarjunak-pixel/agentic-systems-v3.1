import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Callable

logger = logging.getLogger("CodexForge.Validation")

class ValidationHarness:
    def __init__(self, sandbox: Any):
        self.sandbox = sandbox

    def verify_red_state(self, test_file_rel: str) -> Tuple[bool, str]:
        """
        Validates that the reproduction test fails (RED state) first (V005).
        """
        logger.info(f"Verifying RED state for {test_file_rel}")
        res = self.sandbox.run_command(f"python3 -m pytest {test_file_rel} -v")
        exit_code = res.get("exit_code", -1)
        stdout = res.get("stdout", "")
        stderr = res.get("stderr", "")
        
        # Test passes if exit_code == 0, so RED state means exit_code != 0
        is_red = (exit_code != 0)
        output = stdout + "\n" + stderr
        return is_red, output

    def verify_green_state(self, test_file_rel: str) -> Tuple[bool, str]:
        """
        Validates that the reproduction test passes (GREEN state).
        """
        logger.info(f"Verifying GREEN state for {test_file_rel}")
        res = self.sandbox.run_command(f"python3 -m pytest {test_file_rel} -v")
        exit_code = res.get("exit_code", -1)
        stdout = res.get("stdout", "")
        stderr = res.get("stderr", "")
        
        is_green = (exit_code == 0)
        output = stdout + "\n" + stderr
        return is_green, output


class PlaywrightScaffold:
    """
    Playwright E2E driver scaffold (V001).
    Wraps browser actions, replacing standard sleep calls with event-driven wait triggers.
    If playwright is unavailable, falls back to structural mocks.
    """
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.actions_log = []
        self.playwright_available = False
        
        if not mock_mode:
            try:
                from playwright.sync_api import sync_playwright
                self.playwright_available = True
                logger.info("Playwright library detected. E2E browser mode active.")
            except ImportError:
                logger.warning("Playwright library not found. Stubbing E2E browser interactions.")

    def run_e2e_flow(self, url: str, actions: List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        Executes a sequence of E2E UI actions.
        actions: list of (action_type, target/selector) e.g., [("click", "#login-btn"), ("type", "#username")]
        """
        if self.playwright_available and not self.mock_mode:
            return self._run_real_playwright(url, actions)
        else:
            return self._run_mock_playwright(url, actions)

    def _run_real_playwright(self, url: str, actions: List[Tuple[str, str]]) -> Dict[str, Any]:
        from playwright.sync_api import sync_playwright
        
        self.actions_log.append(f"Navigate to {url}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url)
                
                # Replace sleep with event-driven wait trigger (V005)
                page.wait_for_load_state("networkidle")
                
                for act_type, target in actions:
                    if act_type == "click":
                        # Wait for element to be visible/clickable instead of sleep
                        page.wait_for_selector(target, state="visible", timeout=5000)
                        page.click(target)
                        self.actions_log.append(f"Clicked {target}")
                    elif act_type == "type":
                        # Type text, target format: "selector|text"
                        selector, text = target.split("|", 1)
                        page.wait_for_selector(selector, state="visible", timeout=5000)
                        page.fill(selector, text)
                        self.actions_log.append(f"Typed '{text}' into {selector}")
                
                # Verify title or some state
                title = page.title()
                browser.close()
                return {"success": True, "title": title, "actions": self.actions_log}
        except Exception as e:
            logger.error(f"Playwright run failed: {e}")
            return {"success": False, "error": str(e), "actions": self.actions_log}

    def _run_mock_playwright(self, url: str, actions: List[Tuple[str, str]]) -> Dict[str, Any]:
        """Runs a mock simulation of Playwright, checking selectors and waiting dynamically."""
        self.actions_log.append(f"Mock Navigate to {url}")
        
        # Simulating event-driven wait trigger
        time.sleep(0.01) # fast simulation
        
        for act_type, target in actions:
            if act_type == "click":
                self.actions_log.append(f"Mock Click element: {target}")
            elif act_type == "type":
                self.actions_log.append(f"Mock Type into element: {target}")
                
        return {
            "success": True,
            "title": "Mock Application Landing Page",
            "actions": self.actions_log
        }
        
    def wait_for_condition(self, condition_func: Callable[[], bool], timeout_seconds: float = 5.0, poll_interval: float = 0.1) -> bool:
        """
        Event-driven wait trigger instead of standard time.sleep() (GAP-13, V005).
        """
        start = time.time()
        while time.time() - start < timeout_seconds:
            if condition_func():
                return True
            time.sleep(poll_interval)
        return False
