import os
import time
import logging
from typing import Dict, Any, List, Optional

# Core Imports (Phase 0, 1, 2)
from core.wammr.router import ModelRouter
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.gateway import WebhookMessagingGateway

# Synthesizer, Transcoder, Filters (Phase 5)
from media.synthesizer.comfy_client import ComfyUIClient
from media.synthesizer.renderer_stub import ThreeJSRendererStub
from media.transcode.transcode_client import TranscodeClient
from media.filters.skeleton_filter import SkeletonFilter
from media.filters.reid_filter import ReIDFilter
from media.filters.watermark import C2PAWatermarkEmbedder

logger = logging.getLogger("BrandStream.MediaSynthesisPipeline")

class MediaSynthesisPipeline:
    """
    Main coordinator implementing full BrandStream Phase 5 pipeline.
    Chains together:
      Phase 4 inputs -> ComfyUI Synthesizer -> Skeleton/ReID Filters -> Transcoding Egress -> C2PA Provenance.
    Wired directly with ModelRouter, Safety Gatekeeper (AISG), ABTM Budgeting, and WMG messaging.
    """
    def __init__(
        self,
        model_router: ModelRouter,
        guardrail_checker: GuardrailChecker,
        budget_manager: BudgetManager,
        wmg_gateway: WebhookMessagingGateway,
        connection_id: str = "brandstream_publish_conn",
        mock: bool = True
    ):
        self.model_router = model_router
        self.guardrail_checker = guardrail_checker
        self.budget_manager = budget_manager
        self.wmg_gateway = wmg_gateway
        self.connection_id = connection_id
        
        # Initialize Synthesizer components
        self.comfy_client = ComfyUIClient(mock=mock)
        self.renderer_stub = ThreeJSRendererStub()
        
        # Initialize Transcoder client
        self.transcode_client = TranscodeClient(mock=mock)
        
        # Initialize filters
        self.skeleton_filter = SkeletonFilter()
        self.reid_filter = ReIDFilter()
        self.watermark_embedder = C2PAWatermarkEmbedder()

    def run_pipeline(
        self,
        storyboard: List[Dict[str, Any]],
        narration: str,
        visual_blueprint: Dict[str, Any],
        skeleton_pose_data: Optional[Dict[str, List[float]]] = None,
        recipient_channel: str = "operator_channel"
    ) -> Dict[str, Any]:
        """
        Executes full offline/online media synthesis loop.
        """
        logger.info("Executing BrandStream Media Synthesis Pipeline...")
        
        # 1. Budget Verification via ABTM (Verify before generating anything)
        # Assume media synthesis logic calls ModelRouter to optimize style prompt structure
        est_tokens = max(1, len(narration) // 4 + 100)
        self.budget_manager.check_budget("synthesizer", est_tokens)
        
        # 2. Pre-synthesis Filter & Coordinate Verification (Skeleton/OpenPose Bounds)
        coords = visual_blueprint.get("coordinates", [0.0, 0.0, 1.0, 1.0])
        valid_coords, coord_msg = self.skeleton_filter.validate_coordinates(coords)
        if not valid_coords:
            raise ValueError(f"Coordinate validation failed: {coord_msg}")
            
        if skeleton_pose_data:
            valid_pose, pose_msg = self.skeleton_filter.validate_pose_plausibility(skeleton_pose_data)
            if not valid_pose:
                raise ValueError(f"Skeleton pose validation failed: {pose_msg}")

        # 3. ComfyUI Media Synthesis Execution
        prompt_id = self.comfy_client.submit_job(storyboard, narration, visual_blueprint)
        poll_res = self.comfy_client.poll_job(prompt_id)
        raw_manifest = self.comfy_client.download_result(prompt_id, poll_res)

        # 4. Post-check Generated Media Content & Text overlay Metadata using Safety Gatekeeper (AISG)
        # We assert the prompt overlay content is clean
        allowed, safety_verdict = self.guardrail_checker.check_output("sdxl", narration)
        if not allowed:
            raise ValueError(f"Safety Gatekeeper flagged synthesized metadata: {safety_verdict}")

        # 5. Spatial Bounding Box & Re-ID Deduplication / Swap Correction
        # Frame deduplication
        deduped_frames = self.reid_filter.deduplicate_frames(raw_manifest.get("media_files", []))
        raw_manifest["media_files"] = deduped_frames
        
        # Simulate Three.js/GSAP rendering transition registration
        render_task = self.renderer_stub.render_transitions(visual_blueprint, coords)
        raw_manifest["threejs_render_task_id"] = render_task

        # 6. Offloaded Media Transcode & Composition
        input_urls = [f.get("url") for f in deduped_frames if f.get("url")]
        job_id = self.transcode_client.submit_transcode_job(
            input_media_urls=input_urls,
            output_bucket="brandstream-egress",
            resolution=visual_blueprint.get("aspect_ratio", "16:9")
        )
        transcode_status = self.transcode_client.get_job_status(job_id)
        
        # Set output video details in the final manifest
        final_video_url = transcode_status.get("output_url", "")
        raw_manifest["final_video_url"] = final_video_url
        raw_manifest["transcode_job_id"] = job_id
        
        # 7. Tamper-resistant Cryptographic Provenance Watermarking (C2PA)
        final_manifest = self.watermark_embedder.embed_watermark(raw_manifest, {
            "layout": visual_blueprint.get("layout"),
            "aspect_ratio": visual_blueprint.get("aspect_ratio"),
            "weathering": visual_blueprint.get("weathering")
        })

        # Register token usage completion on ABTM
        self.budget_manager.record_usage("synthesizer", est_tokens)

        # 8. Egress dispatch / Hook Notification using WMG
        message_text = (
            f"BrandStream campaign synthesis complete! "
            f"Video Output: {final_video_url} "
            f"C2PA Provenance Signature: {final_manifest['c2pa_provenance']['cryptographic_signature'][:24]}..."
        )
        try:
            self.wmg_gateway.dispatch_outgoing_message(
                connection_id=self.connection_id,
                recipient=recipient_channel,
                message_text=message_text
            )
            logger.info("WMG dispatched synthesis completion hook notification successfully.")
        except Exception as e:
            logger.warning(f"WMG delivery hook message dispatch failed: {e}")

        return final_manifest
