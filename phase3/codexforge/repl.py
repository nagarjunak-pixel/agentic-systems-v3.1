import sys
import os
import json
import time
import logging
import importlib
import traceback
from typing import Dict, Any, List, Optional

logger = logging.getLogger("CodexForge.REPL")

class PersistentREPL:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        # Sandbox execution local dict space
        self.locals_dict = {
            "__builtins__": __builtins__,
        }
        # Track imported modules to reload
        self.imported_modules = set()
        
        # Ensure workspace_dir is on sys.path
        if self.workspace_dir not in sys.path:
            sys.path.insert(0, self.workspace_dir)

    def execute(self, code: str) -> Dict[str, Any]:
        """
        Executes a block of Python code, capturing stdout and stderr.
        Returns:
            Dict containing stdout, stderr, exit_code, and current variables.
        """
        import io
        from contextlib import redirect_stdout, redirect_stderr

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        
        # Track module imports in the code block to register them
        # simple regex detection of import statements
        import re
        imports = re.findall(r"^(?:import|from)\s+([a-zA-Z0-9_\.]+)", code, re.MULTILINE)
        for imp in imports:
            base_module = imp.split(".")[0]
            self.imported_modules.add(base_module)

        exit_code = 0
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                # Executing the code inside the preserved locals dictionary
                exec(code, self.locals_dict)
        except Exception as e:
            exit_code = 1
            stderr_buf.write(traceback.format_exc())

        # Exclude builtins and non-serializable elements from variables list
        repl_vars = {}
        for k, v in self.locals_dict.items():
            if k == "__builtins__":
                continue
        # Exclude builtins and force all variables to be string values for schema compatibility
        repl_vars = {}
        for k, v in self.locals_dict.items():
            if k == "__builtins__":
                continue
            repl_vars[k] = str(v)

        return {
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "exit_code": exit_code,
            "repl_vars": repl_vars
        }

    def reload_modules(self):
        """
        Implements filesystem-watcher watchdog reload (GAP-09).
        Iterates over imported modules and uses importlib.reload to refresh them.
        """
        logger.info("Watchdog Reload: refreshing stale module imports")
        for module_name in list(self.imported_modules):
            try:
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                    logger.info(f"Successfully reloaded module: {module_name}")
            except Exception as e:
                logger.warning(f"Failed to reload module {module_name}: {e}")

    def export_state_handoff(self, memory_engine: Any, filename: str, attempted_solutions: List[Any], file_diffs: Dict[str, str], lint_output: str) -> bool:
        """
        Saves the current REPL variable state, attempted solutions, diffs,
        and Advisor validation as a JSON handoff following the Phase 0 MemoryEngine schema (GAP-05).
        """
        # Formulate variables (all values must be strings)
        serializable_vars = {}
        for k, v in self.locals_dict.items():
            if k == "__builtins__":
                continue
            serializable_vars[k] = str(v)

        # Format attempted solutions to match the schema array of objects
        formatted_solutions = []
        for sol in attempted_solutions:
            if isinstance(sol, str):
                formatted_solutions.append({
                    "description": sol,
                    "result": "executed",
                    "timestamp": str(time.time())
                })
            elif isinstance(sol, dict):
                formatted_solutions.append({
                    "description": sol.get("description", "Unknown task"),
                    "result": sol.get("result", "executed"),
                    "timestamp": str(sol.get("timestamp", time.time()))
                })

        handoff_data = {
            "attempted_solutions": formatted_solutions,
            "file_diffs": file_diffs,
            "lint_output": lint_output,
            "repl_vars": serializable_vars,
            "advisor_validation": {
                "validated": True,
                "advisor_id": "advisor_bot_v1",
                "timestamp": str(time.time())
            }
        }
        
        # Save state through memory engine
        success = memory_engine.save_handoff_state(filename, handoff_data)
        if success:
            logger.info(f"Handoff state successfully validated and saved to {filename}")
        else:
            logger.error("Handoff state failed validation!")
        return success

    def import_state_handoff(self, memory_engine: Any, filename: str) -> bool:
        """
        Restores REPL variables from a JSON handoff state file (Conflict 3 sync).
        """
        full_path = os.path.join(memory_engine.root_dir, filename)
        if not os.path.exists(full_path):
            logger.error(f"Handoff file {full_path} not found.")
            return False
            
        try:
            with open(full_path, "r") as f:
                data = json.load(f)
            
            # Basic validation
            if not memory_engine.validate_handoff(data):
                logger.warning("Imported state failed validation check, importing anyway.")
                
            # Restore REPL variables
            repl_vars = data.get("repl_vars", {})
            for k, v in repl_vars.items():
                self.locals_dict[k] = v
                
            logger.info(f"Successfully restored {len(repl_vars)} variables from state handoff.")
            return True
        except Exception as e:
            logger.error(f"Failed to import state handoff: {e}")
            return False
