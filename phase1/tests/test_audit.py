import os
import json
import shutil
import sys
import pytest

# Dynamically add Phase 0 path
PHASE0_PATH = "/Users/venkataswaraswamy/Desktop/agentic_core/phase0"
if PHASE0_PATH not in sys.path:
    sys.path.append(PHASE0_PATH)

from core.memory.engine import MemoryEngine
from audit.logger import CommandAuditLogger

TEMP_AUDIT_ROOT = "/Users/venkataswaraswamy/Desktop/agentic_core/phase1/tests/temp_audit_root"

@pytest.fixture(autouse=True)
def run_around():
    os.makedirs(TEMP_AUDIT_ROOT, exist_ok=True)
    yield
    if os.path.exists(TEMP_AUDIT_ROOT):
        shutil.rmtree(TEMP_AUDIT_ROOT)

def test_audit_logs_append_and_tamper_detection():
    # Initialize MemoryEngine
    engine = MemoryEngine(TEMP_AUDIT_ROOT)
    
    # Initialize Audit Logger
    log_file = "audit/command_audit.jsonl"
    audit_logger = CommandAuditLogger(engine, log_filename=log_file)
    
    # 1. Log actions
    entry0 = audit_logger.log_execution("echo 'A'", ["read", "write"], ["github.com"], 0)
    entry1 = audit_logger.log_execution("python main.py", ["execve", "futex"], ["api.openai.com"], 0)
    entry2 = audit_logger.log_execution("rm -rf /", ["unlink"], [], 1)
    
    # Verify indexes and chain links
    assert entry0["index"] == 0
    assert entry1["index"] == 1
    assert entry2["index"] == 2
    assert entry1["prev_hash"] == entry0["hash"]
    assert entry2["prev_hash"] == entry1["hash"]
    
    # Shutdown worker to flush all files to disk
    engine.shutdown()
    
    # Reload engine and verify integrity of written logs
    engine_verify = MemoryEngine(TEMP_AUDIT_ROOT)
    audit_logger_verify = CommandAuditLogger(engine_verify, log_filename=log_file)
    
    is_valid, tampered = audit_logger_verify.verify_integrity()
    assert is_valid is True
    assert len(tampered) == 0
    
    # 2. Tamper with log file to test verification engine detection
    full_log_path = os.path.join(TEMP_AUDIT_ROOT, log_file)
    with open(full_log_path, "r") as f:
        lines = f.readlines()
        
    # Modify command of entry 1
    entry1_modified = json.loads(lines[1])
    entry1_modified["command"] = "python main.py --tampered"
    lines[1] = json.dumps(entry1_modified) + "\n"
    
    with open(full_log_path, "w") as f:
        f.writelines(lines)
        
    # Verify integrity and assert that the modification is caught
    is_valid_after, tampered_after = audit_logger_verify.verify_integrity()
    assert is_valid_after is False
    # Modifying entry 1 breaks the hash of entry 1 and the prev_hash link of entry 2
    assert 1 in tampered_after
    assert 2 in tampered_after
    
    engine_verify.shutdown()
