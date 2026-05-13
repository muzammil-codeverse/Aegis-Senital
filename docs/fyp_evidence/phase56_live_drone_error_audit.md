# Phase 56 Live Drone Runtime Error Audit

Generated: 2026-05-13 (Phase 56 baseline)

## 1. Runtime Inventory

| Runtime | Status | Path | Type |
|---------|--------|------|------|
| Blocks | AVAILABLE | `C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks.exe` | Windows EXE |
| AirSimNH | UNAVAILABLE | `C:\AegisExternalTools\drone_sim\runtime\environments\AirSimNH\AirSimNH\LinuxNoEditor\AirSimNH.sh` | Linux build — incompatible on Windows |
| CityEnviron | NOT INSTALLED | — | Missing; extraction failed (7z not available) |

**Selected runtime:** Blocks (fallback)  
**Fallback used:** true

## 2. Blocks Runtime Crash Analysis

**Last crash type:** `Ensure`  
**GPU at crash time:** Intel(R) UHD Graphics ← **ROOT CAUSE**  
**Expected GPU:** NVIDIA GeForce RTX 4060 Laptop GPU  

**Error:**
```
Ensure condition failed: ActorHasBegunPlay == EActorBeginPlayState::HasNotBegunPlay
[File: Engine\Source\Runtime\Engine\Private\Actor.cpp] [Line: 2796]
EndPlay on CameraDirector failed. Make sure to call Super::EndPlay() in your override function.
```

**Stack trace (abbreviated):**
```
0x... Blocks.exe!AActor::RouteEndPlay()
0x... Blocks.exe!UWorld::EndPlay()
0x... Blocks.exe!UGameEngine::PreExit()
0x... Blocks.exe!FEngineLoop::Exit()
```

**Analysis:**
- Crash is in shutdown path (`EndPlay`), not initialization.
- Blocks.exe defaults to Intel UHD integrated GPU instead of NVIDIA RTX 4060.
- Intel GPU causes rendering pipeline instability that triggers CameraDirector ensure during EndPlay.
- RPC port 41451 may open successfully but runtime destabilizes under Intel GPU load.

**Required fix:** Force Blocks.exe to use NVIDIA GPU via Windows Graphics Settings:  
`Windows Settings → System → Display → Graphics → Add Blocks.exe → High performance (NVIDIA)`

**Alternative launch flags:**
- `-dx12` — forces DirectX 12, tends to select dedicated GPU on hybrid systems
- `-ResX=640 -ResY=480 -NoSound` — minimal load profile

## 3. AirSimNH Status

- **Downloaded:** Yes (Phase 55)
- **Platform:** Linux (LinuxNoEditor — `.sh` entry point)
- **Windows compatible:** NO
- **Cause:** GitHub AirSim release asset `AirSimNH.zip` contained Linux Unreal build
- **Fix needed:** Download Windows build specifically (filter out Linux-named assets)
- **Blocker:** 1.6 GB download; previous attempt grabbed Linux build first

## 4. CityEnviron Status

- **Downloaded:** No
- **Cause:** Extraction requires 7-Zip (`7z.exe`) which is not installed on this system
- **7-Zip path check:** `C:\Program Files\7-Zip\7z.exe` → NOT FOUND
- **Fix needed:** Install 7-Zip OR download a simple `.zip` release of CityEnviron

## 5. RPC Status

- **Port 41451:** CLOSED (simulator not running at audit time)
- **cosysairsim client:** v3.3.0 installed and importable
- **AirSim settings path:** `C:\Users\mufee\Documents\AirSim\settings.json`
- **RPC behavior:** Port opens when simulator launches successfully; closes on crash/shutdown

## 6. Dashboard Status

- **Backend:** Not running at audit time (needs launch)
- **Frontend:** Not running at audit time (needs launch)
- **Demo data:** May need re-seeding

## 7. Missing Videos

- `datasets/demo_videos/` — directory existence unknown; videos need preparation
- Test videos: `datasets/test_videos/test_001.mp4` — existence to be verified

## 8. Missing Scripts (Phase 56 requires)

| Script | Status |
|--------|--------|
| `scripts/repair_blocks_runtime.py` | MISSING — must be created |
| `scripts/smoke_drone_dashboard_apis.py` | MISSING — must be created |
| `scripts/smoke_drone_ws_updates.py` | MISSING — must be created |

## 9. Validation Blockers (Phase 55 exit state)

- `mission_status: failed` — Blocks mission ends in `failed` status
  - Root cause: `_final_mission_status` degraded path requires `had_frame AND had_telemetry`
  - Likely issue: `telemetry.status != "connected"` when runtime crashes during mission
- `--require-city` smoke fails when only Blocks is available
- AirSimNH Windows binary missing

## 10. Environment Baseline

| Item | Value |
|------|-------|
| Python | 3.12.10 (venv) |
| CUDA | RTX 4060 Laptop GPU — AVAILABLE |
| cosysairsim | 3.3.0 |
| pip check | Clean |
| Git branch | main |
| Last commit | 41aec14d (Phase 55) |
| 7-Zip | NOT INSTALLED |

## 11. Recovery Plan (Phase 56)

1. **Create `repair_blocks_runtime.py`** — stable launch with NVIDIA hint, minimal settings
2. **Update download script** — prefer Windows assets (filter out "linux" named)
3. **Update inventory catalog** — handle Linux-only AirSimNH gracefully
4. **Fix mission status** — ensure `degraded_fallback_complete` fires for Blocks
5. **Create missing API/WS smoke scripts**
6. **Launch and validate full stack**
7. **Seed demo data and verify all routes**
8. **Produce defense docs**

## 12. Honest Defense Assessment

- **Live Windows simulator:** Blocks.exe (requires manual NVIDIA GPU selection)
- **City runtime:** Not achievable without 7-Zip or Windows AirSimNH download (1.6 GB)
- **Defense path:** Blocks fallback + full demo data + uploaded video analysis
- **Safe wording:** All output is marked `simulated=true`, `operator_review_required=true`
