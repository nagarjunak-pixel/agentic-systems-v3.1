import pytest
from brandstream.audit.auditor import CopyAuditor, ChessValidator, LogicStateValidator

def test_copy_auditor():
    auditor = CopyAuditor(max_words=10, max_frames=3)
    
    # 1. Compliant copy
    valid_data = {
        "narration": "Hello world, this copy is very short.", # 7 words
        "storyboard": [
            {"frame": 1, "visual": "Intro", "audio": "Hello"},
            {"frame": 2, "visual": "Outro", "audio": "World"}
        ]
    }
    report = auditor.audit_copy(valid_data)
    assert report["valid"] is True
    assert len(report["errors"]) == 0
    
    # 2. Exceeds max words
    invalid_words_data = {
        "narration": "This is a much longer sentence that will definitely exceed the word limit of ten words.", # 16 words
        "storyboard": [
            {"frame": 1, "visual": "Intro", "audio": "Hello"}
        ]
    }
    report_words = auditor.audit_copy(invalid_words_data)
    assert report_words["valid"] is False
    assert any("word count" in err for err in report_words["errors"])

    # 3. Exceeds max frames
    invalid_frames_data = {
        "narration": "Short sentence.",
        "storyboard": [
            {"frame": 1, "visual": "A", "audio": "A"},
            {"frame": 2, "visual": "B", "audio": "B"},
            {"frame": 3, "visual": "C", "audio": "C"},
            {"frame": 4, "visual": "D", "audio": "D"} # Exceeds max_frames = 3
        ]
    }
    report_frames = auditor.audit_copy(invalid_frames_data)
    assert report_frames["valid"] is False
    assert any("exceeds the limit" in err for err in report_frames["errors"])

def test_chess_validator():
    validator = ChessValidator()
    
    # 1. Valid move sequence (Ruy Lopez opening)
    valid_moves = ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    is_valid, msg = validator.validate_moves(valid_moves)
    assert is_valid is True
    
    # 2. Invalid move sequence (repeated turn / double pawn move e4 by white immediately)
    invalid_moves = ["e4", "e4"]
    is_valid_bad, msg_bad = validator.validate_moves(invalid_moves)
    assert is_valid_bad is False
    assert "Illegal move" in msg_bad or "already occupied" in msg_bad or "repeated consecutively" in msg_bad

    # 3. Invalid notation format
    invalid_notation = ["e4", "invalid_move_format"]
    is_valid_notation, msg_notation = validator.validate_moves(invalid_notation)
    assert is_valid_notation is False
    assert "Invalid move notation" in msg_notation or "Could not determine target square" in msg_notation

def test_logic_state_validator_spatial_blueprint():
    validator = LogicStateValidator()
    
    # 1. Valid blueprint
    valid_bp = {"coordinates": [0.1, 0.2, 0.8, 0.5]}
    ok, msg = validator.validate_spatial_blueprint(valid_bp)
    assert ok is True
    
    # 2. Out of bounds coordinates
    invalid_bounds_bp = {"coordinates": [-0.1, 0.2, 1.2, 0.5]}
    ok_bounds, msg_bounds = validator.validate_spatial_blueprint(invalid_bounds_bp)
    assert ok_bounds is False
    assert "out of bounds" in msg_bounds.lower()
    
    # 3. Invalid widths/heights (x1 >= x2)
    invalid_order_bp = {"coordinates": [0.8, 0.2, 0.1, 0.5]}
    ok_order, msg_order = validator.validate_spatial_blueprint(invalid_order_bp)
    assert ok_order is False
    assert "width" in msg_order.lower() or "height" in msg_order.lower()

def test_logic_state_validator_storyboard_sequence():
    validator = LogicStateValidator()
    
    # 1. Valid sequence
    valid_seq = [
        {"frame": 1, "visual": "V1"},
        {"frame": 2, "visual": "V2"}
    ]
    ok, msg = validator.validate_storyboard_sequence(valid_seq)
    assert ok is True
    
    # 2. Invalid frame numbers (unordered / missing)
    invalid_seq = [
        {"frame": 1, "visual": "V1"},
        {"frame": 3, "visual": "V2"}
    ]
    ok_bad, msg_bad = validator.validate_storyboard_sequence(invalid_seq)
    assert ok_bad is False
    assert "expected frame 2" in msg_bad.lower()
