import os
import time
import pytest
import shutil
import threading
from core.memory.engine import MemoryEngine

TEMP_TEST_DIR = "/Users/venkataswaraswamy/Desktop/agentic_core/phase0/tests/temp_memory_root"

@pytest.fixture(autouse=True)
def run_around_tests():
    # Setup
    os.makedirs(TEMP_TEST_DIR, exist_ok=True)
    yield
    # Teardown
    if os.path.exists(TEMP_TEST_DIR):
        shutil.rmtree(TEMP_TEST_DIR)

def test_mutex_serialization():
    engine = MemoryEngine(TEMP_TEST_DIR)
    
    filename = "concurrent_write.txt"
    thread_count = 10
    write_events = []
    
    def worker(worker_id: int):
        # Perform synchronous writes, forcing them to queue up
        engine.write_file_sync(filename, f"Line {worker_id}\n", mode="a")

    threads = []
    for i in range(thread_count):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
        
    engine.shutdown()

    # Read output and verify all lines are recorded securely without interleaving corruption
    filepath = os.path.join(TEMP_TEST_DIR, filename)
    with open(filepath, "r") as f:
        lines = f.readlines()
        
    assert len(lines) == thread_count
    # Ensure they are unique
    assert len(set(lines)) == thread_count


def test_handoff_validation_logic():
    engine = MemoryEngine(TEMP_TEST_DIR)
    
    valid_handoff = {
        "attempted_solutions": [
            {"description": "Tried patching core/wammr/router.py", "result": "Import error", "timestamp": "2026-07-13T00:00:00Z"}
        ],
        "file_diffs": {
            "core/wammr/router.py": "-import time\n+import time\n+import os"
        },
        "lint_output": "No errors found",
        "repl_vars": {
            "retries": "3"
        },
        "advisor_validation": {
            "validated": True,
            "advisor_id": "advisor-01",
            "timestamp": "2026-07-13T00:05:00Z",
            "notes": "State transitions verified"
        }
    }
    
    # Test valid handoff
    assert engine.validate_handoff(valid_handoff) is True
    
    # Test validation failure when Advisor has not validated
    invalid_validation_state = valid_handoff.copy()
    invalid_validation_state["advisor_validation"] = {
        "validated": False,
        "advisor_id": "advisor-01",
        "timestamp": "2026-07-13T00:05:00Z"
    }
    assert engine.validate_handoff(invalid_validation_state) is False

    # Test validation failure when fields are missing
    incomplete_handoff = valid_handoff.copy()
    del incomplete_handoff["attempted_solutions"]
    assert engine.validate_handoff(incomplete_handoff) is False
    
    # Test saving state
    filename = "handoff_state.json"
    save_success = engine.save_handoff_state(filename, valid_handoff)
    assert save_success is True
    
    filepath = os.path.join(TEMP_TEST_DIR, filename)
    assert os.path.exists(filepath)
    
    engine.shutdown()
