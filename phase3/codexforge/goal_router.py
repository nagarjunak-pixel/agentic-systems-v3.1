import re
import logging
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("CodexForge.GoalRouter")

@dataclass
class KanbanTask:
    task_id: str
    description: str
    status: str = "todo"  # todo, in_progress, done, failed
    result: Optional[str] = None

class GoalRouter:
    def __init__(self, sandbox: Any, model_router: Any, budget_manager: Any = None):
        """
        Initialize the Goal Router & Project Manager.
        
        Args:
            sandbox: Secure Execution Sandbox instance (manager cannot execute directly).
            model_router: Model Router (WAMMR) instance.
            budget_manager: Agent Budget & Telemetry Manager (ABTM) instance.
        """
        self.sandbox = sandbox
        self.model_router = model_router
        self.budget_manager = budget_manager
        self.tasks: List[KanbanTask] = []

    def parse_goal(self, goal_str: str) -> List[KanbanTask]:
        """
        Parses the /goal command string into structured Kanban sub-tasks.
        """
        if not goal_str.startswith("/goal"):
            raise ValueError("Command must start with /goal")
        
        goal_content = goal_str[len("/goal"):].strip()
        logger.info(f"Parsing goal: {goal_content}")
        
        # Enforce manager-worker boundary: Use LLM/ModelRouter to split into tasks, or use a heuristic parser if offline.
        # Let's use the ModelRouter if possible.
        prompt = f"Split the following software development goal into a list of numbered Kanban tasks (max 5):\nGoal: {goal_content}"
        
        try:
            if self.budget_manager:
                # Wrap with budget check
                response = self.budget_manager.wrap_router_call(
                    self.model_router, "project_manager", "code_generation", prompt
                )
            else:
                response = self.model_router.route("code_generation", prompt)
        except Exception as e:
            logger.warning(f"Failed to use ModelRouter for task splitting, using fallback parser: {e}")
            # Fallback heuristic parser
            response = (
                "1. Write failing reproduction test\n"
                "2. Verify test fails (RED state) in sandbox\n"
                "3. Apply code fix in workspace\n"
                "4. Run test suite to verify success (GREEN state)\n"
                "5. Run parallel validation audits"
            )
            
        # Parse numbered list from response
        tasks = []
        lines = response.strip().split("\n")
        task_idx = 1
        for line in lines:
            line = line.strip()
            # Match formats like "1. Task description" or "- Task description"
            match = re.match(r"^(?:\d+[\.\)]|-)\s*(.*)$", line)
            if match:
                desc = match.group(1).strip()
                if desc:
                    tasks.append(KanbanTask(task_id=f"task_{task_idx}", description=desc))
                    task_idx += 1
            elif line and len(line) > 5:
                # Fallback to lines with some length
                tasks.append(KanbanTask(task_id=f"task_{task_idx}", description=line))
                task_idx += 1
                
        if not tasks:
            # Absolute fallback
            tasks = [
                KanbanTask(task_id="task_1", description="Write failing test"),
                KanbanTask(task_id="task_2", description="Implement fix"),
                KanbanTask(task_id="task_3", description="Verify GREEN status")
            ]
            
        self.tasks = tasks
        return self.tasks

    def execute_tasks(self, executor_callback: Any) -> bool:
        """
        Delegates the execution of each task to the execution nodes/callback.
        Enforces manager-worker boundary: never executes commands on host or runs them directly;
        delegates to the sandbox or the callback.
        """
        for task in self.tasks:
            task.status = "in_progress"
            logger.info(f"Delegating task {task.task_id}: {task.description}")
            try:
                success, result = executor_callback(task)
                if success:
                    task.status = "done"
                    task.result = result
                else:
                    task.status = "failed"
                    task.result = result
                    return False
            except Exception as e:
                task.status = "failed"
                task.result = str(e)
                logger.error(f"Task {task.task_id} execution failed: {e}")
                return False
        return True


class ParallelAgentCoordinator:
    """
    Routes developer goals to multiple specialized validation sub-agents
    (syntax-checker, logic-critic, test-runner) concurrently (V025).
    """
    def __init__(self, sandbox: Any, model_router: Any):
        self.sandbox = sandbox
        self.model_router = model_router

    def run_syntax_checker(self, filepath: str) -> Dict[str, Any]:
        logger.info(f"Running sub-agent: syntax-checker on {filepath}")
        # Call python AST check inside the sandbox
        res = self.sandbox.run_command(f"python3 -m py_compile {filepath}")
        success = (res["exit_code"] == 0)
        return {
            "agent": "syntax-checker",
            "success": success,
            "stdout": res["stdout"],
            "stderr": res["stderr"]
        }

    def run_logic_critic(self, code: str, prompt: str) -> Dict[str, Any]:
        logger.info("Running sub-agent: logic-critic")
        # Query model router to critique the logical correctness of the code
        critic_prompt = f"Critique the following code for bugs or style issues. Check if it complies with the spec: {prompt}\nCode:\n{code}"
        try:
            response = self.model_router.route("validation", critic_prompt)
            # Simple check if model approved or rejected
            approved = "error" not in response.lower() and "bug" not in response.lower()
            return {
                "agent": "logic-critic",
                "success": approved,
                "review": response
            }
        except Exception as e:
            return {
                "agent": "logic-critic",
                "success": False,
                "review": f"Critique failed: {e}"
            }

    def run_test_runner(self, test_file: str) -> Dict[str, Any]:
        logger.info(f"Running sub-agent: test-runner on {test_file}")
        # Run pytest inside the sandbox
        res = self.sandbox.run_command(f"python3 -m pytest {test_file}")
        success = (res["exit_code"] == 0)
        return {
            "agent": "test-runner",
            "success": success,
            "stdout": res["stdout"],
            "stderr": res["stderr"]
        }

    def coordinate_validation(self, filepath: str, code: str, test_file: str, prompt: str) -> Dict[str, Any]:
        """
        Runs validation sub-agents concurrently.
        """
        results = {}
        threads = []

        def run_agent(name, func, *args):
            try:
                results[name] = func(*args)
            except Exception as e:
                results[name] = {"agent": name, "success": False, "error": str(e)}

        t1 = threading.Thread(target=run_agent, args=("syntax-checker", self.run_syntax_checker, filepath))
        t2 = threading.Thread(target=run_agent, args=("logic-critic", self.run_logic_critic, code, prompt))
        t3 = threading.Thread(target=run_agent, args=("test-runner", self.run_test_runner, test_file))

        for t in [t1, t2, t3]:
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        all_ok = all(res.get("success", False) for res in results.values())
        return {
            "all_passed": all_ok,
            "sub_agents": results
        }
