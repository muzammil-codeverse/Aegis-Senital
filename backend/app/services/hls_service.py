from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from app.models.streaming_models import HlsPlaylistInfo
from app.services.rtsp_ingest_service import load_streaming_runtime_config

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe_camera_component(camera_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(camera_id or "").strip())
    return cleaned or "camera"


def _resolve_ffmpeg_binary() -> str | None:
    explicit = (os.environ.get("AEGIS_FFMPEG_PATH") or os.environ.get("FFMPEG_BINARY") or "").strip()
    if explicit:
        return explicit

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        winget_link = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        try:
            target = os.readlink(str(winget_link))
            return target.replace("\\\\?\\", "")
        except OSError:
            try:
                if os.path.lexists(str(winget_link)):
                    return str(winget_link)
            except OSError:
                pass
    return None


class HlsService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._config = load_streaming_runtime_config().get("streaming", {})
        self._hls_cfg = self._config.get("hls", {})
        self._enabled = bool(self._config.get("enabled", True)) and bool(self._hls_cfg.get("enabled", False))
        self._segment_seconds = int(self._hls_cfg.get("segment_seconds", 2))
        self._playlist_length = int(self._hls_cfg.get("playlist_length", 6))
        self._cleanup_old_segments = bool(self._hls_cfg.get("cleanup_old_segments", True))
        self._retention_minutes = int(self._hls_cfg.get("max_retention_minutes", 60))
        self._output_dir = Path(str(self._hls_cfg.get("output_dir") or "storage/hls"))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._ffmpeg = _resolve_ffmpeg_binary()

    @property
    def ffmpeg_available(self) -> bool:
        return bool(self._ffmpeg)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_playlist_info(self, camera_id: str) -> HlsPlaylistInfo:
        camera_dir = self._camera_dir(camera_id)
        playlist_path = camera_dir / "playlist.m3u8"
        available = playlist_path.exists()
        detail = None
        if not self._enabled:
            detail = "HLS is disabled by runtime configuration"
        elif not self.ffmpeg_available:
            detail = "ffmpeg is not installed"
        elif not available:
            detail = "playlist not generated"
        return HlsPlaylistInfo(
            camera_id=camera_id,
            available=available,
            playlist_url=f"/api/streams/{camera_id}/hls/playlist.m3u8" if available else None,
            output_dir=str(camera_dir),
            segment_seconds=self._segment_seconds,
            playlist_length=self._playlist_length,
            detail=detail,
        )

    def ensure_preview(self, camera_id: str, source_uri: str | None) -> HlsPlaylistInfo:
        if not self._enabled:
            return self.get_playlist_info(camera_id)
        if not self.ffmpeg_available:
            return self.get_playlist_info(camera_id)
        if not source_uri:
            return HlsPlaylistInfo(
                camera_id=camera_id,
                available=False,
                output_dir=str(self._camera_dir(camera_id)),
                segment_seconds=self._segment_seconds,
                playlist_length=self._playlist_length,
                detail="camera source is unavailable",
            )

        with self._lock:
            proc = self._processes.get(camera_id)
            if proc is not None and proc.poll() is None:
                return self.get_playlist_info(camera_id)

            camera_dir = self._camera_dir(camera_id)
            camera_dir.mkdir(parents=True, exist_ok=True)
            if self._cleanup_old_segments:
                self.cleanup_old_segments(camera_id)
            playlist_path = camera_dir / "playlist.m3u8"
            segment_pattern = str(camera_dir / "segment_%06d.ts")
            command = self._build_ffmpeg_command(source_uri, playlist_path, segment_pattern)
            try:
                self._processes[camera_id] = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as exc:
                logger.warning("HLS preview start failed for %s: %s", camera_id, exc)
                return HlsPlaylistInfo(
                    camera_id=camera_id,
                    available=False,
                    output_dir=str(camera_dir),
                    segment_seconds=self._segment_seconds,
                    playlist_length=self._playlist_length,
                    detail=str(exc),
                )
        return self.get_playlist_info(camera_id)

    def stop_preview(self, camera_id: str) -> None:
        with self._lock:
            proc = self._processes.pop(camera_id, None)
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def resolve_playlist_path(self, camera_id: str) -> Path:
        return self._camera_dir(camera_id) / "playlist.m3u8"

    def resolve_segment_path(self, camera_id: str, segment_name: str) -> Path:
        if not _SAFE_NAME.match(segment_name):
            raise ValueError("unsafe HLS segment path")
        if not segment_name.endswith((".ts", ".m4s")):
            raise ValueError("unsupported HLS segment extension")
        path = (self._camera_dir(camera_id) / segment_name).resolve()
        base = self._camera_dir(camera_id).resolve()
        if base not in path.parents:
            raise ValueError("segment path escapes camera directory")
        return path

    def cleanup_old_segments(self, camera_id: str) -> None:
        if not self._cleanup_old_segments:
            return
        cutoff = time.time() - (self._retention_minutes * 60)
        for path in self._camera_dir(camera_id).glob("*"):
            if path.is_dir():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    def _build_ffmpeg_command(self, source_uri: str, playlist_path: Path, segment_pattern: str) -> list[str]:
        command = [self._ffmpeg or "ffmpeg", "-y"]
        lowered = str(source_uri).lower()
        if lowered.startswith("rtsp://"):
            command.extend(["-rtsp_transport", "tcp"])
        elif lowered.endswith((".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v")):
            command.extend(["-stream_loop", "-1", "-re"])
        command.extend(
            [
                "-i",
                source_uri,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "zerolatency",
                "-g",
                str(max(2, self._segment_seconds * 15)),
                "-sc_threshold",
                "0",
                "-f",
                "hls",
                "-hls_time",
                str(self._segment_seconds),
                "-hls_list_size",
                str(self._playlist_length),
                "-hls_flags",
                "delete_segments+append_list+omit_endlist",
                "-hls_segment_filename",
                segment_pattern,
                str(playlist_path),
            ]
        )
        return command

    def _camera_dir(self, camera_id: str) -> Path:
        return self._output_dir / _safe_camera_component(camera_id)


_hls_service: HlsService | None = None
_hls_service_lock = threading.Lock()


def get_hls_service() -> HlsService:
    global _hls_service
    if _hls_service is None:
        with _hls_service_lock:
            if _hls_service is None:
                _hls_service = HlsService()
    return _hls_service
