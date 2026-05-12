# Model registry table (Phase 41)

| Governance ID | Registry key | Active version | Task | Approval | Notes |
| --- | --- | --- | --- | --- | --- |
| weapon_yolo11s_v2_current | weapon_detector | v2 | weapon_detection | demo_approved | Metrics from offline eval |
| phone_detector_current | phone_detector | v1 | phone_detection | production_pending | Metrics pending benchmark |
| anomaly_videomae_current | anomaly_pipeline | current | anomaly_detection | demo_approved | Live-eval report required in prod policy |
| sam2_segmentation | segmentation_sam2 | sam2_t | segmentation | production_pending | Checkpoint optional in dev |
| face_insightface_buffalo_l | face_recognition | buffalo_l | face_embedding | demo_approved | Bundle path |
| reid_osnet_provider | reid_osnet | torchreid | person_reid | demo_approved | Library-managed weights |
| open_vocab_grounding | open_vocab | grounding_dino | open_vocabulary | demo_approved | Prompt sensitivity |
| llm_runtime_provider | llm_provider | config | llm | demo_approved | Config-only |
| liveness_provider_gate | liveness_provider | none | identity_liveness | production_pending | Disabled / roadmap |

Canonical JSON: `models/registry.json`.
