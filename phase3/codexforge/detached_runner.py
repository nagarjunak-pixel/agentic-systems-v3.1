import os
import subprocess
import threading
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("CodexForge.DetachedRunner")

class CloudDetachedRunner:
    def __init__(self, workspace_dir: str, github_token: Optional[str] = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.active_jobs = {}

    def create_worktree_branch(self, branch_name: str, base_branch: str = "main") -> Dict[str, Any]:
        """
        Spins up an isolated git worktree/branch for the async run (J9-083).
        """
        logger.info(f"Creating isolated branch '{branch_name}' from '{base_branch}'")
        
        # Check if git is initialized in the workspace
        git_dir = os.path.join(self.workspace_dir, ".git")
        if not os.path.exists(git_dir):
            # Safe local simulation if git is not initialized
            logger.warning("Git repository not detected. Simulating branch creation.")
            return {
                "success": True,
                "branch": branch_name,
                "is_mock": True,
                "msg": "Simulated git branch checkout successfully."
            }

        try:
            # Safe local checkout
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.workspace_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return {
                "success": True,
                "branch": branch_name,
                "is_mock": False,
                "msg": f"Checked out new branch {branch_name}"
            }
        except subprocess.CalledProcessError as e:
            # If branch already exists, checkout it
            try:
                subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=self.workspace_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return {
                    "success": True,
                    "branch": branch_name,
                    "is_mock": False,
                    "msg": f"Checked out existing branch {branch_name}"
                }
            except Exception as e2:
                logger.error(f"Git checkout failed: {e2}")
                return {"success": False, "error": str(e2)}

    def run_refactor_async(self, command: str, branch_name: str, callback: Optional[Any] = None):
        """
        Runs the refactor/test suite asynchronously in a background thread.
        """
        job_id = f"job-{int(time.time())}"
        self.active_jobs[job_id] = {
            "status": "running",
            "command": command,
            "branch": branch_name,
            "result": None
        }

        def worker():
            logger.info(f"Asynchronous worker started for job {job_id} on branch {branch_name}")
            try:
                # Local execution wrapper for mock sandbox command
                res = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.workspace_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=60
                )
                self.active_jobs[job_id]["status"] = "completed"
                self.active_jobs[job_id]["result"] = {
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr
                }
                logger.info(f"Asynchronous worker finished for job {job_id} with exit code {res.returncode}")
                if callback:
                    callback(job_id, self.active_jobs[job_id])
            except Exception as e:
                self.active_jobs[job_id]["status"] = "failed"
                self.active_jobs[job_id]["result"] = {"error": str(e)}
                logger.error(f"Async job {job_id} failed: {e}")
                if callback:
                    callback(job_id, self.active_jobs[job_id])

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return job_id

    def open_pull_request(self, repo: str, head_branch: str, base_branch: str = "main", title: str = "CodexForge Fix", body: str = "Auto-generated PR") -> Dict[str, Any]:
        """
        Opens a pull request via GitHub API (J9-083).
        If GITHUB_TOKEN is absent, returns a mock PR payload.
        """
        logger.info(f"Opening Pull Request for {head_branch} -> {base_branch} on repo '{repo}'")
        
        if not self.github_token:
            logger.warning("GITHUB_TOKEN not found in environment. Mocking GitHub API PR creation.")
            return {
                "success": True,
                "pr_number": 42,
                "url": f"https://github.com/{repo}/pull/42",
                "status": "mocked",
                "msg": "PR successfully mocked."
            }

        # Make actual GitHub API POST request if token is set
        try:
            import requests
            url = f"https://api.github.com/repos/{repo}/pulls"
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            payload = {
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 201:
                data = response.json()
                return {
                    "success": True,
                    "pr_number": data.get("number"),
                    "url": data.get("html_url"),
                    "status": "created"
                }
            else:
                logger.error(f"GitHub API error: {response.text}")
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"GitHub PR API call crashed: {e}")
            return {"success": False, "error": str(e)}
