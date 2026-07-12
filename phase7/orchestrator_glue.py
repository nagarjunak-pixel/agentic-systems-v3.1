import time
from typing import Dict, Any, Optional

class SystemStatus:
    def __init__(
        self,
        orchestrator: Optional[Any] = None,
        budget_manager: Optional[Any] = None,
        guardrail_checker: Optional[Any] = None,
        voice_gateway: Optional[Any] = None
    ):
        self.orchestrator = orchestrator
        self.budget_manager = budget_manager
        self.guardrail_checker = guardrail_checker
        self.voice_gateway = voice_gateway

    def aggregate_status(self) -> Dict[str, Any]:
        """Pulls health from all subsystems and aggregates into a unified status dict."""
        status = {
            "timestamp": time.time(),
            "status": "HEALTHY",
            "subsystems": {}
        }
        
        # 1. Phase 0: Orchestrator
        if self.orchestrator is not None:
            active_tasks = getattr(self.orchestrator, "active_tasks", [])
            status["subsystems"]["orchestrator"] = {
                "status": "RUNNING" if active_tasks else "IDLE",
                "active_tasks_count": len(active_tasks),
                "details": f"Orchestrator monitoring {len(active_tasks)} task(s)."
            }
        else:
            # Mock
            status["subsystems"]["orchestrator"] = {
                "status": "MOCKED_IDLE",
                "active_tasks_count": 0,
                "details": "Mock Orchestrator running."
            }

        # 2. Phase 2: ABTM Budgets
        if self.budget_manager is not None:
            global_limit = getattr(self.budget_manager, "global_limit", 0)
            global_usage = getattr(self.budget_manager, "global_usage", 0)
            agent_usage = getattr(self.budget_manager, "agent_usage", {})
            status["subsystems"]["abtm"] = {
                "status": "HEALTHY" if global_usage < global_limit else "BUDGET_EXCEEDED",
                "global_limit": global_limit,
                "global_usage": global_usage,
                "agent_usage": agent_usage,
                "remaining_budget": max(0, global_limit - global_usage)
            }
        else:
            # Mock
            status["subsystems"]["abtm"] = {
                "status": "MOCKED_HEALTHY",
                "global_limit": 100000,
                "global_usage": 45000,
                "agent_usage": {"planner": 15000, "builder": 30000},
                "remaining_budget": 55000
            }

        # 3. Phase 1: AISG (Safety Gatekeeper)
        if self.guardrail_checker is not None:
            nemo_available = getattr(self.guardrail_checker, "nemo_available", False)
            config_path = getattr(self.guardrail_checker, "config_path", "unknown")
            status["subsystems"]["aisg"] = {
                "status": "ACTIVE",
                "nemo_guardrails_enabled": nemo_available,
                "config_loaded": config_path
            }
        else:
            # Mock
            status["subsystems"]["aisg"] = {
                "status": "MOCKED_ACTIVE",
                "nemo_guardrails_enabled": False,
                "config_loaded": "nemo_config.yaml"
            }

        # 4. Phase 6: Voice Gateway
        if self.voice_gateway is not None:
            host = getattr(self.voice_gateway, "host", "unknown")
            port = getattr(self.voice_gateway, "port", 0)
            connections = getattr(self.voice_gateway, "connections", set())
            active_tasks = getattr(self.voice_gateway, "active_tasks", {})
            status["subsystems"]["voice_gateway"] = {
                "status": "RUNNING",
                "host": host,
                "port": port,
                "active_connections": len(connections),
                "active_tasks_count": len(active_tasks)
            }
        else:
            # Mock
            status["subsystems"]["voice_gateway"] = {
                "status": "MOCKED_RUNNING",
                "host": "127.0.0.1",
                "port": 8765,
                "active_connections": 1,
                "active_tasks_count": 0
            }
            
        # Determine global status
        for sub in status["subsystems"].values():
            if sub["status"] in ["BUDGET_EXCEEDED", "ERROR"]:
                status["status"] = "DEGRADED"
                break
                
        return status
