from __future__ import annotations

def predict_next(camera_id: str, graph: dict) -> dict:
    neighbors = graph.get(camera_id, {})
    if not neighbors:
        return {"camera_id": None, "eta_seconds": None, "confidence": 0.0}
    next_cam = max(neighbors, key=lambda k: neighbors[k].get("weight", 0.0))
    meta = neighbors[next_cam]
    return {"camera_id": next_cam, "eta_seconds": meta.get("eta_seconds", 5), "confidence": meta.get("weight", 0.5)}
