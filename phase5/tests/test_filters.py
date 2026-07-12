import pytest
from media.filters.skeleton_filter import SkeletonFilter
from media.filters.reid_filter import ReIDFilter
from media.filters.watermark import C2PAWatermarkEmbedder

def test_skeleton_filter():
    sf = SkeletonFilter()
    
    # 1. Coordinate bounds validation
    valid_coords = [0.1, 0.2, 0.8, 0.9]
    ok, msg = sf.validate_coordinates(valid_coords)
    assert ok is True
    
    invalid_coords = [1.2, 0.2, 0.8, 0.9]
    ok, msg = sf.validate_coordinates(invalid_coords)
    assert ok is False
    assert "out of bounds" in msg.lower()
    
    invalid_box = [0.8, 0.2, 0.1, 0.9] # x1 >= x2
    ok, msg = sf.validate_coordinates(invalid_box)
    assert ok is False
    assert "layout width" in msg.lower()

    # 2. Pose anatomical checks
    plausible_pose = {
        "nose": [0.5, 0.1],
        "left_shoulder": [0.4, 0.3],
        "right_shoulder": [0.6, 0.3],
        "left_hip": [0.4, 0.6],
        "right_hip": [0.6, 0.6],
        "left_ankle": [0.4, 0.9],
        "right_ankle": [0.6, 0.9]
    }
    ok_pose, msg_pose = sf.validate_pose_plausibility(plausible_pose)
    assert ok_pose is True
    
    implausible_pose = plausible_pose.copy()
    implausible_pose["nose"] = [0.5, 0.4] # nose y is below shoulder y (0.3)
    ok_pose, msg_pose = sf.validate_pose_plausibility(implausible_pose)
    assert ok_pose is False
    assert "head" in msg_pose.lower()

def test_reid_filter_deduplication():
    rf = ReIDFilter()
    
    frames = [
        {"frame_index": 1, "visual_description": "A close up of a coffee cup"},
        {"frame_index": 2, "visual_description": "A close up of a coffee cup"}, # Duplicate description
        {"frame_index": 3, "visual_description": "A wide shot of a coffee shop"}
    ]
    
    deduped = rf.deduplicate_frames(frames)
    assert len(deduped) == 2
    assert deduped[0]["frame_index"] == 1
    assert deduped[1]["frame_index"] == 3

def test_reid_skeleton_swap_correction():
    rf = ReIDFilter()
    
    # 2 actors crossing. Original tracking features:
    # Actor 1 has feature vector [1.0, 0.0]
    # Actor 2 has feature vector [0.0, 1.0]
    prev_skeletons = [
        {"id": 1, "coordinates": [0.1, 0.2, 0.3, 0.4], "visual_feature_descriptor": [1.0, 0.0]},
        {"id": 2, "coordinates": [0.7, 0.2, 0.9, 0.4], "visual_feature_descriptor": [0.0, 1.0]}
    ]
    
    # After crossing, the raw tracker swaps them because coordinates crossed,
    # but their visual feature descriptors are bound to the visual frame:
    # Actor 1 features are now at coordinates of current ID 2, and vice versa.
    curr_skeletons_swapped = [
        {"id": 1, "coordinates": [0.75, 0.2, 0.95, 0.4], "visual_feature_descriptor": [0.0, 1.0]}, # Swapped: features map to prev ID 2
        {"id": 2, "coordinates": [0.15, 0.2, 0.35, 0.4], "visual_feature_descriptor": [1.0, 0.0]}  # Swapped: features map to prev ID 1
    ]
    
    swap_detected, corrected = rf.detect_skeleton_swap(prev_skeletons, curr_skeletons_swapped)
    assert swap_detected is True
    
    # Check that corrected identities were restored:
    # Current ID 1 (visual [0.0, 1.0]) should be mapped to original ID 2
    # Current ID 2 (visual [1.0, 0.0]) should be mapped to original ID 1
    corrected_map = {s["id"]: s for s in corrected}
    assert corrected_map[1]["visual_feature_descriptor"] == [1.0, 0.0]
    assert corrected_map[2]["visual_feature_descriptor"] == [0.0, 1.0]

def test_c2pa_watermark_embedder():
    embedder = C2PAWatermarkEmbedder(signer_name="Test Signer")
    
    manifest = {
        "prompt_id": "test_id",
        "media_files": [
            {"filename": "frame_1.png", "size_bytes": 100},
            {"filename": "frame_2.png", "size_bytes": 200}
        ]
    }
    
    watermarked = embedder.embed_watermark(manifest, {"campaign": "test"})
    assert "c2pa_provenance" in watermarked
    c2pa = watermarked["c2pa_provenance"]
    assert c2pa["signer"] == "Test Signer"
    assert c2pa["c2pa_version"] == "1.3"
    assert "combined_asset_hash" in c2pa["assertions"]
    assert c2pa["assertions"]["actions"][0]["parameters"]["campaign"] == "test"
    assert c2pa["cryptographic_signature"].startswith("sha256WithRSAEncryption:sig:")
