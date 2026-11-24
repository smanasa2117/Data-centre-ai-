# DataCenter Guardian AI

MCP-powered operations coordinator for AI data centres. Five specialised **MCP servers** expose 18 tools; an AI agent calls them,
correlates the results and returns explainable, simulated, **operator-approved** recommendations. Everything runs on a synthetic facility
(16 GPU racks, 4 clusters, 4 cooling units, 12 workloads). **No real equipment is controlled.**

## Quick start
```bash
pip install -r requirements.txt
./run.sh                 # dashboard at http://localhost:5000   (reseeds a fresh demo state on every start)
python demo_cli.py       # same Rack 07 workflow in the terminal
python -m pytest tests   # 31 tests
```
Optional LLM mode: `export ANTHROPIC_API_KEY=...` (see `agent/llm.py`). Without a key the agent runs in **demo mode**: a deterministic planner
picks MCP tools and composes the answer only from returned tool data (cannot hallucinate; works offline).

## Layout
| Path | What |
|---|---|
| `mcp_servers/` | Thermal, Compute, Maintenance, Resource, Approval & Simulation MCP servers (stdio) |
| `backend/services/` | `thermal_engine` (stress score), `workload_matcher` (hard checks + weighted score), `investigator`, `incident_simulator`, `resource_model` |
| `backend/seed.py` | deterministic synthetic data + 4 scenarios; `backend/app.py` Flask API |
| `agent/` | MCP hub (real MCP client), orchestrator, optional LLM adapter |
| `frontend/` | dashboard (no build step) |
| `tests/` | thermal, matching, simulation/approval/audit, MCP + agent tests |

## Demo script (3-4 min)
1. **Overview** - R07 is Critical (74.7), cluster A has negative thermal headroom.  2. **AI Assistant** - "Why is Rack 07 overheating?" and show the live MCP trace (10 calls).
3. **Workload Matching** - LLM-TRAIN-04: Cluster B recommended, Cluster C excluded by hard checks; switch profile to *green*.
4. **Simulation & Approval** - simulate the move, approve/reject.  5. **Audit Trail** - verify the hash chain.  Switch **Scenario** to `stale_sensor` to show uncertainty handling.

## Features beyond the original brief
Scoring profiles (balanced / thermal-first / green), score-contribution bars, cascading evacuation plan for a cooling-unit outage (priority-ordered, capacity-aware),
telemetry confidence scoring, tamper-evident SHA-256 hash-chained audit log, re-validation of destinations at approval time, four injectable scenarios,
incident report export (.md), carbon/water/cost trade-off table, rack drill-down with trend charts.

## Honest scope notes
* Thresholds, weights, WUE/carbon/PUE factors are **illustrative prototype values**, not facility-validated limits.
* Stack differs from the brief's suggestion: **Flask** (not FastAPI) and a **vanilla-JS dashboard with SVG charts** (not React/Tailwind/Recharts) because the build environment could not install packages. The API is plain JSON, so a React front end can be dropped in.
* The optional LLM path needs internet and an API key and was not exercised in the offline build; demo mode is the tested default.
* Brief's worked example lists Cluster A = 67.5; with the stated weights it is **69.0** (B = 87.0 is correct). Tests use 69.0.
