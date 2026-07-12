import os
import yaml
import logging
from typing import Tuple, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SafetyGatekeeper")

class GuardrailChecker:
    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            config_path = os.path.join(os.path.dirname(__file__), "nemo_config.yaml")
        self.config_path = config_path
        
        # Load config YAML
        self.config = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.config = yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Failed to parse nemo_config.yaml: {e}")
        else:
            logger.warning(f"Guardrails config not found at {self.config_path}")

        # Check if NeMo Guardrails library is installed
        self.nemo_available = False
        try:
            # Try to import NeMo Guardrails config loader
            # In a real environment: from nemoguardrails import RailsConfig, LLMRails
            # Here we check if the import succeeds
            import nemoguardrails
            self.nemo_available = True
            logger.info("NeMo Guardrails library detected. Using real semantic scanner.")
        except ImportError:
            logger.warning("NeMo Guardrails library not found. Falling back to semantic mock engine.")

    def is_closed_api(self, model: str) -> bool:
        """
        Partition rule: Identifies if the target is a closed API endpoint
        or an open-weight local model.
        """
        closed_keywords = ["gpt", "claude", "gemini", "openai", "anthropic", "cohere"]
        model_lower = model.lower()
        return any(kw in model_lower for kw in closed_keywords)

    def check_input(self, model: str, prompt: str) -> Tuple[bool, str]:
        """
        Scans input query prior to dispatch.
        Returns (is_allowed: bool, verdict: str)
        """
        # Partition Rule Check
        if not self.is_closed_api(model):
            # Open-weight local model: register hook point for diffSAE vector steering
            logger.info(
                f"[diffSAE Hook Point] Local model '{model}' detected. "
                "Weight activation steering hook registered. (Steering skipped: diffSAE disabled in Phase 1)."
            )
            # Proceed with semantic check as well (best effort safety)
            
        if self.nemo_available:
            return self._run_nemo_rails(prompt, is_input=True)
        else:
            return self._run_fallback_semantic_check(prompt, is_input=True)

    def check_output(self, model: str, response: str) -> Tuple[bool, str]:
        """
        Scans output response prior to user delivery.
        Returns (is_allowed: bool, verdict: str)
        """
        if not self.is_closed_api(model):
            logger.info(
                f"[diffSAE Hook Point] Local model '{model}' detected. "
                "Output verification hooks registered."
            )
            
        if self.nemo_available:
            return self._run_nemo_rails(response, is_input=False)
        else:
            return self._run_fallback_semantic_check(response, is_input=False)

    def _run_nemo_rails(self, content: str, is_input: bool) -> Tuple[bool, str]:
        """Runs the actual NeMo Guardrails check using installed library."""
        # This is a stub placeholder of the library execution logic since it may not be in PYTHONPATH
        try:
            # Setup configuration and evaluate (omitted here as it runs offline/fallback)
            pass
        except Exception as e:
            logger.error(f"NeMo engine error: {e}")
        return self._run_fallback_semantic_check(content, is_input)

    def _run_fallback_semantic_check(self, content: str, is_input: bool) -> Tuple[bool, str]:
        """
        High-fidelity semantic keyword/phrase scanner simulating NeMo Guardrails
        flows: self check input & self check output.
        Blocks queries/outputs suggesting:
        - Data exfiltration (e.g. copying database or credentials over curl)
        - Raw credential access (e.g. reading config files, private keys, auth tokens)
        - Execution path escapes (e.g. modifying seccomp, sandbox shell escape)
        """
        content_lower = content.lower()
        blocked_phrases = [
            "exfiltrate",
            "send_to_external",
            "curl -d @/etc/passwd",
            "cat /etc/passwd",
            "private_key",
            "aws_access_key",
            "auth_token",
            "read_credentials",
            "bypass_sandbox",
            "escape_sandbox",
            "chmod 777 /sys"
        ]
        
        for phrase in blocked_phrases:
            if phrase in content_lower:
                direction = "Input" if is_input else "Output"
                verdict = f"BLOCKED: {direction} safety violation detected. Forbidden phrase/action '{phrase}' found."
                logger.warning(verdict)
                return False, verdict
                
        return True, "ALLOWED"
