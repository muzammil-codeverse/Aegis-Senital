from app.services.hls_service import HlsService


def test_hls_service_rejects_unsafe_segment_name():
    service = HlsService()
    try:
        service.resolve_segment_path("cam_01", "../segment.ts")
    except ValueError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("unsafe segment path should be rejected")


def test_hls_service_reports_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr("app.services.hls_service._resolve_ffmpeg_binary", lambda: None)
    service = HlsService()
    info = service.get_playlist_info("cam_01")
    assert info.available is False
    assert "ffmpeg" in (info.detail or "")
