def validate_frame_result(detection, tracking, events):
    objects = getattr(detection, "objects", None)
    if objects is None:
        objects = getattr(detection, "detections", [])
    assert isinstance(objects, list)

    for obj in objects:
        assert obj.bbox is not None
        assert obj.confidence >= 0

    for track in tracking:
        track_id = getattr(track, "id", None)
        if track_id is None:
            track_id = getattr(track, "track_id", None)
        assert track_id is not None

    return True
