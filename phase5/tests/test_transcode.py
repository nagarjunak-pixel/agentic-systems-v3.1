import pytest
from media.transcode.transcode_client import TranscodeClient

def test_transcode_client_mock():
    client = TranscodeClient(mock=True)
    input_urls = ["http://localhost:8188/view?filename=frame_1.png", "http://localhost:8188/view?filename=frame_2.png"]
    
    job_id = client.submit_transcode_job(
        input_media_urls=input_urls,
        output_bucket="my-bucket",
        output_format="mp4",
        resolution="1280x720",
        bitrate_kbps=3000
    )
    
    assert job_id.startswith("job_")
    
    status = client.get_job_status(job_id)
    assert status["job_id"] == job_id
    assert status["status"] == "COMPLETED"
    assert "output_url" in status
    assert status["output_url"].endswith(".mp4")
    assert status["details"]["file_size_bytes"] > 0
