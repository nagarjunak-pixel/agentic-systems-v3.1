import os
import json
import shutil
import pytest
from ses.sandbox import DockerSandbox, TranscodeAPIClient

TEMP_WORKSPACE = "/Users/venkataswaraswamy/Desktop/agentic_core/phase1/tests/temp_workspace"

@pytest.fixture(autouse=True)
def setup_workspace():
    os.makedirs(TEMP_WORKSPACE, exist_ok=True)
    yield
    if os.path.exists(TEMP_WORKSPACE):
        shutil.rmtree(TEMP_WORKSPACE)

def test_seccomp_profile_valid():
    sandbox = DockerSandbox(TEMP_WORKSPACE)
    assert sandbox.seccomp_valid is True
    # Verify critical syscalls are allowed in the JSON
    names = sandbox.seccomp_config["syscalls"][0]["names"]
    assert "futex" in names
    assert "rt_sigreturn" in names
    assert "statx" in names
    assert "getcwd" in names
    assert "pipe" in names
    assert "pipe2" in names

def test_sandbox_run_command_mock():
    sandbox = DockerSandbox(TEMP_WORKSPACE)
    res = sandbox.run_command("echo 'Hello Sandbox'", mock=True)
    assert res["exit_code"] == 0
    assert "Hello Sandbox" in res["stdout"].strip()
    assert res["is_mocked"] is True

def test_sandbox_egress_blocking_mock():
    sandbox = DockerSandbox(TEMP_WORKSPACE)
    res = sandbox.run_command("curl https://blocked-domain.com", mock=True)
    assert res["exit_code"] != 0
    assert "Blocked by egress proxy whitelist" in res["stderr"]

def test_sandbox_ffmpeg_forbidden_mock():
    sandbox = DockerSandbox(TEMP_WORKSPACE)
    res = sandbox.run_command("ffmpeg -i input.mp4 output.mp4", mock=True)
    assert res["exit_code"] == 127
    assert "Local FFmpeg composition is forbidden" in res["stderr"]

def test_transcode_api_client():
    client = TranscodeAPIClient()
    res = client.transcode("input.mp4", {"scale": "1920:1080"})
    assert res["status"] == "QUEUED"
    assert "tx-job-" in res["job_id"]

def test_sandbox_run_command_docker():
    sandbox = DockerSandbox(TEMP_WORKSPACE)
    if not sandbox.is_docker_available():
        pytest.skip("Docker not available in this environment. Skipping Docker execution test.")
        
    res = sandbox.run_command("echo 'Inside Docker Container'", mock=False)
    assert res["exit_code"] == 0
    assert "Inside Docker Container" in res["stdout"].strip()
    assert res["is_mocked"] is False
