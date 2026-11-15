# Brief: Literature Review Assistant UI polish

Target: Polish the research-ops dashboard so it reads as a finished product. Stack: React 19, Vite 7, Tailwind 4, FastAPI backend.
Size: Light. Hard cap 2 hours from 2026-11-15 03:00 UTC.
References: cook/refs/R01 to R04 (Linear, Rayyan, Elicit, Covidence landing pages, collected locally, own style at that quality).
Shots: S01 setup `/` at 390x844 and 1440x900 light+dark; S02 run chrome `/run/demo-ui-01/activity` same viewports (VITE_UI_DEMO).
Bar: layout 9 | type 9 | color 9 | components 9 | polish 9 | motion 9.
Calibration offset: none yet.
Rules: default slop ban list. Project overrides: Inter and violet accent per docs/UI.md and tokens.css. Extra bans: none. Must include: phone and wide, light and dark.
Time: cap 2h. Started: 2026-11-15 03:00 UTC.
Deliverable: working build, cook stills, PR to main.
Permissions: commit each round yes, push yes, deploy no, publish no, prod data no.
Judges: 2 fresh critics per round if available; else self-scored (logged).
Gate: Parth not watching per round; no ping.

## Decisions

- Intake: all defaults from factory worker prompt (Light, 2h cap, 9/10 bar, no references from Parth).
- References: collected 4 live products in systematic-review / research-ops space before round 1.
- Violet accent kept per project design (not treated as slop).
- VITE_UI_DEMO fixtures for cook screenshots without paid LLM calls or missing run DBs on VPS.
- VITE_STUB_LLM short-circuits config generation stream in the browser when demo/stub flags are set.

Parth's words: "Make the UI look and feel like a finished, polished product."