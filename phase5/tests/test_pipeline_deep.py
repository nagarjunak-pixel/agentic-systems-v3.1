"""Targeted tests to lift phase5/media/pipeline.py coverage (was 28%)."""
import sys
sys.path.insert(0, "/Users/venkataswaraswamy/Desktop/agentic_core/phase0")
sys.path.insert(0, "/Users/venkataswaraswamy/Desktop/agentic_core/phase1")
sys.path.insert(0, "/Users/venkataswaraswamy/Desktop/agentic_core/phase2")

from media.pipeline import MediaSynthesisPipeline


class FakeRouter:
    def complete(self, *a, **k): return "ok"
class FakeGuardrails:
    def check_output(self, *a, **k): return (True, {"allowed": True})
class FakeBudget:
    def __init__(self): self.recorded = []
    def check_budget(self, *a, **k): pass
    def record_usage(self, *a, **k): self.recorded.append(a)
class FakeWMG:
    def __init__(self): self.sent = []
    def dispatch_outgoing_message(self, connection_id, recipient, message_text):
        self.sent.append(message_text)


def _make_pipeline():
    return MediaSynthesisPipeline(
        model_router=FakeRouter(),
        guardrail_checker=FakeGuardrails(),
        budget_manager=FakeBudget(),
        wmg_gateway=FakeWMG(),
        mock=True,
    )


STORYBOARD = [{"frame": 1, "visual": "intro", "audio": "hello"}]
NARRATION = "Short promo narration text."
BLUEPRINT = {
    "coordinates": [0.1, 0.2, 0.8, 0.9],
    "layout": "split-screen",
    "aspect_ratio": "16:9",
    "weathering": "clean",
}
POSE = {
    "nose": [0.5, 0.2],
    "left_shoulder": [0.4, 0.35], "right_shoulder": [0.6, 0.35],
    "left_hip": [0.4, 0.6], "right_hip": [0.6, 0.6],
    "left_ankle": [0.4, 0.9], "right_ankle": [0.6, 0.9],
}


def test_full_pipeline_runs_offline_and_returns_manifest():
    p = _make_pipeline()
    manifest = p.run_pipeline(STORYBOARD, NARRATION, BLUEPRINT, skeleton_pose_data=POSE)
    assert "media_files" in manifest
    assert "final_video_url" in manifest
    assert "c2pa_provenance" in manifest
    assert manifest["c2pa_provenance"]["cryptographic_signature"]
    assert manifest["threejs_render_task_id"]
    assert p.wmg_gateway.sent  # completion hook dispatched


def test_pipeline_rejects_bad_coordinates():
    p = _make_pipeline()
    bad_bp = dict(BLUEPRINT); bad_bp["coordinates"] = [0.1, 0.2, 1.5, 0.9]  # x2 > 1.0
    try:
        p.run_pipeline(STORYBOARD, NARRATION, bad_bp)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Coordinate" in str(e)


def test_pipeline_rejects_bad_pose():
    p = _make_pipeline()
    bad_pose = {"hip": [0.5, 0.5], "shoulder": [1.2, 0.4]}  # > 1.0
    try:
        p.run_pipeline(STORYBOARD, NARRATION, BLUEPRINT, skeleton_pose_data=bad_pose)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Skeleton" in str(e)


def test_pipeline_budget_recorded():
    p = _make_pipeline()
    p.run_pipeline(STORYBOARD, NARRATION, BLUEPRINT)
    assert p.budget_manager.recorded  # usage recorded after run
