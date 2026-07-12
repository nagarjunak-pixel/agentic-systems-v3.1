import time
import threading
import logging
from typing import Dict, Any, Callable, List, Tuple

logger = logging.getLogger("TemporalEventBroker")

class TemporalEventBroker:
    def __init__(self):
        self.timers: List[Tuple[float, Callable[[], None], str]] = []  # (trigger_time, callback, task_id)
        self.file_watchers: Dict[str, List[Tuple[Callable[[str], None], str]]] = {}  # filepath -> [(callback, task_id)]
        self.webhook_listeners: Dict[str, List[Tuple[Callable[[Dict[str, Any]], None], str]]] = {}  # webhook_id -> [(callback, task_id)]
        self.lock = threading.Lock()
        
        self.shutdown_event = threading.Event()
        self.broker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.broker_thread.start()

    def _run_loop(self):
        while not self.shutdown_event.is_set():
            now = time.time()
            triggered = []

            with self.lock:
                # Process timers
                remaining_timers = []
                for trigger_time, callback, task_id in self.timers:
                    if now >= trigger_time:
                        triggered.append((callback, None, f"Timer wakeup for task {task_id}"))
                    else:
                        remaining_timers.append((trigger_time, callback, task_id))
                self.timers = remaining_timers

            # Fire triggered timers outside lock to avoid deadlocks
            for callback, arg, msg in triggered:
                logger.info(msg)
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in timer callback: {e}")

            time.sleep(0.1)

    def register_timer(self, delay_seconds: float, task_id: str, callback: Callable[[], None]):
        """Schedule a wake-up callback after delay_seconds."""
        with self.lock:
            trigger_time = time.time() + delay_seconds
            self.timers.append((trigger_time, callback, task_id))
            logger.info(f"Registered wake-up timer for task {task_id} in {delay_seconds}s.")

    def register_file_watcher(self, filepath: str, task_id: str, callback: Callable[[str], None]):
        """Register a callback when a file changes (simulated or real)."""
        with self.lock:
            if filepath not in self.file_watchers:
                self.file_watchers[filepath] = []
            self.file_watchers[filepath].append((callback, task_id))
            logger.info(f"Registered file watcher for '{filepath}' (task {task_id}).")

    def register_webhook(self, webhook_id: str, task_id: str, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback when a webhook is triggered."""
        with self.lock:
            if webhook_id not in self.webhook_listeners:
                self.webhook_listeners[webhook_id] = []
            self.webhook_listeners[webhook_id].append((callback, task_id))
            logger.info(f"Registered webhook listener for webhook '{webhook_id}' (task {task_id}).")

    def trigger_file_change(self, filepath: str):
        """Simulate a file change event to wake up registered tasks."""
        callbacks_to_fire = []
        with self.lock:
            if filepath in self.file_watchers:
                callbacks_to_fire = list(self.file_watchers[filepath])

        for callback, task_id in callbacks_to_fire:
            logger.info(f"File change event triggered for '{filepath}' -> waking up task {task_id}")
            try:
                callback(filepath)
            except Exception as e:
                logger.error(f"Error in file watcher callback: {e}")

    def trigger_webhook_receive(self, webhook_id: str, payload: Dict[str, Any]):
        """Simulate a webhook reception to wake up registered tasks."""
        callbacks_to_fire = []
        with self.lock:
            if webhook_id in self.webhook_listeners:
                callbacks_to_fire = list(self.webhook_listeners[webhook_id])

        for callback, task_id in callbacks_to_fire:
            logger.info(f"Webhook event triggered for '{webhook_id}' -> waking up task {task_id}")
            try:
                callback(payload)
            except Exception as e:
                logger.error(f"Error in webhook listener callback: {e}")

    def shutdown(self):
        self.shutdown_event.set()
