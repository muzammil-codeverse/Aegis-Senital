import asyncio

from app.services.webrtc_service import WebRTCService


def test_webrtc_service_falls_back_without_active_stream():
    service = WebRTCService()
    result = asyncio.run(service.handle_offer("cam_01", {"sdp": "v=0", "type": "offer"}))
    assert result.status in {"unavailable", "fallback", "disabled"}
    assert result.preview_url is not None

