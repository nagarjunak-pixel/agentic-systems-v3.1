import os
import time
import json
import logging
import asyncio
from typing import Dict, Any, Callable, Optional, List

# Core imports (using standard sys.path mapping in phase6)
from core.wammr.router import ModelRouter
from abtm.budget import BudgetManager

logger = logging.getLogger("BrandStream.VoiceDelegationController")

class VoiceDelegationController:
    """
    Coordinates real-time voice turns with background reasoning and frontend UI generation.
    - Emits progress tokens (V028) if reasoning takes longer than 3 seconds.
    - Generates dynamic UI cards for rendering on client frontends.
    """
    def __init__(self, model_router: ModelRouter, budget_manager: BudgetManager):
        self.model_router = model_router
        self.budget_manager = budget_manager

    async def execute_reasoning_with_progress(
        self,
        prompt: str,
        websocket_send_callback: Callable[[Dict[str, Any]], Any],
        reasoning_delay: float = 0.0
    ) -> str:
        """
        Executes reasoning using the ModelRouter.
        Concurrently runs a progress token monitor. If processing exceeds 3.0s,
        progressive tokens are emitted to keep the user engaged (V028).
        """
        logger.info(f"Delegating reasoning for prompt: '{prompt}' (delay: {reasoning_delay}s)")
        
        async def progress_emitter():
            try:
                # Wait 3 seconds before starting progress notifications
                await asyncio.sleep(3.0)
                progress_stages = [
                    "thinking...",
                    "accessing knowledge base...",
                    "generating localized variants...",
                    "finalizing voice output..."
                ]
                for stage in progress_stages:
                    await websocket_send_callback({
                        "type": "progress",
                        "token": stage,
                        "timestamp": time.time()
                    })
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                # Normal termination when reasoning completes before all tokens are sent
                pass

        # Start the background progress emitter
        progress_task = asyncio.create_task(progress_emitter())
        
        try:
            # Simulate heavy database lookup or reasoning delay if requested
            if reasoning_delay > 0:
                await asyncio.sleep(reasoning_delay)
                
            # Wrap the ModelRouter call in ABTM budget checks and token recording
            # Note: wrap_router_call is synchronous, so we run it in executor to avoid blocking the loop
            loop = asyncio.get_running_loop()
            response_text = await loop.run_in_executor(
                None,
                self.budget_manager.wrap_router_call,
                self.model_router,
                "voice_delegation",
                "voice_realtime",
                prompt
            )
            return response_text
        finally:
            # Always ensure the progress task is terminated
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

    def generate_ui_card(self, card_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produces structured JSON cards (product recap, poll, media_preview, etc.)
        for the client frontend to render.
        """
        logger.info(f"Generating UI Card for type: {card_type}")
        
        card_schemas = {
            "product_recap": {
                "required": ["product_name", "price", "description"],
                "default": {
                    "product_name": "Unknown Product",
                    "price": "$0.00",
                    "description": "No description available"
                }
            },
            "poll": {
                "required": ["question", "options"],
                "default": {
                    "question": "What do you think?",
                    "options": ["Yes", "No"]
                }
            },
            "media_preview": {
                "required": ["media_url", "aspect_ratio", "c2pa_signature"],
                "default": {
                    "media_url": "",
                    "aspect_ratio": "16:9",
                    "c2pa_signature": ""
                }
            }
        }
        
        schema = card_schemas.get(card_type)
        if not schema:
            # Generic/custom card fallback
            return {
                "card_type": card_type,
                "schema_version": "1.0",
                "data": data,
                "timestamp": time.time()
            }
            
        # Clean and apply defaults for missing required keys
        cleaned_data = {}
        for key in schema["required"]:
            cleaned_data[key] = data.get(key, schema["default"][key])
            
        # Add any other payload keys that might be relevant
        for k, v in data.items():
            if k not in cleaned_data:
                cleaned_data[k] = v
                
        return {
            "card_type": card_type,
            "schema_version": "1.0",
            "title": card_type.replace("_", " ").title(),
            "data": cleaned_data,
            "timestamp": time.time()
        }
