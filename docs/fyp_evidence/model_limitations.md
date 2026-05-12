# Known model limitations (Phase 41)

Summaries mirror `known_limitations` arrays in `models/registry.json` (single source of truth).

## Weapon (YOLO11s)

- Weak knife / shotgun AP in offline eval; grenade class lacks validation instances.

## Phone

- Roboflow-sourced weights; domain shift not verified on all cameras; dual class ids map to phone.

## Anomaly (VideoMAE)

- Offline scores are pipeline validation signals; live evaluation coverage is limited by available labeled site video.

## SAM2

- Segmentation quality depends on upstream detector boxes.

## Open vocabulary

- Prompt sensitivity and domain-shift risk; outputs are advisory.

## Identity / liveness

- Liveness disabled without integrated provider; enabling without provider is a production governance risk when fail flags are set.

## LLM provider

- Availability and data handling depend on configured vendor and keys.
