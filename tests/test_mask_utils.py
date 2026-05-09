from __future__ import annotations

import numpy as np

from inference.segmentation.mask_utils import (
    compute_bbox_area,
    compute_mask_area,
    compute_mask_iou,
    compute_mask_polygon_overlap,
    mask_to_polygon,
    mask_to_rle,
    rle_to_mask,
)


def test_mask_area_and_bbox_area() -> None:
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:5, 3:7] = 1

    assert compute_mask_area(mask) == 12
    assert compute_bbox_area([3, 2, 7, 5]) == 12


def test_rle_encode_decode_roundtrip() -> None:
    mask = np.zeros((6, 5), dtype=np.uint8)
    mask[1:4, 2:5] = 1

    encoded = mask_to_rle(mask)
    decoded = rle_to_mask(encoded)

    assert np.array_equal(decoded, mask)


def test_mask_iou() -> None:
    left = np.zeros((10, 10), dtype=np.uint8)
    right = np.zeros((10, 10), dtype=np.uint8)
    left[1:5, 1:5] = 1
    right[3:7, 3:7] = 1

    assert round(compute_mask_iou(left, right), 4) == round(4 / 28, 4)


def test_mask_polygon_overlap() -> None:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[5:15, 5:15] = 1
    polygon = [[10, 0], [19, 0], [19, 19], [10, 19]]

    overlap = compute_mask_polygon_overlap(mask, polygon)

    assert overlap["overlap_area"] == 50
    assert overlap["mask_area"] == 100
    assert overlap["overlap_ratio"] == 0.5
    assert overlap["inside_zone"] is True


def test_mask_to_polygon_returns_points() -> None:
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:8, 3:7] = 1

    polygon = mask_to_polygon(mask)

    assert len(polygon) >= 3
