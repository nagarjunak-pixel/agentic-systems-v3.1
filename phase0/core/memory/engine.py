import os
import json
import queue
import threading
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("MemoryEngine")

class WriteRequest:
    def __init__(self, filepath: str, content: str, mode: str = "w"):
        self.filepath = filepath
        self.content = content
        self.mode = mode
        self.completed_event = threading.Event()
        self.error: Optional[Exception] = None

class MemoryEngine:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        os.makedirs(self.root_dir, exist_ok=True)
        self.write_queue = queue.Queue()
        self.lock = threading.Lock()
        
        # Load handoff schema
        schema_path = os.path.join(os.path.dirname(__file__), "handoff_schema.json")
        try:
            with open(schema_path, "r") as f:
                self.schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load handoff schema: {e}")
            self.schema = None

        # Start the single-threaded writer worker
        self.shutdown_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._writer_worker, daemon=True)
        self.worker_thread.start()

    def _writer_worker(self):
        while not self.shutdown_event.is_set():
            try:
                # Wait for a write request with a timeout so we can exit on shutdown
                request: WriteRequest = self.write_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                # Enforce Mutex lock on actual file writing
                with self.lock:
                    target_path = os.path.join(self.root_dir, request.filepath)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, request.mode) as f:
                        f.write(request.content)
            except Exception as e:
                logger.error(f"Error executing file write: {e}")
                request.error = e
            finally:
                request.completed_event.set()
                self.write_queue.task_done()

    def write_file_sync(self, filepath: str, content: str, mode: str = "w"):
        """Queue a write request and block until it is completed by the worker thread."""
        request = WriteRequest(filepath, content, mode)
        self.write_queue.put(request)
        # Block until the writer thread completes this specific write
        finished = request.completed_event.wait(timeout=10.0)
        if not finished:
            raise TimeoutError(f"Write operation for {filepath} timed out in queue.")
        if request.error:
            raise request.error

    def write_file_async(self, filepath: str, content: str, mode: str = "w") -> threading.Event:
        """Queue a write request and return immediately. Returns the event to wait on."""
        request = WriteRequest(filepath, content, mode)
        self.write_queue.put(request)
        return request.completed_event

    def validate_handoff(self, handoff_data: Dict[str, Any]) -> bool:
        """Validates state handoff JSON structure against the handoff schema."""
        if not self.schema:
            logger.warning("No schema loaded. Performing structural verification.")
            return self._manual_validate(handoff_data)
        
        try:
            import jsonschema
            jsonschema.validate(instance=handoff_data, schema=self.schema)
            # Additional Advisor-validation check requirement (GAP-05)
            adv = handoff_data.get("advisor_validation", {})
            return bool(adv.get("validated"))
        except ImportError:
            logger.debug("jsonschema library not found. Falling back to manual validation.")
            return self._manual_validate(handoff_data)
        except Exception as e:
            logger.error(f"Handoff validation failed schema validation: {e}")
            return False

    def _manual_validate(self, data: Dict[str, Any]) -> bool:
        """Fallback manual validation matching schema requirements."""
        required_keys = ["attempted_solutions", "file_diffs", "lint_output", "repl_vars", "advisor_validation"]
        for key in required_keys:
            if key not in data:
                logger.error(f"Validation failed: missing key '{key}'")
                return False

        if not isinstance(data["attempted_solutions"], list):
            logger.error("Validation failed: attempted_solutions must be a list")
            return False
            
        if not isinstance(data["file_diffs"], dict):
            logger.error("Validation failed: file_diffs must be a dict")
            return False

        if not isinstance(data["repl_vars"], dict):
            logger.error("Validation failed: repl_vars must be a dict")
            return False

        adv = data["advisor_validation"]
        if not isinstance(adv, dict):
            logger.error("Validation failed: advisor_validation must be a dict")
            return False

        if not adv.get("validated") or "advisor_id" not in adv or "timestamp" not in adv:
            logger.error("Validation failed: advisor_validation must be validated and contain advisor_id and timestamp")
            return False

        return True

    def save_handoff_state(self, filename: str, handoff_data: Dict[str, Any]) -> bool:
        """Validates handoff state and writes it to disk if valid."""
        if not self.validate_handoff(handoff_data):
            logger.error("Failed to save handoff state: validation failed.")
            return False
        
        content = json.dumps(handoff_data, indent=2)
        self.write_file_sync(filename, content)
        return True

    def shutdown(self):
        self.shutdown_event.set()
        # Wait for queue to process remaining items
        self.write_queue.join()
