import os
import sys
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("CodexForge.Orchestrator")

# Ensure appropriate imports
from codexforge.goal_router import GoalRouter, ParallelAgentCoordinator
from codexforge.context import ContextIndexer
from codexforge.advisor_editor import AdvisorEditorEngine
from codexforge.repl import PersistentREPL
from codexforge.validation import ValidationHarness, PlaywrightScaffold
from codexforge.detached_runner import CloudDetachedRunner
from codexforge.blueprint import DeclarativeAppBlueprintEngine

# Core imports
# Since conftest.py adds phase0, phase1, phase2 to sys.path, we can import them directly:
try:
    from core.wammr.router import ModelRouter
    from core.memory.engine import MemoryEngine
    from core.orchestrator.broker import TemporalEventBroker
    from ses.sandbox import DockerSandbox
    from aisg.guardrails import GuardrailChecker
    from abtm.budget import BudgetManager
    from wmg.gateway import WebhookMessagingGateway
except ImportError as e:
    logger.warning(f"Could not import core components directly: {e}. Mocks will be used if unavailable.")

class CodexForgeOrchestrator:
    def __init__(
        self,
        workspace_dir: str,
        model_router: Any,
        sandbox: Any,
        memory_engine: Any,
        guardrail_checker: Any,
        budget_manager: Any = None,
        wmg: Any = None,
        connection_id: Optional[str] = None
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.model_router = model_router
        self.sandbox = sandbox
        self.memory_engine = memory_engine
        self.guardrail_checker = guardrail_checker
        self.budget_manager = budget_manager
        self.wmg = wmg
        self.connection_id = connection_id

        # Internal components
        self.goal_router = GoalRouter(self.sandbox, self.model_router, self.budget_manager)
        self.context_indexer = ContextIndexer(self.workspace_dir)
        self.advisor_editor = AdvisorEditorEngine(self.model_router, self.budget_manager)
        self.repl = PersistentREPL(self.workspace_dir)
        self.validation = ValidationHarness(self.sandbox)
        self.coordinator = ParallelAgentCoordinator(self.sandbox, self.model_router)
        self.blueprint_engine = DeclarativeAppBlueprintEngine(os.path.join(self.workspace_dir, "scaffolded"))
        self.detached_runner = CloudDetachedRunner(self.workspace_dir)

    def notify(self, message: str):
        """Sends notification to user via WMG if attached."""
        if self.wmg and self.connection_id:
            try:
                self.wmg.dispatch_outgoing_message(self.connection_id, "developer", message)
            except Exception as e:
                logger.warning(f"Failed to dispatch WMG message: {e}")
        else:
            logger.info(f"[Notification] {message}")

    def execute_goal(self, goal_command: str, target_file_rel: str, test_file_rel: str, constraints: str) -> bool:
        """
        Main execution loop for CodexForge Phase 3.
        """
        self.notify(f"Starting CodexForge run for goal: {goal_command}")
        
        # 1. Parse goal into tasks
        tasks = self.goal_router.parse_goal(goal_command)
        self.notify(f"Goal parsed into {len(tasks)} sub-tasks.")

        # 2. Run Context Indexer to resolve workspace files
        context_json = self.context_indexer.build_ai_native_context()
        logger.info(f"Context Index built. Files in workspace: {len(context_json)}")

        # Helper callback to execute task step-by-step
        def step_executor(task) -> Tuple[bool, str]:
            self.notify(f"Executing task: {task.description}")
            
            # AISG Input pre-check (Phase 1)
            is_allowed, verdict = self.guardrail_checker.check_input(
                self.model_router.config["routing_matrix"]["code_generation"]["primary_model"],
                task.description
            )
            if not is_allowed:
                return False, f"AISG Blocked: {verdict}"

            # Step-specific actions
            if "test" in task.description.lower() and "fail" in task.description.lower():
                # Write and verify reproduction test fails (RED state)
                target_file_abs = os.path.join(self.workspace_dir, target_file_rel)
                test_file_abs = os.path.join(self.workspace_dir, test_file_rel)
                
                # Ask Editor to write a failing test
                # Standard prompt
                test_prompt = f"Write a failing pytest reproduction test function for {target_file_rel}. Command: {goal_command}"
                
                # Check budget
                if self.budget_manager:
                    test_code_raw = self.budget_manager.wrap_router_call(
                        self.model_router, "test_writer", "code_generation", test_prompt
                    )
                else:
                    test_code_raw = self.model_router.route("code_generation", test_prompt)
                    
                test_code = self.advisor_editor._extract_code_block(test_code_raw)
                
                # Save test file safely via host/sandbox write file
                os.makedirs(os.path.dirname(test_file_abs), exist_ok=True)
                with open(test_file_abs, "w") as f:
                    f.write(test_code)
                    
                # Verify RED state
                is_red, output = self.validation.verify_red_state(test_file_rel)
                if is_red:
                    return True, f"RED state verified successfully:\n{output}"
                else:
                    return False, f"Test passed when it should have failed. Output:\n{output}"

            elif "fix" in task.description.lower() or "apply" in task.description.lower() or "implement" in task.description.lower():
                # Run Advisor-Editor loop to obtain a safe, verified fix
                target_file_abs = os.path.join(self.workspace_dir, target_file_rel)
                test_file_abs = os.path.join(self.workspace_dir, test_file_rel)
                
                with open(target_file_abs, "r") as f:
                    current_code = f.read()
                with open(test_file_abs, "r") as f:
                    test_code = f.read()
                    
                # Run the dual-agent loop to generate corrected code
                success, proposed_code = self.advisor_editor.run_loop(
                    target_file_rel, current_code, test_code, "Initial RED failure", constraints
                )
                
                if success:
                    # Write final proposed code
                    with open(target_file_abs, "w") as f:
                        f.write(proposed_code)
                    
                    # Verify GREEN state
                    is_green, output = self.validation.verify_green_state(test_file_rel)
                    if is_green:
                        # Handoff state save
                        self.repl.locals_dict["target_file"] = target_file_rel
                        self.repl.export_state_handoff(
                            self.memory_engine,
                            "codexforge/handoff_state.json",
                            [goal_command],
                            {target_file_rel: proposed_code},
                            output
                        )
                        return True, f"GREEN state achieved:\n{output}"
                    else:
                        return False, f"Tests still failed after applying Advisor-Editor fix:\n{output}"
                else:
                    return False, f"Advisor-Editor engine failed to reach consensus: {proposed_code}"

            elif "audit" in task.description.lower() or "validation" in task.description.lower():
                # Run parallel validations
                target_file_abs = os.path.join(self.workspace_dir, target_file_rel)
                test_file_abs = os.path.join(self.workspace_dir, test_file_rel)
                
                with open(target_file_abs, "r") as f:
                    code = f.read()
                    
                validation_res = self.coordinator.coordinate_validation(
                    target_file_rel, code, test_file_rel, goal_command
                )
                if validation_res["all_passed"]:
                    return True, "All parallel audits passed successfully."
                else:
                    return False, f"Some audits failed: {validation_res['sub_agents']}"

            # Fallback success for custom/unrecognized tasks
            return True, "Task completed."

        # Execute goal tasks
        success = self.goal_router.execute_tasks(step_executor)
        
        if success:
            self.notify(f"Goal successfully completed: {goal_command}")
        else:
            self.notify(f"Goal failed: {goal_command}")
            
        return success
