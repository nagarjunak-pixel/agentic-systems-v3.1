import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger("HITLGateway")

class HITLGateway:
    def __init__(self):
        self.pending_escalations: Dict[str, Dict[str, Any]] = {}
        self.mock_decisions: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def escalate_task(self, task_id: str, issue: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Escalate a task block for human review. In Phase 0, this is a stub/blocking interface."""
        logger.warning(f"--- HITL ESCALATION TRIPPED ---")
        logger.warning(f"Task ID: {task_id}")
        logger.warning(f"Reason/Issue: {issue}")
        logger.warning(f"Context: {context}")
        
        with self.lock:
            self.pending_escalations[task_id] = {
                "issue": issue,
                "context": context,
                "status": "pending"
            }

        # Check if we have pre-configured mock decisions for testing
        with self.lock:
            if task_id in self.mock_decisions:
                decision = self.mock_decisions[task_id]
                logger.info(f"Auto-resolving escalation for task {task_id} using mock decision: {decision}")
                self.pending_escalations[task_id]["status"] = "resolved"
                self.pending_escalations[task_id]["decision"] = decision
                return decision

        logger.info(f"Waiting for human operator decision for task {task_id}...")
        # In a real environment, this might block on a WebSocket, DB read, or UI input.
        # For Phase 0, if no mock decision exists, we return a fallback default resolution.
        fallback_decision = {"action": "retry", "parameters": {}, "notes": "Automated fallback resolution"}
        with self.lock:
            self.pending_escalations[task_id]["status"] = "resolved"
            self.pending_escalations[task_id]["decision"] = fallback_decision
        return fallback_decision

    def set_mock_decision(self, task_id: str, decision: Dict[str, Any]):
        """Helper to pre-program decisions for unit testing."""
        with self.lock:
            self.mock_decisions[task_id] = decision

    def get_escalation_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.pending_escalations.get(task_id)
