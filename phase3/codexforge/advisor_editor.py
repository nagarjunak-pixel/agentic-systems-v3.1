import logging
import re
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("CodexForge.AdvisorEditor")

class AdvisorEditorEngine:
    def __init__(self, model_router: Any, budget_manager: Any = None):
        self.model_router = model_router
        self.budget_manager = budget_manager

    def editor_generate_fix(self, target_file: str, current_code: str, test_code: str, test_failure_log: str, feedback: Optional[str] = None) -> str:
        """
        Editor Agent: Generates a proposed code fix.
        """
        prompt = f"""
We have a target file '{target_file}' containing the following code:
```python
{current_code}
```

We wrote the following test:
```python
{test_code}
```

It failed with this output:
```
{test_failure_log}
```
"""
        if feedback:
            prompt += f"\nAdvisor feedback on previous attempt:\n{feedback}\n\nPlease revise your implementation based on this feedback."

        prompt += "\nProvide the entire corrected code inside a ```python ... ``` block."
        
        system_instruction = "You are an expert Editor agent. Your job is to modify Python code to fix failing tests."
        
        try:
            if self.budget_manager:
                response = self.budget_manager.wrap_router_call(
                    self.model_router, "editor", "code_generation", prompt
                )
            else:
                response = self.model_router.route("code_generation", prompt)
            return self._extract_code_block(response)
        except Exception as e:
            logger.error(f"Editor failed to generate fix: {e}")
            raise e

    def advisor_audit_fix(self, target_file: str, proposed_code: str, constraints: str) -> Tuple[bool, str]:
        """
        Advisor Agent: Audits code against constraints before release (V008).
        """
        prompt = f"""
Analyze the following proposed Python code changes for '{target_file}' against the safety and functional constraints.

Proposed Code:
```python
{proposed_code}
```

Constraints to enforce:
{constraints}

Verify:
1. Does this code contain security issues (e.g. subprocess injection, secret leaks)?
2. Does it violate the project constraints?
3. Does it look correct?

Response format:
DECISION: [APPROVED or REJECTED]
REASON: [Detailed explanation of why or what to fix]
"""
        system_instruction = "You are an expert Advisor agent. Your job is to audit code edits against strict security and functional guidelines."
        
        try:
            if self.budget_manager:
                response = self.budget_manager.wrap_router_call(
                    self.model_router, "advisor", "validation", prompt
                )
            else:
                response = self.model_router.route("validation", prompt)
            
            # Parse response
            decision_match = re.search(r"DECISION:\s*(APPROVED|REJECTED)", response, re.IGNORECASE)
            reason_match = re.search(r"REASON:\s*(.*)", response, re.IGNORECASE | re.DOTALL)
            
            approved = False
            if decision_match:
                approved = (decision_match.group(1).upper() == "APPROVED")
            
            reason = reason_match.group(1).strip() if reason_match else response
            
            return approved, reason
        except Exception as e:
            logger.error(f"Advisor failed to audit fix: {e}")
            return False, f"Audit crashed: {e}"

    def run_loop(self, target_file: str, current_code: str, test_code: str, test_failure_log: str, constraints: str, max_attempts: int = 3) -> Tuple[bool, str]:
        """
        Runs the dual-agent loop.
        Editor proposes a fix, Advisor audits it. Loops until Advisor approves or max_attempts is reached.
        """
        attempt = 0
        feedback = None
        proposed_code = current_code
        
        while attempt < max_attempts:
            attempt += 1
            logger.info(f"Advisor-Editor loop attempt {attempt}/{max_attempts}")
            
            # Editor writes
            proposed_code = self.editor_generate_fix(target_file, current_code, test_code, test_failure_log, feedback)
            
            # Advisor audits
            approved, feedback = self.advisor_audit_fix(target_file, proposed_code, constraints)
            logger.info(f"Advisor decision: {'APPROVED' if approved else 'REJECTED'}. Feedback: {feedback}")
            
            if approved:
                return True, proposed_code
                
        return False, proposed_code

    def _extract_code_block(self, text: str) -> str:
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()
