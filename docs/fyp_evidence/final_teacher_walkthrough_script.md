# Teacher/Examiner Walkthrough Script — Aegis Sentinel AI Defense

**Date:** 2026-05-13  
**Duration:** ~15-20 minutes

---

## Opening Statement (1 min)

> "This is Aegis Sentinel AI, a research platform for multi-source surveillance analytics. The system integrates a live drone simulator, multiple AI models, and a real-time analytics dashboard. Everything runs locally on this machine — no cloud services. I'll walk through the five core capabilities."

---

## Capability 1: Live Drone Simulation (3 min)

**Show:** Drone Simulation panel in dashboard

> "The drone is simulated using AirSimNH, Microsoft's open-source Unreal Engine environment. You can see the live GPS coordinates, altitude, and camera feed from the drone's front camera."

**Point to:**
- Runtime status: "AirSimNH — connected"
- GPS: latitude, longitude, altitude
- Camera frame: live 256×144 image

> "The system captures frames through our StreamProcessor pipeline, which applies detection models and generates observation candidates — always labelled as 'Simulated aerial observation' to prevent any false real-world claims."

**Show:** Trigger mission

> "I can trigger a patrol mission. The drone executes a sequence of GPS waypoints converted to AirSim's NED coordinate system. The system records telemetry and waypoint events in real time."

---

## Capability 2: Multi-Source Fusion (3 min)

**Show:** Fusion panel

> "The fusion engine correlates observations from multiple cameras and the drone feed. When the same observation appears in overlapping camera fields at similar times, it creates a 'Candidate cross-source observation'."

**Point to:**
- Correlation confidence score
- Source camera IDs
- Timestamp delta

> "Crucially, every correlation is flagged with 'Operator review required'. The system never makes autonomous enforcement decisions."

---

## Capability 3: Investigation & Case Management (3 min)

**Show:** Investigations panel

> "Investigators can create hypotheses linking observations across time. The system shows 'Evidence-backed hypothesis' with confidence bounds. When confidence is below threshold, it shows 'Insufficient data' — the system is designed to be conservative."

**Show:** Cases panel

> "Cases aggregate evidence for formal review. Each case has a timeline, linked media, and an audit trail. All identifications remain as 'candidate' until a human operator confirms or rejects."

---

## Capability 4: Video Analysis (3 min)

**Show:** Uploaded Videos panel

> "The system can analyse any uploaded CCTV or aerial footage. This demo video shows a street scene. The AI detects people and vehicles, and the report is generated with the same safe labelling — 'Simulated aerial observation', operator review required."

**Point to:**
- Detection events in the report
- Confidence scores
- Frame timestamps

> "We use YOLOv8 for object detection, SAM2 for segmentation, and GroundingDINO for open-vocabulary detection. All running on the local CUDA GPU."

---

## Capability 5: Analytics & GIS (2 min)

**Show:** Analytics panel

> "The analytics overview shows system-wide detection metrics — total observations, correlation rates, case resolution times."

**Show:** GIS panel (if available)

> "The GIS layer shows camera coverage zones and drone flight paths overlaid on a map."

---

## Technical Architecture Summary (2 min)

> "The backend is FastAPI on Python 3.12, the frontend is React with TypeScript, and the drone integration uses cosysairsim's msgpack-RPC protocol. The database uses SQLAlchemy with SQLite for development. The AI pipeline runs YOLOv8, SAM2, GroundingDINO, and InsightFace for face re-identification — 1026 unit tests pass."

---

## Ethical Framework (1 min)

> "Privacy and ethics were central design requirements. The system:
> 1. Never makes automated enforcement decisions
> 2. Requires operator review for all identifications
> 3. Uses role-based access control (RBAC)
> 4. Maintains complete audit logs
> 5. Labels all AI outputs as 'candidate' observations
> 6. Has 'Insufficient data' guards on low-confidence inferences"

---

## Closing (30 sec)

> "The full system has 1026 unit tests passing, all core APIs validated, and the drone simulation running live on AirSimNH. I'm happy to deep-dive into any component — the code, the models, the API design, or the ethics framework."

---

_Script prepared for Phase 56 defense — Aegis Sentinel AI_
