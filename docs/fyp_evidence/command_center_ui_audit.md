# Command Center UI Audit

Date audited: May 12, 2026

## Audit table
| Area | Route | Purpose | API / hook sources | Loading / error handling | Safety badge | Empty state quality | Visual consistency | Missing integration / note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dashboard | `#dashboard` | Command landing page | `useAlerts`, `useIncidents`, `useCases`, `useMetrics`, `useMapState`, `useDroneSimulation`, analytics preview APIs | Existing polling plus drawer errors | Partial before Phase 47, improved in header copy | Honest | Improved with new shell | Added review queue, operations timeline, tactical scene |
| AnalyticsPage | `#analytics` | KPI and trend review | analytics APIs | Existing | No dedicated safety badge | Depends on existing components | Inherited shell now consistent | Future deeper chart polish still possible |
| MapOperationsPage | `#map-operations` | GIS overlays and spatial operations | `useGisMap`, `useCameraGeoProfiles` | Existing | Indirect via copy | Existing | Improved with command header | Additional overlay polish can continue in Phase 48 |
| InvestigationWorkspacePage | `#investigation` | Path reconstruction and hypothesis review | `useInvestigation` | Existing | Yes | Honest | Improved with command header | Can still gain richer step icons and low-confidence warnings |
| DroneSimulationPage | `#drone-simulation` | Live simulated drone runtime | `useDroneSimulation` | Existing | Yes | Honest | Improved with command header | Uses real simulator data only |
| DroneMissionPlannerPage | `#drone-mission-planner` | Mission planning and monitoring | `useDroneMissions` | Existing | Yes | Honest | Improved with command header | API does not yet expose a global active-session summary cleanly |
| DroneFusionPage | `#drone-fusion` | Cross-source drone + fixed camera review | `useDroneFusion` | Existing plus WS status | Yes | Honest | Reworked | Route wiring closed in Phase 47 |
| DroneOperationsHub | `#drone-operations` | Unified drone demo page | `useDroneSimulation`, `useDroneMissions`, `useDroneFusion`, `useRuntimeStatus` | Yes | Yes | Honest | New | Added for FYP demo |
| CasesPage | `#cases` | Case intake and review | `useCases`, `useCaseEnrichment` | Existing | LLM safety badge present | Honest | Improved by shell | Could still gain dedicated drawer tabs |
| UploadedVideoAnalysisPage | `#uploaded-video-analysis` | Offline uploaded video workflows | uploaded video APIs / existing page hook | Existing | Existing page-specific copy | Honest | Improved by shell | Could still gain tighter timeline-to-case linking visuals |
| ModelGovernancePage | `#model-governance` | Registry, limitations, drift, rollback | `useModelGovernance` | Existing | Badge language added by header | Honest | Improved with header | Future table polish still possible |
| IdentityPage | `#identities` | Identity workflows | identity hooks / APIs | Existing | Existing safe backend constraints | Depends on data | Improved by shell | Could still use dedicated candidate review queue visualization |
| SystemHealthPage | `#system` | Runtime and subsystem health | metrics and health endpoints | Existing | N/A | Honest | Improved by shell | Global runtime strip now reduces fragmentation |
| Sidebar / navigation | all | Primary navigation and route discovery | `commandNavigation.js`, `useAuth`, `useRuntimeStatus` | N/A | N/A | N/A | Reworked | Now grouped, RBAC-aware, and badge-capable |

## Findings
- The pre-Phase 47 app had strong page-level functionality but lacked a unified operational shell.
- Drone Fusion existed but route wiring was incomplete.
- Several pages had good data fidelity but inconsistent hierarchy, navigation language, and operator workflow continuity.
- Safe wording existed in multiple areas but did not yet have a frontend static check.
- Runtime and review state were too distributed to sell a single command-center story for demo use.

## Fixed gaps in Phase 47
- Introduced a command-center shell with grouped navigation, runtime strip, command palette, and status bar.
- Wired `#drone-fusion` and added `#drone-operations`.
- Added a unified review queue and operations timeline.
- Added command headers to core drone, map, investigation, and governance pages.
- Added a frontend safe wording check script.
