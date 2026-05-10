import json
import os
import tempfile
import yaml
import pytest
from pathlib import Path


@pytest.fixture
def sample_kaggle_config(tmp_path):
    config = {
        "ucf_crime": {
            "kaggle_slug": "odins0n/ucf-crime-dataset",
            "fallback_slug": "bypktt/ucf-crimes",
            "raw_dir": str(tmp_path / "ucf_crime"),
            "zip_dir": str(tmp_path / "kaggle_zips"),
            "role": "broad_surveillance_anomaly",
            "required": True,
        },
        "xd_violence": {
            "kaggle_slug": "bypktt/xd-violence",
            "raw_dir": str(tmp_path / "xd_violence"),
            "zip_dir": str(tmp_path / "kaggle_zips"),
            "role": "violence_anomaly",
            "required": True,
        },
    }
    cfg_file = tmp_path / "kaggle_anomaly_sources.yaml"
    cfg_file.write_text(yaml.dump(config))
    return cfg_file, config, tmp_path


def test_kaggle_config_loads(sample_kaggle_config):
    cfg_file, config, tmp_path = sample_kaggle_config
    with open(cfg_file) as fh:
        loaded = yaml.safe_load(fh)
    assert "ucf_crime" in loaded
    assert "xd_violence" in loaded
    assert loaded["ucf_crime"]["required"] is True


def test_kaggle_config_required_fields(sample_kaggle_config):
    _, config, _ = sample_kaggle_config
    for name, cfg in config.items():
        assert "kaggle_slug" in cfg
        assert "raw_dir" in cfg
        assert "zip_dir" in cfg


def test_dataset_registry_loads_config():
    from inference.anomaly.dataset_registry import load_kaggle_sources
    sources = load_kaggle_sources()
    # Should at least return a dict (empty if file not found, but schema is correct)
    assert isinstance(sources, dict)


def test_dataset_registry_roboflow_loads():
    from inference.anomaly.dataset_registry import load_roboflow_sources
    sources = load_roboflow_sources()
    assert isinstance(sources, dict)


def test_zip_extraction_manifest_writes(tmp_path):
    manifest_path = tmp_path / "extraction_manifest.json"
    manifest = {"ucf_crime": {"status": "success", "zip_file": "test.zip", "dest_dir": str(tmp_path)}}
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh)
    with open(manifest_path) as fh:
        loaded = json.load(fh)
    assert loaded["ucf_crime"]["status"] == "success"


def test_prepare_script_label_mapping():
    from scripts.prepare_video_anomaly_dataset import _canonical_label, LABEL_MAP
    assert _canonical_label("Fighting") == "violence"
    assert _canonical_label("Normal") == "normal"
    assert _canonical_label("Shoplifting") == "theft"
    assert _canonical_label("RoadAccidents") == "traffic_accident"
    assert _canonical_label("UnknownClass") == "generic_anomaly"


def test_prepare_script_collect_videos(tmp_path):
    from scripts.prepare_video_anomaly_dataset import _collect_videos
    fight_dir = tmp_path / "Fighting"
    fight_dir.mkdir()
    (fight_dir / "fight001.mp4").touch()
    norm_dir = tmp_path / "Normal"
    norm_dir.mkdir()
    (norm_dir / "normal001.mp4").touch()

    items = _collect_videos(tmp_path)
    assert len(items) == 2
    labels = {i["label"] for i in items}
    assert "violence" in labels
    assert "normal" in labels


def test_prepare_script_jsonl_structure(tmp_path):
    from scripts.prepare_video_anomaly_dataset import _make_clips
    video_items = [{"video_path": "/fake/fight.mp4", "label": "violence", "is_anomaly": True}]
    clips = _make_clips(video_items, "ucf_crime", clip_length=5.0, stride=2.5)
    assert len(clips) > 0
    c = clips[0]
    assert "clip_id" in c
    assert "label" in c
    assert "is_anomaly" in c
    assert "start_sec" in c
    assert "end_sec" in c
    assert "source" in c
