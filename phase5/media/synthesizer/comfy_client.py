import os
import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional
from media.synthesizer.blueprint_mapper import map_blueprint_to_comfy_payload

logger = logging.getLogger("BrandStream.ComfyUIClient")

class ComfyUIClient:
    """
    ComfyUI API Client (HTTP) that handles prompt construction, job submission,
    polling of queue status, and output manifest retrieval.
    Includes high-fidelity Mock Mode to run without active GPU server.
    """
    def __init__(self, base_url: str = "http://localhost:8188", mock: Optional[bool] = None):
        self.base_url = base_url.rstrip("/")
        # Auto-configure mock mode based on env or manual override
        if mock is not None:
            self.mock = mock
        else:
            self.mock = os.getenv("COMFYUI_MOCK", "true").lower() in ("true", "1", "yes")
            
        logger.info(f"Initialized ComfyUI API Client. Host: {self.base_url}, Mock Mode: {self.mock}")

    def submit_job(
        self,
        storyboard: List[Dict[str, Any]],
        narration: str,
        visual_blueprint: Dict[str, Any]
    ) -> str:
        """
        Submits storyboard, narration, and layout parameters to ComfyUI.
        Returns the prompt ID (Job Queue ID).
        """
        # Map Phase 4 blueprint into ComfyUI prompt payload format
        payload = map_blueprint_to_comfy_payload(storyboard, narration, visual_blueprint)
        
        if self.mock:
            prompt_id = f"mock_prompt_{int(time.time())}"
            logger.info(f"[Mock Mode] Submitted media synthesis job. Generated Prompt ID: {prompt_id}")
            return prompt_id

        # Real HTTP connection
        try:
            url = f"{self.base_url}/prompt"
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            res_data = response.json()
            prompt_id = res_data.get("prompt_id")
            if not prompt_id:
                raise ValueError("ComfyUI response did not return a prompt_id.")
            logger.info(f"Submitted job to ComfyUI. Prompt ID: {prompt_id}")
            return prompt_id
        except Exception as e:
            logger.error(f"Failed to submit ComfyUI job: {e}")
            raise

    def poll_job(self, prompt_id: str, timeout_seconds: int = 10, poll_interval: float = 0.5) -> Dict[str, Any]:
        """
        Polls the ComfyUI server for prompt history/status until completion or timeout.
        Returns the history manifest block if completed, or throws.
        """
        if self.mock:
            logger.info(f"[Mock Mode] Polling Prompt ID {prompt_id} - completed instantly.")
            return {"status": "SUCCESS", "completed": True, "prompt_id": prompt_id}

        start_time = time.time()
        url = f"{self.base_url}/history/{prompt_id}"
        
        while time.time() - start_time < timeout_seconds:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    history = response.json()
                    # ComfyUI history returns an object keyed by prompt_id when done
                    if prompt_id in history:
                        logger.info(f"ComfyUI Job {prompt_id} completed successfully.")
                        return {
                            "status": "SUCCESS",
                            "completed": True,
                            "prompt_id": prompt_id,
                            "history": history[prompt_id]
                        }
                time.sleep(poll_interval)
            except Exception as e:
                logger.warning(f"Error polling ComfyUI status: {e}")
                time.sleep(poll_interval)
                
        raise TimeoutError(f"ComfyUI job {prompt_id} did not complete within {timeout_seconds} seconds.")

    def download_result(self, prompt_id: str, history_manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieves the output image/video manifest details from ComfyUI execution.
        In Mock mode, returns a high-fidelity stub manifest with mock file locations.
        """
        if self.mock:
            # High-fidelity stub manifest aligning with what Phase 6 consumes
            return {
                "prompt_id": prompt_id,
                "media_files": [
                    {
                        "filename": "brandstream_frame_1.png",
                        "size_bytes": 1048576,
                        "width": 1024,
                        "height": 576,
                        "type": "image/png",
                        "url": f"{self.base_url}/view?filename=brandstream_frame_1.png&type=output",
                        "visual_description": "Intro title card splash"
                    },
                    {
                        "filename": "brandstream_frame_2.png",
                        "size_bytes": 1084200,
                        "width": 1024,
                        "height": 576,
                        "type": "image/png",
                        "url": f"{self.base_url}/view?filename=brandstream_frame_2.png&type=output",
                        "visual_description": "Product dashboard detail overview"
                    }
                ],
                "synthesis_metadata": {
                    "sampler": "dpmpp_2m",
                    "steps": 25,
                    "engine": "ComfyUI/SDXL-Flux",
                    "timestamp": time.time()
                }
            }

        # Real mode parser
        if not history_manifest or "history" not in history_manifest:
            raise ValueError("History manifest is required to download/locate outputs in real mode.")
            
        outputs = history_manifest["history"].get("outputs", {})
        media_files = []
        
        # Traverse outputs to extract file information
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img in node_output["images"]:
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "")
                    img_type = img.get("type", "output")
                    
                    media_files.append({
                        "filename": filename,
                        "type": f"image/{img.get('format', 'png')}",
                        "url": f"{self.base_url}/view?filename={filename}&subfolder={subfolder}&type={img_type}"
                    })
                    
        return {
            "prompt_id": prompt_id,
            "media_files": media_files,
            "synthesis_metadata": {
                "engine": "ComfyUI",
                "timestamp": time.time(),
                "node_outputs": list(outputs.keys())
            }
        }
