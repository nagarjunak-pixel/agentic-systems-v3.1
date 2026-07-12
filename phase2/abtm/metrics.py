import os
import json
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("ABTM.Metrics")

class MetricReporter:
    def __init__(self, memory_engine: Any, log_filename: str = "audit/business_metrics.jsonl"):
        self.memory_engine = memory_engine
        self.log_filename = log_filename
        
        # Load schema
        schema_path = os.path.join(os.path.dirname(__file__), "business_metrics_schema.json")
        try:
            with open(schema_path, "r") as f:
                self.schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load business metrics schema: {e}")
            self.schema = None

    def validate_metric(self, metric_data: Dict[str, Any]) -> bool:
        if not self.schema:
            return self._manual_validate(metric_data)
        
        try:
            import jsonschema
            jsonschema.validate(instance=metric_data, schema=self.schema)
            return True
        except ImportError:
            return self._manual_validate(metric_data)
        except Exception as e:
            logger.error(f"Metric validation failed: {e}")
            return False

    def _manual_validate(self, data: Dict[str, Any]) -> bool:
        required_keys = ["timestamp", "task_id", "agent_id", "outcome_type", "success", "roi_value_usd", "cost_usd"]
        for key in required_keys:
            if key not in data:
                return False
        if not isinstance(data["roi_value_usd"], (int, float)):
            return False
        if not isinstance(data["cost_usd"], (int, float)):
            return False
        return True

    def report_metric(self, task_id: str, agent_id: str, outcome_type: str, success: bool, roi_value_usd: float, cost_usd: float, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validates and records a business-outcome metric.
        Calculates efficiency_ratio (ROI / Cost) and writes to log_filename via memory_engine.
        """
        if details is None:
            details = {}
            
        efficiency_ratio = 0.0
        if cost_usd > 0:
            efficiency_ratio = float(roi_value_usd / cost_usd)
            
        entry = {
            "timestamp": time.time(),
            "task_id": task_id,
            "agent_id": agent_id,
            "outcome_type": outcome_type,
            "success": success,
            "roi_value_usd": float(roi_value_usd),
            "cost_usd": float(cost_usd),
            "efficiency_ratio": efficiency_ratio,
            "details": details
        }
        
        if not self.validate_metric(entry):
            raise ValueError(f"Metric report data violated business_metrics_schema: {entry}")
            
        entry_str = json.dumps(entry) + "\n"
        if self.memory_engine:
            self.memory_engine.write_file_sync(self.log_filename, entry_str, mode="a")
            logger.info(f"Recorded business outcome metric for task {task_id}")
        else:
            logger.warning("MemoryEngine not attached. Metric entry printed but not persisted.")
            
        return entry
