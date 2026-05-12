# Command Center UI Overhaul

Date completed: May 12, 2026

## Route map
- `#dashboard`
- `#analytics`
- `#system`
- `#live-streams`
- `#uploaded-video-analysis`
- `#alerts`
- `#incidents`
- `#map-operations`
- `#investigation`
- `#drone-operations`
- `#drone-simulation`
- `#drone-mission-planner`
- `#drone-fusion`
- `#cases`
- `#identities`
- `#osint-enrichment`
- `#model-governance`

## Design system
- New shell:
  `frontend/src/components/layout/CommandCenterShell.jsx`
- New sidebar:
  `frontend/src/components/layout/CommandSidebar.jsx`
- New top bar:
  `frontend/src/components/layout/CommandTopBar.jsx`
- New status bar:
  `frontend/src/components/layout/CommandStatusBar.jsx`
- Shared page header:
  `frontend/src/components/layout/CommandPageHeader.jsx`
- Shared section wrapper:
  `frontend/src/components/layout/CommandSection.jsx`
- Theme tokens:
  `frontend/src/styles/commandCenterTheme.js`
- Command-center stylesheet:
  `frontend/src/styles/commandCenter.css`

Visual direction:
- dark tactical command center
- glass-like high-contrast panels
- disciplined status colors
- compact intelligence layout
- reduced-motion aware interactions

## Key operator upgrades
- Grouped navigation with RBAC-aware visibility.
- Runtime status strip spanning backend, database, redis, GIS, drone runtime, drone mission, fusion, investigation, governance, and LLM when authorized.
- `Ctrl+K` command palette with route search and safe API-backed result sections.
- New Drone Operations Hub for FYP walkthroughs.
- Unified review queue for cross-page operator action.
- Tactical operations timeline that merges alerts, cases, drone mission state, fusion timeline signals, uploaded video sessions, and investigation hypotheses.

## Drone workflows
- `#drone-operations` for overview and demo control flow.
- `#drone-simulation` for live simulator-backed observation state.
- `#drone-mission-planner` for mission authoring and monitoring.
- `#drone-fusion` for correlation review with safe wording and simulated-source labeling.

## Safety language
- Added `scripts/check_frontend_safe_wording.py`.
- Removed forbidden certainty phrases from frontend source.
- Kept explicit simulated-source labeling and operator-review caveats.
