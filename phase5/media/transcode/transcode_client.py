import os
import uuid
import time
import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger("BrandStream.TranscodeClient")

class TranscodeClient:
    """
    Thin client to external AWS Elemental style transcode service (GAP-08).
    Offloads heavy ffmpeg/moviepy operations from local container.
    """
    def __init__(self, endpoint_url: str = "https://api.elemental-transcode.internal", mock: Optional[bool] = None):
        self.endpoint_url = endpoint_url.rstrip("/")
        if mock is not None:
            self.mock = mock
        else:
            self.mock = os.getenv("TRANSCODE_MOCK", "true").lower() in ("true", "1", "yes")

        logger.info(f"Initialized Transcode Client. Endpoint: {self.endpoint_url}, Mock Mode: {self.mock}")

    def submit_transcode_job(
        self,
        input_media_urls: List[str],
        output_bucket: str = "brandstream-egress",
        output_format: str = "mp4",
        resolution: str = "1920x1080",
        bitrate_kbps: int = 4000
    ) -> str:
        """
        Submits a video composition/transcode request to the external API.
        Returns the transcode job ID.
        """
        job_payload = {
            "inputs": input_media_urls,
            "output_config": {
                "s3_bucket": output_bucket,
                "format": output_format,
                "resolution": resolution,
                "bitrate_kbps": bitrate_kbps
            },
            "timestamp": time.time()
        }

        if self.mock:
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            logger.info(f"[Mock Mode] Submitted transcode job. Generated Job ID: {job_id}")
            return job_id

        # Real HTTP invocation to the AWS Elemental style API
        try:
            api_key = os.getenv("TRANSCODE_API_KEY")
            headers = {
                "Content-Type": "application/json",
            }
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            response = requests.post(
                f"{self.endpoint_url}/jobs",
                json=job_payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            res_data = response.json()
            job_id = res_data.get("job_id")
            if not job_id:
                raise ValueError("Transcode server response did not include a job_id.")
            logger.info(f"Submitted transcode job to service. Job ID: {job_id}")
            return job_id
        except Exception as e:
            logger.error(f"Failed to submit transcode job to external API: {e}")
            raise

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieves status of transcoder job.
        In Mock mode, returns fake output URL.
        """
        if self.mock:
            logger.info(f"[Mock Mode] Retrieving transcode status for {job_id}")
            # Mock success output payload
            output_url = f"https://s3.amazonaws.com/brandstream-egress/{job_id}/final_campaign.mp4"
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "progress_pct": 100,
                "output_url": output_url,
                "details": {
                    "duration_seconds": 15.0,
                    "codec": "h264",
                    "file_size_bytes": 7864320
                }
            }

        try:
            api_key = os.getenv("TRANSCODE_API_KEY")
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            response = requests.get(
                f"{self.endpoint_url}/jobs/{job_id}",
                headers=headers,
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch transcode job status for {job_id}: {e}")
            raise
