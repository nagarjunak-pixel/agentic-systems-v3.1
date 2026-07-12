import os
import time
import json
import logging
from typing import Dict, Any, Optional, Callable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WAMMR")

class CircuitBreaker:
    def __init__(self, failure_threshold_pct: float, recovery_time_seconds: float):
        self.failure_threshold_pct = failure_threshold_pct
        self.recovery_time_seconds = recovery_time_seconds
        self.state = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"
        self.history = []  # list of (timestamp, is_failure)
        self.last_state_change = time.time()

    def record_result(self, success: bool):
        now = time.time()
        self.history.append((now, not success))
        self._cleanup()

        if self.state == "CLOSED":
            if self._should_trip():
                self.state = "OPEN"
                self.last_state_change = now
                logger.warning(f"Circuit breaker TRIPPED to OPEN. Failure rate threshold exceeded.")
        elif self.state == "HALF_OPEN":
            if success:
                self.state = "CLOSED"
                self.history.clear()
                logger.info("Circuit breaker reset to CLOSED after success in HALF_OPEN.")
            else:
                self.state = "OPEN"
                self.last_state_change = now
                logger.warning("Circuit breaker returned to OPEN after failure in HALF_OPEN.")

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_state_change > self.recovery_time_seconds:
                self.state = "HALF_OPEN"
                self.last_state_change = now
                logger.info("Circuit breaker entered HALF_OPEN (cooldown completed).")
                return True
            return False
        return True

    def _cleanup(self):
        now = time.time()
        # Keep failures only in the last 60 seconds
        self.history = [h for h in self.history if now - h[0] <= 60]
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def _should_trip(self) -> bool:
        # Require at least 4 queries before checking threshold to avoid early noise
        if len(self.history) < 4:
            return False
        fail_count = sum(1 for _, is_fail in self.history if is_fail)
        pct = (fail_count / len(self.history)) * 100
        return pct >= self.failure_threshold_pct


class SelfRepairTracker:
    def __init__(self):
        self.last_repair_time = 0.0
        self.repair_count = 0

    def can_trigger_repair(self) -> bool:
        now = time.time()
        # CAP-04: max 1 self-repair run per 15 minutes (900 seconds)
        if now - self.last_repair_time >= 900:
            return True
        return False

    def record_repair(self):
        self.last_repair_time = time.time()
        self.repair_count += 1
        logger.info(f"Self-repair recorded. Total repairs: {self.repair_count}.")


class ModelRouter:
    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            # Default location
            config_path = os.path.join(os.path.dirname(__file__), "routing_config.json")
        
        self.config_path = config_path
        self.load_config()
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.self_repair_tracker = SelfRepairTracker()
        
        # Setup circuit breakers for each unique model configuration
        cb_conf = self.config["circuit_breakers"]
        for task, matrix in self.config["routing_matrix"].items():
            for m_key in ["primary_model", "fallback_model"]:
                model_name = matrix.get(m_key)
                if model_name and model_name not in self.breakers:
                    self.breakers[model_name] = CircuitBreaker(
                        failure_threshold_pct=cb_conf["failure_threshold_pct"],
                        recovery_time_seconds=cb_conf["recovery_time_seconds"]
                    )
        
        # Client provider adapter for testing or offline usage
        self.client_override: Optional[Callable[[str, str, float], str]] = None

    def load_config(self):
        with open(self.config_path, "r") as f:
            self.config = json.load(f)

    def call_provider(self, model: str, prompt: str, timeout_ms: int) -> str:
        if self.client_override:
            return self.client_override(model, prompt, timeout_ms / 1000.0)

        # Basic multi-provider mock integration to avoid strict external network requirements
        # If API keys are present in env, we attempt a real call using standard headers
        # Anthropic, OpenAI, OpenRouter
        timeout_sec = timeout_ms / 1000.0
        
        # In a real environment, we'd make HTTP requests here
        # We can implement a clean skeleton that reads the env key and throws or calls
        if model.startswith("openrouter/"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model.replace("openrouter/", ""), "messages": [{"role": "user", "content": prompt}]}
        elif "gpt-4o" in model:
            api_key = os.getenv("OPENAI_API_KEY")
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        elif "claude" in model:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}]
            }
        else:
            raise ValueError(f"Unknown model provider format: {model}")

        if not api_key:
            raise ValueError(f"API key missing for model: {model}")

        # Execute using standard http client
        import requests
        response = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
        
        if response.status_code == 429:
            raise requests.exceptions.RequestException("Rate Limit Exceeded (429)", response=response)
        
        response.raise_for_status()
        
        res_data = response.json()
        if "gpt-4o" in model or model.startswith("openrouter/"):
            return res_data["choices"][0]["message"]["content"]
        else:
            return res_data["content"][0]["text"]

    def route(self, task_type: str, prompt: str) -> str:
        matrix = self.config["routing_matrix"].get(task_type)
        if not matrix:
            raise ValueError(f"Task type '{task_type}' not configured in routing matrix.")

        primary = matrix["primary_model"]
        fallback = matrix["fallback_model"]
        timeout_ms = matrix["timeout_ms"]
        max_retries = matrix["max_retries"]

        # 1. Attempt Primary Model
        breaker = self.breakers.get(primary)
        if breaker and breaker.can_execute():
            try:
                result = self._execute_with_retry(primary, prompt, timeout_ms, max_retries)
                breaker.record_result(True)
                return result
            except Exception as e:
                logger.error(f"Primary model '{primary}' failed: {e}")
                breaker.record_result(False)
        else:
            logger.warning(f"Primary model '{primary}' circuit breaker is OPEN/in cooldown. Bypassing to fallback.")

        # 2. Attempt Fallback Model
        fallback_breaker = self.breakers.get(fallback)
        if fallback_breaker and fallback_breaker.can_execute():
            try:
                result = self._execute_with_retry(fallback, prompt, timeout_ms, max_retries)
                fallback_breaker.record_result(True)
                return result
            except Exception as e:
                logger.error(f"Fallback model '{fallback}' failed: {e}")
                fallback_breaker.record_result(False)
                raise RuntimeError(f"All models failed for task {task_type}. Fallback failed: {e}")
        else:
            raise RuntimeError(f"All models failed and fallback breaker is OPEN for task {task_type}.")

    def _execute_with_retry(self, model: str, prompt: str, timeout_ms: int, max_retries: int) -> str:
        retries = 0
        backoff = 1.0  # seconds
        
        while True:
            try:
                return self.call_provider(model, prompt, timeout_ms)
            except Exception as e:
                # If error is a Rate Limit (429) or transient, we retry
                is_transient = "429" in str(e) or "rate limit" in str(e).lower() or isinstance(e, (TimeoutError, ConnectionError))
                if is_transient and retries < max_retries:
                    retries += 1
                    sleep_time = backoff * (2.0 ** (retries - 1))  # exponential backoff (2.0)
                    logger.info(f"Retrying call to '{model}' in {sleep_time}s due to transient error: {e}")
                    time.sleep(sleep_time)
                else:
                    raise e

    def attempt_self_repair(self, repair_func: Callable[[], bool]) -> bool:
        if self.self_repair_tracker.can_trigger_repair():
            self.self_repair_tracker.record_repair()
            try:
                success = repair_func()
                if success:
                    logger.info("Self-repair operation completed successfully.")
                    return True
                else:
                    logger.warning("Self-repair operation failed.")
                    return False
            except Exception as e:
                logger.error(f"Self-repair operation crashed: {e}")
                return False
        else:
            logger.warning("Self-repair cap active (max 1 run per 15 minutes). Skipping repair.")
            return False
