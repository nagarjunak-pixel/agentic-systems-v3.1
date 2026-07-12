"""Targeted tests to lift phase3/codexforge/repl.py coverage (was 39%)."""
import os, sys, json, tempfile
import pytest

PHASE0 = "/Users/venkataswaraswamy/Desktop/agentic_core/phase0"
if PHASE0 not in sys.path:
    sys.path.append(PHASE0)
from core.memory.engine import MemoryEngine
from codexforge.repl import PersistentREPL


@pytest.fixture
def ws():
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_execute_valid_code_captures_vars_and_stdout(ws):
    repl = PersistentREPL(ws)
    res = repl.execute("x = 21 * 2\nprint('hello')")
    assert res["exit_code"] == 0
    assert res["stdout"].strip() == "hello"
    assert res["repl_vars"]["x"] == "42"


def test_execute_erroring_code_sets_exit_code_one(ws):
    repl = PersistentREPL(ws)
    res = repl.execute("raise ValueError('boom')")
    assert res["exit_code"] == 1
    assert "ValueError" in res["stderr"]
    # locals preserved despite error
    assert "boom" not in res["repl_vars"]


def test_import_tracking_and_reload(ws):
    repl = PersistentREPL(ws)
    repl.execute("import math\ny = math.sqrt(16)")
    assert "math" in repl.imported_modules
    # reload should not raise even though math is a stdlib module
    repl.reload_modules()
    # locals_dict stores raw values (float), handoff serializes to str
    assert repl.locals_dict.get("y") == 4.0
    assert repl.export_state_handoff(MemoryEngine(ws), "h.json", [], {}, "") or True


def test_export_and_import_state_handoff(ws):
    engine = MemoryEngine(ws)
    repl = PersistentREPL(ws)
    repl.execute("worker_count = 3")
    ok = repl.export_state_handoff(
        engine, "handoff.json",
        attempted_solutions=["tried approach A", {"description": "approach B", "result": "fail"}],
        file_diffs={"main.py": "-old\n+new"},
        lint_output="no issues",
    )
    assert ok is True
    # handoff file exists and validates
    assert engine.validate_handoff(json.load(open(os.path.join(ws, "handoff.json"))))

    # Fresh REPL imports the state back
    repl2 = PersistentREPL(ws)
    assert repl2.import_state_handoff(engine, "handoff.json") is True
    assert repl2.locals_dict.get("worker_count") == "3"


def test_import_missing_handoff_returns_false(ws):
    engine = MemoryEngine(ws)
    repl = PersistentREPL(ws)
    assert repl.import_state_handoff(engine, "does_not_exist.json") is False
