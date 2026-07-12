import os
import time
import json
import logging
import asyncio
import websockets
from typing import Dict, Any, Optional, Set

# Core imports (using standard sys.path mapping in phase6)
from core.wammr.router import ModelRouter
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.gateway import WebhookMessagingGateway
from media.pipeline import MediaSynthesisPipeline

# Phase 6 imports
from voice.delegation.controller import VoiceDelegationController

logger = logging.getLogger("BrandStream.VoiceGatewayServer")

class VoiceGatewayServer:
    """
    Speech-to-Speech Voice Gateway (WebSocket server).
    - Accepts bidirectional audio frames and text.
    - Routes to TTS/STT pipelines (mock mode).
    - Detects interruptions and handles re-planning (V019).
    - Enforces sub-100ms latency targets.
    - Coordinates with delegation controller, safety, budget, WMG, and media pipelines.
    """
    def __init__(
        self,
        model_router: ModelRouter,
        guardrail_checker: GuardrailChecker,
        budget_manager: BudgetManager,
        wmg_gateway: WebhookMessagingGateway,
        delegation_controller: VoiceDelegationController,
        media_pipeline: Optional[MediaSynthesisPipeline] = None,
        host: str = "127.0.0.1",
        port: int = 8765,
        connection_id: str = "brandstream_publish_conn",
        latency_threshold_ms: float = 100.0,
        mock_mode: bool = True
    ):
        self.model_router = model_router
        self.guardrail_checker = guardrail_checker
        self.budget_manager = budget_manager
        self.wmg_gateway = wmg_gateway
        self.delegation_controller = delegation_controller
        self.media_pipeline = media_pipeline
        
        self.host = host
        self.port = port
        self.connection_id = connection_id
        self.latency_threshold_ms = latency_threshold_ms
        self.mock_mode = mock_mode
        
        self.server = None
        self.connections: Set[Any] = set()
        self.active_tasks: Dict[Any, asyncio.Task] = {}
        self.outbound_active: Dict[Any, bool] = {}

    async def start(self):
        """Starts the WebSocket server."""
        self.server = await websockets.serve(self.handler, self.host, self.port)
        logger.info(f"Voice Gateway WebSocket Server started on ws://{self.host}:{self.port}")

    async def stop(self):
        """Stops the WebSocket server."""
        if self.server:
            # Cancel all active tasks
            for conn, task in list(self.active_tasks.items()):
                task.cancel()
            self.server.close()
            await self.server.wait_closed()
            logger.info("Voice Gateway WebSocket Server stopped.")

    async def handler(self, websocket, path=None):
        """WebSocket connection handler."""
        self.connections.add(websocket)
        self.outbound_active[websocket] = False
        logger.info(f"Client connected: {websocket.remote_address}")
        
        try:
            async for message in websocket:
                try:
                    payload = json.loads(message)
                except ValueError:
                    # Treat binary or invalid JSON as mock raw audio frame
                    payload = {"type": "audio_frame", "audio_data": message}
                
                await self.process_message(websocket, payload)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client connection closed.")
        finally:
            self.connections.remove(websocket)
            if websocket in self.active_tasks:
                self.active_tasks[websocket].cancel()
                del self.active_tasks[websocket]
            if websocket in self.outbound_active:
                del self.outbound_active[websocket]

    async def process_message(self, websocket, payload: Dict[str, Any]):
        """Processes message frames and checks for interruption events."""
        msg_type = payload.get("type")
        
        # Check if user spoke/interrupted while agent was talking (outbound window active)
        if self.outbound_active.get(websocket, False):
            logger.warning("User spoke while agent was talking. Interruption detected! (V019)")
            
            # Abort current generation task immediately
            if websocket in self.active_tasks:
                self.active_tasks[websocket].cancel()
                logger.info("Aborted ongoing reasoning task.")
                
            # Send interruption event receipt
            await websocket.send(json.dumps({
                "type": "interruption_acknowledged",
                "message": "User interruption detected. Aborting and re-planning..."
            }))
            
            # Start re-plan/recovery task
            self.outbound_active[websocket] = False
            replan_task = asyncio.create_task(self.handle_replan(websocket))
            self.active_tasks[websocket] = replan_task
            return
            
        if msg_type == "interruption_event":
            # Direct injection/mock of interruption event (when agent isn't talking, ignore)
            logger.info("Explicit interruption event injected, but agent was not talking.")
            return

        # Start measuring turn-around round-trip latency
        start_time = time.perf_counter()
        
        # Create normal reasoning turn task
        turn_task = asyncio.create_task(self.handle_turn(websocket, payload, start_time))
        self.active_tasks[websocket] = turn_task

    async def handle_turn(self, websocket, payload: Dict[str, Any], start_time: float):
        """Processes a normal user voice/text query turn."""
        try:
            # 1. Decode / Transcribe
            user_text = ""
            msg_type = payload.get("type")
            if msg_type == "text_input":
                user_text = payload.get("text", "")
            elif msg_type == "audio_frame":
                # Mock speech-to-text translation (mock audio frames echo transcript or return stub)
                user_text = payload.get("transcript", "Mock transcribed audio content.")
            else:
                user_text = "Hello"

            logger.info(f"Voice Gateway Input Text: '{user_text}'")

            # 2. Safety pre-check using GuardrailChecker (AISG)
            allowed, verdict = self.guardrail_checker.check_input("voice_realtime", user_text)
            if not allowed:
                logger.warning(f"Guardrail checker blocked input: {verdict}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "code": "GUARDRAIL_BLOCKED_INPUT",
                    "message": f"Input safety check failed: {verdict}"
                }))
                return

            # 3. Budget checks using BudgetManager (ABTM)
            est_tokens = max(1, len(user_text) // 4)
            self.budget_manager.check_budget("voice_gateway", est_tokens)
            
            # Set outbound window active as we enter reasoning/speech state
            self.outbound_active[websocket] = True
            
            # 4. Process reasoning & check for progress tokens via Delegation Controller
            async def send_callback(data):
                await websocket.send(json.dumps(data))

            reasoning_delay = payload.get("reasoning_delay", 0.0)
            response_text = await self.delegation_controller.execute_reasoning_with_progress(
                user_text,
                send_callback,
                reasoning_delay=reasoning_delay
            )

            # 5. Safety post-check using GuardrailChecker (AISG)
            allowed, verdict = self.guardrail_checker.check_output("voice_realtime", response_text)
            if not allowed:
                logger.warning(f"Guardrail checker blocked output: {verdict}")
                self.outbound_active[websocket] = False
                await websocket.send(json.dumps({
                    "type": "error",
                    "code": "GUARDRAIL_BLOCKED_OUTPUT",
                    "message": f"Output safety check failed: {verdict}"
                }))
                return

            # 6. Check if Media Synthesis is requested (e.g. video keyword present)
            media_manifest = None
            media_keywords = ["video", "render", "campaign", "media", "synthesize"]
            if (payload.get("media_requested") or any(kw in user_text.lower() for kw in media_keywords)) and self.media_pipeline:
                logger.info("Voice turn requested media synthesis. Running MediaSynthesisPipeline...")
                
                # Mock media synthesis details
                storyboard = [
                    {"frame": 1, "visual": f"Scene responding to: {user_text}", "audio": response_text}
                ]
                visual_blueprint = {
                    "layout": "voice-response-layout",
                    "aspect_ratio": "16:9",
                    "coordinates": [0.0, 0.0, 1.0, 1.0],
                    "weathering": "sleek"
                }
                
                loop = asyncio.get_running_loop()
                media_manifest = await loop.run_in_executor(
                    None,
                    self.media_pipeline.run_pipeline,
                    storyboard,
                    response_text,
                    visual_blueprint,
                    None,  # skeleton_pose_data
                    "operator_channel"
                )
                logger.info("MediaSynthesisPipeline execution complete for voice turn.")

            # 7. Mock speech synthesis (TTS) - returns fake audio token manifest
            audio_manifest = {
                "audio_url": f"https://api.brandstream.ai/voice/mock-audio-{int(time.time())}.wav",
                "voice_id": "eleven_labs_voice_jessica",
                "sample_rate": 24000,
                "bit_rate": 128,
                "duration_sec": max(1.0, len(response_text) * 0.05),
                "transcript": response_text
            }

            # Record total tokens consumed (input + output) on ABTM
            total_tokens = est_tokens + max(1, len(response_text) // 4)
            self.budget_manager.record_usage("voice_gateway", total_tokens)

            # 8. Measure Latency
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000.0
            logger.info(f"Voice turn processing latency: {latency_ms:.2f}ms")

            # Formulate final response manifest
            response_payload = {
                "type": "voice_response",
                "text": response_text,
                "audio_manifest": audio_manifest,
                "latency_ms": latency_ms,
                "latency_compliant": latency_ms < self.latency_threshold_ms
            }
            if media_manifest:
                response_payload["media_manifest"] = media_manifest

            # Emit final voice response
            await websocket.send(json.dumps(response_payload))
            
            # 9. Webhook / messaging gateway dispatch notification
            self.wmg_gateway.dispatch_outgoing_message(
                connection_id=self.connection_id,
                recipient="operator_channel",
                message_text=f"Voice Gateway delivered response. Latency: {latency_ms:.1f}ms. Status: OK."
            )

        except asyncio.CancelledError:
            logger.info("Voice gateway processing task cancelled.")
        except Exception as e:
            logger.error(f"Error handling voice gateway turn: {e}", exc_info=True)
            await websocket.send(json.dumps({
                "type": "error",
                "message": str(e)
            }))
        finally:
            self.outbound_active[websocket] = False
            if websocket in self.active_tasks:
                del self.active_tasks[websocket]

    async def handle_replan(self, websocket):
        """Triggers a re-plan turn recovery loop after user interruption."""
        try:
            logger.info("Executing re-plan logic after user interruption...")
            
            # Send prompt to ModelRouter for recovery phrase
            prompt = "The user interrupted the agent while it was speaking. Generate a brief, polite conversational recovery response."
            
            loop = asyncio.get_running_loop()
            response_text = await loop.run_in_executor(
                None,
                self.budget_manager.wrap_router_call,
                self.model_router,
                "voice_delegation",
                "voice_realtime",
                prompt
            )
            
            # Generate fast TTS mock audio manifest for recovery response
            audio_manifest = {
                "audio_url": "https://api.brandstream.ai/voice/recovery-audio.wav",
                "voice_id": "eleven_labs_voice_jessica",
                "sample_rate": 24000,
                "bit_rate": 128,
                "duration_sec": 1.5,
                "transcript": response_text
            }
            
            await websocket.send(json.dumps({
                "type": "replan_response",
                "text": response_text,
                "audio_manifest": audio_manifest
            }))
            
            # Notify WMG that recovery turn is completed
            self.wmg_gateway.dispatch_outgoing_message(
                connection_id=self.connection_id,
                recipient="operator_channel",
                message_text=f"Interruption occurred. Re-plan recovery dispatched: '{response_text}'."
            )
            
        except asyncio.CancelledError:
            logger.info("Re-plan handler cancelled.")
        except Exception as e:
            logger.error(f"Error executing re-plan handler: {e}")
        finally:
            if websocket in self.active_tasks:
                del self.active_tasks[websocket]
