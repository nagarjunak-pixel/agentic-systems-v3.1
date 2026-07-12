import os
import json
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger("ABTM.Budget")

class BudgetExceededError(Exception):
    """Raised when the agent or global token budget is exceeded."""
    pass

class BudgetManager:
    def __init__(self, global_limit: int, memory_engine: Any = None, state_file: str = "abtm/budget_state.json"):
        self.global_limit = global_limit
        self.memory_engine = memory_engine
        self.state_file = state_file
        self.lock = threading.Lock()
        
        self.global_usage = 0
        self.agent_limits: Dict[str, int] = {}
        self.agent_usage: Dict[str, int] = {}
        
        self._load_state()

    def _load_state(self):
        if not self.memory_engine:
            return
        
        full_path = os.path.join(self.memory_engine.root_dir, self.state_file)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r") as f:
                    data = json.load(f)
                self.global_usage = data.get("global_usage", 0)
                self.agent_limits = data.get("agent_limits", {})
                self.agent_usage = data.get("agent_usage", {})
                logger.info(f"Loaded budget state: global_usage={self.global_usage}")
            except Exception as e:
                logger.error(f"Failed to load budget state: {e}")

    def _save_state(self):
        if not self.memory_engine:
            return
        
        state_data = {
            "global_usage": self.global_usage,
            "agent_limits": self.agent_limits,
            "agent_usage": self.agent_usage
        }
        try:
            self.memory_engine.write_file_sync(self.state_file, json.dumps(state_data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save budget state: {e}")

    def set_agent_limit(self, agent_id: str, limit: int):
        with self.lock:
            self.agent_limits[agent_id] = limit
            self._save_state()

    def get_usage(self, agent_id: str) -> int:
        with self.lock:
            return self.agent_usage.get(agent_id, 0)

    def record_usage(self, agent_id: str, tokens: int):
        with self.lock:
            # Check global limit
            if self.global_usage + tokens > self.global_limit:
                raise BudgetExceededError(
                    f"Global token budget exceeded: limit={self.global_limit}, "
                    f"current_usage={self.global_usage}, requested={tokens}"
                )
            
            # Check agent limit
            agent_limit = self.agent_limits.get(agent_id)
            current_agent_usage = self.agent_usage.get(agent_id, 0)
            if agent_limit is not None and current_agent_usage + tokens > agent_limit:
                raise BudgetExceededError(
                    f"Agent '{agent_id}' token budget exceeded: limit={agent_limit}, "
                    f"current_usage={current_agent_usage}, requested={tokens}"
                )
            
            # Commit usage
            self.global_usage += tokens
            self.agent_usage[agent_id] = current_agent_usage + tokens
            self._save_state()
            logger.info(f"Recorded {tokens} tokens for agent '{agent_id}'. New usage: {self.agent_usage[agent_id]}")

    def check_budget(self, agent_id: str, estimated_tokens: int = 0) -> bool:
        """Returns True if budget is safe, otherwise raises BudgetExceededError."""
        with self.lock:
            if self.global_usage + estimated_tokens > self.global_limit:
                raise BudgetExceededError(
                    f"Global token budget check failed: limit={self.global_limit}, "
                    f"current_usage={self.global_usage}, estimated={estimated_tokens}"
                )
            
            agent_limit = self.agent_limits.get(agent_id)
            current_agent_usage = self.agent_usage.get(agent_id, 0)
            if agent_limit is not None and current_agent_usage + estimated_tokens > agent_limit:
                raise BudgetExceededError(
                    f"Agent '{agent_id}' token budget check failed: limit={agent_limit}, "
                    f"current_usage={current_agent_usage}, estimated={estimated_tokens}"
                )
        return True

    def wrap_router_call(self, router: Any, agent_id: str, task_type: str, prompt: str) -> str:
        """
        Wraps WAMMR route execution. Estimates input tokens, checks budget, executes query,
        estimates output tokens, records usage, and returns response.
        Raises BudgetExceededError before or after the call if budgets are violated.
        """
        # Estimate input tokens: ~1 token per 4 characters
        est_input_tokens = max(1, len(prompt) // 4)
        self.check_budget(agent_id, est_input_tokens)
        
        # Call model router
        response = router.route(task_type, prompt)
        
        # Estimate output tokens
        est_output_tokens = max(1, len(response) // 4)
        total_tokens = est_input_tokens + est_output_tokens
        
        # Record usage (this enforces the budget and updates state)
        self.record_usage(agent_id, total_tokens)
        
        return response
