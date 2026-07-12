from typing import Dict, Any, List

def map_blueprint_to_comfy_payload(
    storyboard: List[Dict[str, Any]],
    narration: str,
    blueprint: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Maps Phase 4 visual_blueprint specifications and storyboard details
    into a structured ComfyUI API node-graph payload.
    """
    ar = blueprint.get("aspect_ratio", "16:9")
    if ar == "16:9":
        width, height = 1024, 576
    elif ar == "9:16":
        width, height = 576, 1024
    elif ar == "1:1":
        width, height = 1024, 1024
    else:
        # Custom aspect ratios or default fallback
        width, height = 1024, 576

    layout = blueprint.get("layout", "default")
    coords = blueprint.get("coordinates", [0.0, 0.0, 1.0, 1.0])
    weathering = blueprint.get("weathering", "none")

    # Format weathering and layout parameters for prompting
    weathering_str = f" with weathering effect: {weathering}" if weathering and weathering != "none" else ""
    layout_str = f" composition: {layout}" if layout and layout != "default" else ""
    coords_str = f" bounding box bounds: [{coords[0]}, {coords[1]} to {coords[2]}, {coords[3]}]" if coords else ""

    # Generate node prompting content
    positive_prompt = (
        f"Promo media synthesis. Narration audio overlay: '{narration}'. "
        f"Storyboard instructions: {json_storyboard_summary(storyboard)}."
        f"{weathering_str}{layout_str}{coords_str}"
    )

    # Output formatted ComfyUI Node Graph structure
    payload = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 101,
                "steps": 25,
                "cfg": 8.0,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "sd_xl_base_1.0.safetensors"
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": len(storyboard) if storyboard else 1
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive_prompt,
                "clip": ["4", 1]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry, low contrast, text watermark, extra limbs, bad anatomy, deformed",
                "clip": ["4", 1]
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "brandstream_synthesized_media",
                "images": ["8", 0]
            }
        }
    }
    return {"prompt": payload}

def json_storyboard_summary(storyboard: List[Dict[str, Any]]) -> str:
    """Helper to convert storyboard description into a single prompt string."""
    frames_desc = []
    for f in storyboard:
        frame_num = f.get("frame", 0)
        visual = f.get("visual", "")
        frames_desc.append(f"Frame {frame_num}: {visual}")
    return " | ".join(frames_desc)
