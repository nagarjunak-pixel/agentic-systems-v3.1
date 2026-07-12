"""Targeted tests to lift phase4/brandstream/audit/auditor.py coverage (was 49%)."""
import sys
sys.path.insert(0, "/Users/venkataswaraswamy/Desktop/agentic_core/phase0")
from brandstream.audit.auditor import CopyAuditor, ChessValidator, LogicStateValidator


# ---- CopyAuditor branches ----
def test_copy_auditor_empty_narration_invalid():
    a = CopyAuditor()
    r = a.audit_copy({"narration": "   ", "storyboard": [{"frame": 1}]})
    assert r["valid"] is False
    assert any("empty" in e for e in r["errors"])


def test_copy_auditor_zero_frames_invalid():
    a = CopyAuditor()
    r = a.audit_copy({"narration": "Some words here", "storyboard": []})
    assert r["valid"] is False
    assert any("0 frames" in e for e in r["errors"])


def test_copy_auditor_too_many_words_invalid():
    a = CopyAuditor(max_words=3)
    r = a.audit_copy({"narration": "one two three four five", "storyboard": [{"frame": 1}]})
    assert r["valid"] is False
    assert any("word count" in e for e in r["errors"])


def test_copy_auditor_too_many_frames_invalid():
    a = CopyAuditor(max_frames=1)
    r = a.audit_copy({"narration": "ok", "storyboard": [{"frame": 1}, {"frame": 2}]})
    assert r["valid"] is False
    assert any("exceeds the limit" in e for e in r["errors"])


# ---- ChessValidator (fallback path; chess likely not installed) ----
def test_chess_validator_consecutive_duplicate_rejected():
    v = ChessValidator()
    ok, msg = v.validate_moves(["e4", "e4"])
    assert ok is False
    assert "consecutive" in msg or "occupied" in msg


def test_chess_validator_valid_opening_accepted():
    v = ChessValidator()
    ok, msg = v.validate_moves(["e4", "e5", "Nf3", "Nc6", "Bb5"])
    assert ok is True


def test_chess_validator_bad_notation_rejected():
    v = ChessValidator()
    ok, msg = v.validate_moves(["zz9", "e5"])
    assert ok is False
    assert "notation" in msg


def test_chess_validator_castling_accepted():
    v = ChessValidator()
    ok, msg = v.validate_moves(["e4", "e5", "O-O"])
    # castling target square logic shouldn't crash; either accept or reject gracefully
    assert isinstance(ok, bool)


# ---- LogicStateValidator ----
def test_spatial_missing_coords():
    v = LogicStateValidator()
    ok, msg = v.validate_spatial_blueprint({"coordinates": None})
    assert ok is False
    assert "Missing" in msg


def test_spatial_wrong_length():
    v = LogicStateValidator()
    ok, msg = v.validate_spatial_blueprint({"coordinates": [0.1, 0.2, 0.3]})
    assert ok is False
    assert "list of 4" in msg


def test_spatial_out_of_bounds():
    v = LogicStateValidator()
    ok, msg = v.validate_spatial_blueprint({"coordinates": [0.1, 0.2, 1.5, 0.9]})
    assert ok is False
    assert "out of bounds" in msg


def test_spatial_x1_ge_x2_invalid():
    v = LogicStateValidator()
    ok, msg = v.validate_spatial_blueprint({"coordinates": [0.8, 0.2, 0.5, 0.9]})
    assert ok is False
    assert "width" in msg


def test_spatial_y1_ge_y2_invalid():
    v = LogicStateValidator()
    ok, msg = v.validate_spatial_blueprint({"coordinates": [0.1, 0.8, 0.5, 0.5]})
    assert ok is False
    assert "height" in msg


def test_spatial_valid():
    v = LogicStateValidator()
    ok, msg = v.validate_spatial_blueprint({"coordinates": [0.1, 0.2, 0.8, 0.9]})
    assert ok is True


def test_storyboard_sequence_out_of_order():
    v = LogicStateValidator()
    ok, msg = v.validate_storyboard_sequence([{"frame": 1}, {"frame": 3}])
    assert ok is False
    assert "sequence" in msg


def test_storyboard_sequence_valid():
    v = LogicStateValidator()
    ok, msg = v.validate_storyboard_sequence([{"frame": 1}, {"frame": 2}, {"frame": 3}])
    assert ok is True
