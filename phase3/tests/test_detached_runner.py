import pytest
import os
from codexforge.detached_runner import CloudDetachedRunner

def test_detached_runner_mock_pr(tmp_path):
    # Instantiate with workspace
    runner = CloudDetachedRunner(str(tmp_path), github_token=None)
    
    # Check branch checkout
    res = runner.create_worktree_branch("feature-fix-zero")
    assert res["success"] is True
    
    # Check open PR without GITHUB_TOKEN
    pr_res = runner.open_pull_request(
        repo="octocat/Hello-World",
        head_branch="feature-fix-zero",
        base_branch="main",
        title="Fix divide by zero",
        body="Closes division issue."
    )
    
    assert pr_res["success"] is True
    assert pr_res["status"] == "mocked"
    assert pr_res["pr_number"] == 42
    assert "github.com/octocat/Hello-World/pull/42" in pr_res["url"]

def test_detached_runner_async_job(tmp_path):
    runner = CloudDetachedRunner(str(tmp_path), github_token=None)
    
    # Run an async echo job
    job_id = runner.run_refactor_async("echo 'Refactoring complete'", "feature-fix")
    assert job_id.startswith("job-")
    
    # Wait for completion
    import time
    for _ in range(20):
        if runner.active_jobs[job_id]["status"] == "completed":
            break
        time.sleep(0.05)
        
    job = runner.active_jobs[job_id]
    assert job["status"] == "completed"
    assert job["result"]["exit_code"] == 0
    assert "complete" in job["result"]["stdout"]
