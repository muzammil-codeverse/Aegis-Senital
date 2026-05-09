from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Severity → BGR color (OpenCV uses BGR)
_SEVERITY_BGR: dict[str, tuple[int, int, int]] = {
    "critical": (79, 77, 255),
    "high":     (22, 140, 250),
    "medium":   (20, 219, 250),
    "low":      (26, 196, 82),
    "info":     (255, 144, 24),
    "default":  (125, 117, 108),
}


def _load_config() -> dict:
    try:
        from inference.config_runtime import load_runtime_config
        return load_runtime_config("frame_annotation")
    except Exception:
        return {}


def _severity_bgr(severity: str | None, cfg_colors: dict) -> tuple[int, int, int]:
    sev = (severity or "default").lower()
    if sev in cfg_colors:
        rgb = cfg_colors[sev]
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            return (int(rgb[2]), int(rgb[1]), int(rgb[0]))  # RGB→BGR
    return _SEVERITY_BGR.get(sev, _SEVERITY_BGR["default"])


class FrameAnnotationService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cfg: dict | None = None
        self._output_dir: Path | None = None

    def _get_cfg(self) -> dict:
        with self._lock:
            if self._cfg is None:
                self._cfg = _load_config()
            return self._cfg

    def _ensure_output_dir(self, cfg: dict) -> Path:
        with self._lock:
            if self._output_dir is None:
                raw = cfg.get("output_dir", "backend/output/annotated")
                base = Path(__file__).resolve().parents[3]
                p = Path(raw) if Path(raw).is_absolute() else (base / raw)
                p.mkdir(parents=True, exist_ok=True)
                self._output_dir = p
            return self._output_dir

    def annotate_frame(
        self,
        input_frame_path: str,
        output_frame_path: str,
        overlay_items: list[dict],
        frame_size: tuple[int, int] | None = None,
    ) -> dict:
        """
        Draw bounding boxes and labels onto *input_frame_path* and write the
        result to *output_frame_path*.

        Returns a dict with keys:
          annotated_path, width, height, overlay_count, generated_at
        """
        try:
            import cv2
        except ImportError:
            logger.warning("opencv-python not installed; skipping annotation")
            return self._fallback(output_frame_path, overlay_items)

        cfg = self._get_cfg()
        if not cfg.get("enabled", True):
            return self._fallback(output_frame_path, overlay_items)

        cfg_colors = cfg.get("colors", {})
        label_cfg = cfg.get("labels", {})
        bbox_thickness = int(cfg.get("bbox", {}).get("thickness", 2))
        font_scale = float(label_cfg.get("font_scale", 0.45))
        label_thickness = int(label_cfg.get("thickness", 1))
        lpad = int(label_cfg.get("padding", 3))
        show_conf = bool(cfg.get("show_confidence", True))
        show_tid = bool(cfg.get("show_track_id", True))
        conf_threshold = float(cfg.get("confidence_threshold", 0.0))

        try:
            img = cv2.imread(str(input_frame_path))
            if img is None:
                return self._fallback(output_frame_path, overlay_items)
        except Exception as exc:
            logger.debug("cv2.imread failed for %s: %s", input_frame_path, exc)
            return self._fallback(output_frame_path, overlay_items)

        h, w = img.shape[:2]
        if frame_size:
            src_w, src_h = frame_size
        else:
            src_w, src_h = w, h

        scale_x = w / max(src_w, 1)
        scale_y = h / max(src_h, 1)

        drawn = 0
        for item in overlay_items:
            if item.get("type") != "bbox":
                continue
            bbox = item.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                continue
            conf = item.get("confidence")
            if conf is not None and conf < conf_threshold:
                continue

            x1 = int(bbox[0] * scale_x)
            y1 = int(bbox[1] * scale_y)
            x2 = int(bbox[2] * scale_x)
            y2 = int(bbox[3] * scale_y)

            color = _severity_bgr(item.get("severity"), cfg_colors)

            cv2.rectangle(img, (x1, y1), (x2, y2), color, bbox_thickness)

            # Build label text
            label_parts = []
            raw_label = item.get("label", "")
            base_label = raw_label.split(" ")[0] if raw_label else "obj"
            label_parts.append(base_label)
            if show_conf and conf is not None:
                label_parts.append(f"{conf:.0%}")
            track_id = item.get("track_id")
            if show_tid and track_id is not None:
                label_parts.append(f"#{track_id}")

            label_text = " ".join(label_parts)
            (tw, th), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, label_thickness)
            lx1 = max(x1, 0)
            ly1 = max(y1 - th - lpad * 2, 0)
            cv2.rectangle(img, (lx1, ly1), (lx1 + tw + lpad * 2, ly1 + th + lpad * 2), color, -1)
            cv2.putText(
                img, label_text,
                (lx1 + lpad, ly1 + th + lpad),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                (0, 0, 0), label_thickness, cv2.LINE_AA,
            )
            drawn += 1

        try:
            cv2.imwrite(str(output_frame_path), img)
        except Exception as exc:
            logger.warning("cv2.imwrite failed: %s", exc)
            return self._fallback(output_frame_path, overlay_items)

        return {
            "annotated_path": str(output_frame_path),
            "width": w,
            "height": h,
            "overlay_count": drawn,
            "generated_at": time.time(),
        }

    # ------------------------------------------------------------------

    def annotate_for_camera(
        self,
        camera_id: str,
        input_frame_path: str,
        overlay_items: list[dict],
        frame_id: int | None = None,
        frame_size: tuple[int, int] | None = None,
    ) -> dict | None:
        """Convenience wrapper: derives output path from camera + frame id."""
        cfg = self._get_cfg()
        if not cfg.get("enabled", True):
            return None
        try:
            out_dir = self._ensure_output_dir(cfg)
            cam_dir = out_dir / camera_id
            cam_dir.mkdir(parents=True, exist_ok=True)
            src_name = Path(input_frame_path).stem
            out_name = f"{src_name}_ann.jpg" if frame_id is None else f"frame_{frame_id:06d}_ann.jpg"
            out_path = cam_dir / out_name
            return self.annotate_frame(input_frame_path, str(out_path), overlay_items, frame_size=frame_size)
        except Exception as exc:
            logger.warning("annotate_for_camera failed for %s: %s", camera_id, exc)
            return None

    @staticmethod
    def _fallback(output_frame_path: str, overlay_items: list[dict]) -> dict:
        return {
            "annotated_path": None,
            "width": None,
            "height": None,
            "overlay_count": len([i for i in overlay_items if i.get("type") == "bbox"]),
            "generated_at": time.time(),
        }


_annotation_service: FrameAnnotationService | None = None
_annotation_service_lock = threading.Lock()


def get_frame_annotation_service() -> FrameAnnotationService:
    global _annotation_service
    if _annotation_service is None:
        with _annotation_service_lock:
            if _annotation_service is None:
                _annotation_service = FrameAnnotationService()
    return _annotation_service
