from __future__ import annotations

from typing import Any

import numpy as np


def _as_binary_mask(mask: Any) -> np.ndarray:
    if isinstance(mask, dict) and "counts" in mask and "size" in mask:
        return rle_to_mask(mask)
    arr = np.asarray(mask)
    if arr.ndim > 2:
        arr = np.squeeze(arr)
    if arr.ndim != 2:
        raise ValueError("mask must be a 2D array or RLE dict")
    return (arr > 0).astype(np.uint8)


def compute_mask_area(mask: Any) -> int:
    return int(np.count_nonzero(_as_binary_mask(mask)))


def compute_bbox_area(bbox: list[float]) -> int:
    if len(bbox) < 4:
        return 0
    width = max(0.0, float(bbox[2]) - float(bbox[0]))
    height = max(0.0, float(bbox[3]) - float(bbox[1]))
    return int(round(width * height))


def mask_to_rle(mask: Any) -> dict:
    binary = _as_binary_mask(mask)
    flat = binary.reshape(-1)
    counts: list[int] = []
    last = 0
    run = 0
    for value in flat:
        value = int(value)
        if value == last:
            run += 1
            continue
        counts.append(run)
        run = 1
        last = value
    counts.append(run)
    return {"size": [int(binary.shape[0]), int(binary.shape[1])], "counts": counts}


def rle_to_mask(rle: dict) -> np.ndarray:
    if not isinstance(rle, dict) or "size" not in rle or "counts" not in rle:
        raise ValueError("invalid RLE mask")
    height, width = [int(v) for v in rle["size"][:2]]
    counts = [int(v) for v in rle["counts"]]
    values: list[int] = []
    bit = 0
    for count in counts:
        if count > 0:
            values.extend([bit] * count)
        bit = 1 - bit
    total = height * width
    if len(values) < total:
        values.extend([0] * (total - len(values)))
    return np.asarray(values[:total], dtype=np.uint8).reshape((height, width))


def mask_to_polygon(mask: Any) -> list[list[float]]:
    binary = _as_binary_mask(mask)
    if not np.any(binary):
        return []
    try:
        import cv2

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not isinstance(contours, (list, tuple)) or not contours:
            return []
        contour = max(contours, key=cv2.contourArea)
        epsilon = max(1.0, 0.005 * cv2.arcLength(contour, True))
        approx = cv2.approxPolyDP(contour, epsilon, True)
        return [[float(point[0][0]), float(point[0][1])] for point in approx]
    except Exception:
        ys, xs = np.nonzero(binary)
        if xs.size == 0 or ys.size == 0:
            return []
        x1, x2 = float(xs.min()), float(xs.max())
        y1, y2 = float(ys.min()), float(ys.max())
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def compute_mask_iou(mask_a: Any, mask_b: Any) -> float:
    a = _as_binary_mask(mask_a).astype(bool)
    b = _as_binary_mask(mask_b).astype(bool)
    if a.shape != b.shape:
        raise ValueError("mask shapes must match for IoU")
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 0.0
    return float(inter / union)


def compute_mask_polygon_overlap(mask: Any, polygon: list[list[float]]) -> dict:
    binary = _as_binary_mask(mask)
    mask_area = compute_mask_area(binary)
    if mask_area == 0 or not polygon or len(polygon) < 3:
        return {
            "overlap_area": 0,
            "mask_area": mask_area,
            "overlap_ratio": 0.0,
            "inside_zone": False,
        }

    zone = np.zeros_like(binary, dtype=np.uint8)
    try:
        import cv2

        pts = np.asarray(polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(zone, [pts], 1)
        if not np.any(zone):
            _rasterize_polygon(zone, polygon)
    except Exception:
        _rasterize_polygon(zone, polygon)

    overlap_area = int(np.logical_and(binary > 0, zone > 0).sum())
    ratio = float(overlap_area / mask_area) if mask_area > 0 else 0.0
    return {
        "overlap_area": overlap_area,
        "mask_area": mask_area,
        "overlap_ratio": round(ratio, 3),
        "inside_zone": overlap_area > 0,
    }


def _rasterize_polygon(canvas: np.ndarray, polygon: list[list[float]]) -> None:
    min_x = max(0, int(np.floor(min(point[0] for point in polygon))))
    max_x = min(canvas.shape[1] - 1, int(np.ceil(max(point[0] for point in polygon))))
    min_y = max(0, int(np.floor(min(point[1] for point in polygon))))
    max_y = min(canvas.shape[0] - 1, int(np.ceil(max(point[1] for point in polygon))))
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if _point_in_polygon(float(x) + 0.5, float(y) + 0.5, polygon):
                canvas[y, x] = 1


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside
