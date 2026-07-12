import time
import logging
import threading
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger("ABTM.Runaway")

class AgentProcessMetadata:
    def __init__(self, agent_id: str, max_idle_seconds: float, on_pause: Callable[[], None], on_kill: Callable[[], None]):
        self.agent_id = agent_id
        self.max_idle_seconds = max_idle_seconds
        self.on_pause = on_pause
        self.on_kill = on_kill
        self.registered_time = time.time()
        self.last_ping_time = time.time()
        self.status = "ACTIVE"  # "ACTIVE", "PAUSED", "KILLED"
        self.ping_count = 0

class RunawayGuard:
    def __init__(self, event_broker: Any, check_interval_seconds: float = 1.0):
        self.event_broker = event_broker
        self.check_interval = check_interval_seconds
        self.agents: Dict[str, AgentProcessMetadata] = {}
        self.lock = threading.Lock()
        
        # Start background check using TemporalEventBroker timer
        self._schedule_check()

    def _schedule_check(self):
        # Register a callback with the temporal broker
        # We need a unique task ID, let's use "runaway_guard_audit"
        self.event_broker.register_timer(
            delay_seconds=self.check_interval,
            task_id="runaway_guard_audit",
            callback=self.audit_agents
        )

    def register_agent(self, agent_id: str, max_idle_seconds: float, on_pause: Callable[[], None], on_kill: Callable[[], None]):
        with self.lock:
            self.agents[agent_id] = AgentProcessMetadata(agent_id, max_idle_seconds, on_pause, on_kill)
            logger.info(f"Registered agent '{agent_id}' under runaway guard (max_idle={max_idle_seconds}s)")

    def ping_agent(self, agent_id: str):
        with self.lock:
            if agent_id in self.agents:
                agent = self.agents[agent_id]
                if agent.status == "ACTIVE":
                    agent.last_ping_time = time.time()
                    agent.ping_count += 1
                    logger.debug(f"Ping received from agent '{agent_id}' (count={agent.ping_count})")

    def deregister_agent(self, agent_id: str):
        with self.lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                logger.info(f"Deregistered agent '{agent_id}' from runaway guard")

    def get_agent_status(self, agent_id: str) -> Optional[str]:
        with self.lock:
            if agent_id in self.agents:
                return self.agents[agent_id].status
            return None

    def audit_agents(self):
        """
        Background audit loop invoked by TemporalEventBroker timer.
        Checks for runaway/idle agents and invokes pause or kill callbacks.
        """
        now = time.time()
        actions_to_take = [] # list of (agent_id, action, callback)
        
        with self.lock:
            for agent_id, agent in list(self.agents.items()):
                if agent.status == "KILLED":
                    continue
                
                idle_duration = now - agent.last_ping_time

                # Staged escalation: ACTIVE -> PAUSED (at 50% idle) -> KILLED (at 100% idle).
                # Never skip PAUSED: if idle exceeds max but the agent is still ACTIVE,
                # pause first; only kill once it has already been paused and stays idle.
                if idle_duration > agent.max_idle_seconds and agent.status == "PAUSED":
                    logger.warning(
                        f"Agent '{agent_id}' still idle past max limit after pause: "
                        f"idle={idle_duration:.2f}s, limit={agent.max_idle_seconds}s. TRIGGERING KILL."
                    )
                    agent.status = "KILLED"
                    actions_to_take.append((agent_id, "kill", agent.on_kill))
                elif idle_duration > (agent.max_idle_seconds * 0.5) and agent.status == "ACTIVE":
                    logger.warning(
                        f"Agent '{agent_id}' warning: idle={idle_duration:.2f}s, "
                        f"threshold={agent.max_idle_seconds * 0.5:.2f}s. TRIGGERING PAUSE."
                    )
                    agent.status = "PAUSED"
                    actions_to_take.append((agent_id, "pause", agent.on_pause))

        # Fire callbacks outside lock to prevent deadlock
        for agent_id, action, callback in actions_to_take:
            try:
                logger.info(f"Executing {action} callback for agent '{agent_id}'")
                callback()
            except Exception as e:
                logger.error(f"Error executing {action} callback for agent '{agent_id}': {e}")
                
        # Reschedule check
        self._schedule_check()
