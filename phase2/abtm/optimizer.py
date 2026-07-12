import os
import json
import logging
from typing import Dict, Any, List, Callable, Tuple, Optional

logger = logging.getLogger("ABTM.Optimizer")

class CronOptimizer:
    def __init__(self, memory_engine: Any, wammr_config_path: Optional[str] = None):
        self.memory_engine = memory_engine
        self.wammr_config_path = wammr_config_path
        self.registered_hooks: List[Tuple[str, Callable[[], Dict[str, Any]]]] = []

    def register_optimizer_hook(self, name: str, hook_func: Callable[[], Dict[str, Any]]):
        """Register a hook that performs optimization checks."""
        self.registered_hooks.append((name, hook_func))
        logger.info(f"Registered optimization hook: {name}")

    def execute_optimizations(self) -> Dict[str, Any]:
        """Runs all registered optimization hooks and returns actions taken."""
        results = {}
        for name, hook in self.registered_hooks:
            try:
                res = hook()
                results[name] = {
                    "status": "success",
                    "output": res
                }
                logger.info(f"Optimization hook '{name}' executed successfully: {res}")
            except Exception as e:
                logger.error(f"Optimization hook '{name}' failed: {e}")
                results[name] = {
                    "status": "failed",
                    "error": str(e)
                }
        return results

    def wammr_router_optimizer_hook(self, metrics_filename: str = "audit/business_metrics.jsonl") -> Dict[str, Any]:
        """
        Standard optimization hook that reads metrics logs, evaluates routing performance,
        and modifies WAMMR config mappings to lower cost while maintaining success rate constraints.
        """
        if not self.memory_engine:
            return {"action": "none", "reason": "No MemoryEngine attached"}
            
        full_metrics_path = os.path.join(self.memory_engine.root_dir, metrics_filename)
        if not os.path.exists(full_metrics_path):
            return {"action": "none", "reason": "No metrics found to analyze"}
            
        # Parse metrics logs
        metrics = []
        try:
            with open(full_metrics_path, "r") as f:
                for line in f:
                    if line.strip():
                        metrics.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error parsing metrics for optimization: {e}")
            return {"action": "none", "reason": f"Error parsing metrics: {e}"}
            
        # Group by outcome_type (which maps to routing task types)
        task_stats = {}
        for m in metrics:
            o_type = m["outcome_type"]
            success = m["success"]
            cost = m["cost_usd"]
            if o_type not in task_stats:
                task_stats[o_type] = {"total": 0, "successes": 0, "total_cost": 0.0}
            task_stats[o_type]["total"] += 1
            if success:
                task_stats[o_type]["successes"] += 1
            task_stats[o_type]["total_cost"] += cost
            
        recommendations = []
        
        # Analyze performance
        # E.g., if a task type has 100% success rate and high average cost, check if we can shift
        # or recommend adjusting routing config parameters.
        # For simulation, if we see a task has successes > 5 and avg cost > 5.0, we recommend adjusting the breaker
        # or lowering effort level to conserve budget.
        for task_type, stats in task_stats.items():
            success_rate = stats["successes"] / stats["total"] if stats["total"] > 0 else 0
            avg_cost = stats["total_cost"] / stats["total"] if stats["total"] > 0 else 0
            
            if success_rate >= 0.95 and avg_cost > 1.0:
                # Highly successful but expensive. Recommend shifting from expensive primary to cheap fallback,
                # or reducing timeout constraints.
                recommendations.append({
                    "task_type": task_type,
                    "avg_cost": avg_cost,
                    "success_rate": success_rate,
                    "recommendation": "Switch primary model to cheaper fallback to optimize budget"
                })
                
        # If we have a configured config path, we can simulate modifying it or just return the recommendations
        action_taken = "none"
        if recommendations and self.wammr_config_path and os.path.exists(self.wammr_config_path):
            # Load, modify, and write WAMMR config
            try:
                with open(self.wammr_config_path, "r") as f:
                    config = json.load(f)
                
                # Apply recommendations
                for rec in recommendations:
                    tt = rec["task_type"]
                    if tt in config.get("routing_matrix", {}):
                        # Switch primary and fallback as an optimization or reduce retry/concurrency
                        matrix = config["routing_matrix"][tt]
                        # Simulating switch or tuning timeout
                        matrix["timeout_ms"] = max(1000, int(matrix["timeout_ms"] * 0.9)) # reduce timeout limit by 10%
                
                # Write back
                with open(self.wammr_config_path, "w") as f:
                    json.dump(config, f, indent=2)
                action_taken = "tuned_wammr_timeouts"
            except Exception as e:
                logger.error(f"Failed to update WAMMR configuration in optimizer: {e}")
                action_taken = "failed_to_update_config"
                
        return {
            "analyzed_tasks": len(task_stats),
            "recommendations": recommendations,
            "action_taken": action_taken
        }
