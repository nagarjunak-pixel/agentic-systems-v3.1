import pytest
from media.synthesizer.blueprint_mapper import map_blueprint_to_comfy_payload
from media.synthesizer.comfy_client import ComfyUIClient
from media.synthesizer.renderer_stub import ThreeJSRendererStub

def test_map_blueprint_to_comfy_payload():
    storyboard = [
        {"frame": 1, "visual": "Intro title card", "audio": "Welcome to our product"},
        {"frame": 2, "visual": "Split screen layout showing features", "audio": "Here are our key benefits"}
    ]
    narration = "Welcome to our product. Here are our key benefits."
    blueprint = {
        "layout": "split-screen",
        "aspect_ratio": "9:16",
        "coordinates": [0.15, 0.25, 0.85, 0.75],
        "weathering": "dusty"
    }

    payload = map_blueprint_to_comfy_payload(storyboard, narration, blueprint)
    
    assert "prompt" in payload
    nodes = payload["prompt"]
    
    # KSampler node
    assert nodes["3"]["class_type"] == "KSampler"
    # Aspect ratio mapping: 9:16 should produce width 576, height 1024
    assert nodes["5"]["inputs"]["width"] == 576
    assert nodes["5"]["inputs"]["height"] == 1024
    assert nodes["5"]["inputs"]["batch_size"] == 2
    
    # Prompt text should contain weathering, layout and bounding boxes
    positive_text = nodes["6"]["inputs"]["text"]
    assert "dusty" in positive_text
    assert "split-screen" in positive_text
    assert "[0.15, 0.25 to 0.85, 0.75]" in positive_text

def test_comfyui_client_mock():
    client = ComfyUIClient(mock=True)
    storyboard = [{"frame": 1, "visual": "Scene 1"}]
    narration = "Narration 1"
    blueprint = {"layout": "default", "aspect_ratio": "16:9", "coordinates": [0.0, 0.0, 1.0, 1.0]}
    
    prompt_id = client.submit_job(storyboard, narration, blueprint)
    assert prompt_id.startswith("mock_prompt_")
    
    poll_res = client.poll_job(prompt_id)
    assert poll_res["completed"] is True
    
    manifest = client.download_result(prompt_id, poll_res)
    assert manifest["prompt_id"] == prompt_id
    assert len(manifest["media_files"]) == 2
    assert manifest["media_files"][0]["filename"] == "brandstream_frame_1.png"
    assert manifest["media_files"][1]["filename"] == "brandstream_frame_2.png"

def test_threejs_renderer_stub():
    renderer = ThreeJSRendererStub()
    blueprint = {"layout": "carousel", "aspect_ratio": "1:1"}
    coords = [0.1, 0.1, 0.9, 0.9]
    
    task_id = renderer.render_transitions(blueprint, coords)
    assert task_id.startswith("render_task_")
    
    status = renderer.get_render_status(task_id)
    assert status["status"] == "COMPLETED"
    assert "output_metadata" in status
    assert status["output_metadata"]["hyperframe_arc_motion"] is True
    
    with pytest.raises(ValueError):
        renderer.render_transitions(blueprint, [0.1, 0.2]) # invalid coords len
