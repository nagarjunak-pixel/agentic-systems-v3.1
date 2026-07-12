import time
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("WMG.API")

class AINativeAPI:
    """
    Exposes AI-native API endpoints designed for external agent consumption (V003).
    Ensures structured JSON responses, semantic validation, and routing details.
    """
    def __init__(self, budget_manager: Any, runaway_guard: Any, gateway: Any, model_router: Any):
        self.budget_manager = budget_manager
        self.runaway_guard = runaway_guard
        self.gateway = gateway
        self.model_router = model_router

    def handle_request(self, path: str, method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Dispatches request routes to appropriate handler methods.
        Returns structured JSON responses with metadata.
        """
        logger.info(f"AI-Native Endpoint Call: {method} {path}")
        
        try:
            if path == "/api/v1/agent/status" and method == "GET":
                return self._get_agent_status()
            elif path == "/api/v1/agent/query" and method == "POST":
                if not payload:
                    return {"error": "Missing request payload", "status_code": 400}
                return self._handle_agent_query(payload)
            elif path == "/api/v1/metrics/summary" and method == "GET":
                return self._get_metrics_summary()
            else:
                return {
                    "error": f"Route not found: {method} {path}",
                    "status_code": 404
                }
        except Exception as e:
            logger.error(f"Error handling AI API request: {e}")
            return {
                "error": "Internal Server Error",
                "message": str(e),
                "status_code": 500
            }

    def _get_agent_status(self) -> Dict[str, Any]:
        """Returns the real-time status of all active agents under supervision."""
        agent_states = []
        if self.runaway_guard:
            for agent_id, meta in self.runaway_guard.agents.items():
                agent_states.append({
                    "agent_id": agent_id,
                    "status": meta.status,
                    "idle_duration_seconds": time.time() - meta.last_ping_time,
                    "pings_registered": meta.ping_count,
                    "max_idle_limit": meta.max_idle_seconds
                })
                
        return {
            "status": "success",
            "timestamp": time.time(),
            "active_agents": agent_states
        }

    def _handle_agent_query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a task request on behalf of an external agent.
        Routes via ModelRouter, enforces budget, and returns structured reasoning context.
        """
        # Semantic schema validation of incoming query
        required = ["agent_id", "task_type", "prompt"]
        for field in required:
            if field not in payload:
                return {
                    "error": f"Semantic validation failed. Missing required field: {field}",
                    "status_code": 422
                }
                
        agent_id = payload["agent_id"]
        task_type = payload["task_type"]
        prompt = payload["prompt"]
        
        start_time = time.time()
        
        # Enforce budget and execute via model router
        try:
            if self.budget_manager and self.model_router:
                # Wrap the router execution under the budget constraints
                response = self.budget_manager.wrap_router_call(
                    router=self.model_router,
                    agent_id=agent_id,
                    task_type=task_type,
                    prompt=prompt
                )
            elif self.model_router:
                response = self.model_router.route(task_type, prompt)
            else:
                response = f"Simulated fallback response for task '{task_type}'"
                
            latency = time.time() - start_time
            
            # Return AI-native trace response
            return {
                "status": "completed",
                "result": response,
                "routing_metadata": {
                    "task_type": task_type,
                    "agent_id": agent_id,
                    "latency_seconds": latency,
                    "estimated_tokens_consumed": max(1, (len(prompt) + len(response)) // 4)
                },
                "status_code": 200
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "routing_metadata": {
                    "task_type": task_type,
                    "agent_id": agent_id,
                    "latency_seconds": time.time() - start_time
                },
                "status_code": 500
            }

    def _get_metrics_summary(self) -> Dict[str, Any]:
        """Exposes high-level business outcome statistics."""
        global_usage = 0
        agent_stats = {}
        
        if self.budget_manager:
            global_usage = self.budget_manager.global_usage
            agent_stats = self.budget_manager.agent_usage
            
        return {
            "status": "success",
            "global_tokens_consumed": global_usage,
            "agent_tokens_consumed": agent_stats,
            "timestamp": time.time()
        }
