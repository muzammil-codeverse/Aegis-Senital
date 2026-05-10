from app.models.streaming_models import ReplayClipRequest, StreamHealth


def test_stream_health_defaults():
    model = StreamHealth(camera_id="cam_01")
    assert model.camera_id == "cam_01"
    assert model.status == "stopped"
    assert model.dropped_frames_total == 0


def test_replay_clip_request_defaults():
    model = ReplayClipRequest(case_id="case_1")
    assert model.case_id == "case_1"
    assert model.seconds_before == 10
    assert model.seconds_after == 20
    assert model.attach_to_case is False
