"""Flask API + static dashboard. Operator-initiated actions go through the MCP hub (and are audited);
read-only dashboard refreshes read the simulated DB directly."""
import atexit, json, os, sys
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import db, seed as seedmod
from backend.services import thermal_engine as te, workload_matcher as wm, resource_model as rm
from agent.mcp_hub import MCPHub
from agent.orchestrator import Agent
from agent import llm as llmmod
from agent.tool_registry import EXAMPLES

app = Flask(__name__, static_folder=str(ROOT / "frontend"), static_url_path="")
from backend.config import DB_PATH
if not os.path.exists(DB_PATH) or not os.environ.get("GUARDIAN_KEEP_DB"):
    seedmod.seed()          # fresh, repeatable demo state on every start (set GUARDIAN_KEEP_DB=1 to keep data)
hub = MCPHub(); atexit.register(hub.close)
agent = Agent(hub, llmmod.from_env())

def err(msg, code=400): return jsonify({"error": msg}), code

@app.get("/")
def index(): return send_from_directory(app.static_folder, "index.html")

@app.get("/api/overview")
def overview():
    clusters = []
    for c in db.q("SELECT * FROM clusters"):
        sm = te.cluster_summary(c["cluster_id"])
        racks = []
        for r in db.q("SELECT * FROM racks WHERE cluster_id=?", (c["cluster_id"],)):
            e = te.estimate(r["rack_id"]); h = te.get_history(r["rack_id"], 1)
            last = h[-1] if h else {}
            racks.append({"rack_id": r["rack_id"], "score": e["score"], "level": e["level"], "confidence": e["confidence_level"],
                          "util": last.get("gpu_utilisation"), "power_kw": last.get("power_kw"), "inlet": last.get("inlet_temp"),
                          "max_kw": r["max_kw"], "issues": [i["detail"] for i in e["issues"]],
                          "workloads": [w["workload_id"] for w in db.q("SELECT workload_id FROM workloads WHERE rack_id=?", (r["rack_id"],))]})
        units = db.q("SELECT * FROM cooling_units WHERE cluster_id=?", (c["cluster_id"],))
        clusters.append({**c, **sm, "racks": racks, "units": units})
    alerts = te.alerts()
    allr = [r for c in clusters for r in c["racks"]]
    return jsonify({"clusters": clusters, "alerts": alerts,
                    "kpis": {"racks": len(allr), "critical": sum(r["level"] == "Critical" for r in allr),
                             "elevated": sum(r["level"] == "Elevated" for r in allr),
                             "gpus_free": sum(c["available_gpus"] for c in clusters), "gpus_total": sum(c["total_gpus"] for c in clusters),
                             "it_load_kw": round(sum(c["load_kw"] for c in clusters)),
                             "pending_approvals": db.q("SELECT COUNT(*) n FROM approvals WHERE decision='pending'", one=True)["n"]},
                    "workloads": db.q("SELECT * FROM workloads ORDER BY cluster_id,rack_id"),
                    "scenario": getattr(app, "scenario", "rack07_incident"), "scenarios": seedmod.SCENARIOS,
                    "llm": bool(agent.llm)})

@app.get("/api/rack/<rack_id>")
def rack(rack_id):
    e = te.estimate(rack_id)
    if "error" in e: return err(e["error"], 404)
    h = te.get_history(rack_id, 48)
    return jsonify({"estimate": e, "history": h, "trend": te.inlet_trend_c_per_hour(h[-12:]),
                    "unit": db.q("SELECT cu.* FROM cooling_units cu JOIN racks r ON r.cooling_unit=cu.unit_id WHERE r.rack_id=?", (rack_id,), one=True)})

@app.post("/api/chat")
def chat():
    b = request.get_json(force=True)
    msg = (b.get("message") or "").strip()
    if not msg: return err("message required")
    return jsonify(agent.handle(msg, b.get("profile", "balanced")))

@app.post("/api/placement")
def placement():
    b = request.get_json(force=True)
    args = {k: b[k] for k in ("workload_id", "gpu_required", "memory_required", "priority", "deadline_hours", "est_hours", "density", "arch", "profile", "exclude_cluster") if k in b and b[k] not in ("", None)}
    trace = []
    r = hub.call("find_suitable_cluster", args, trace)
    out = {"placement": r, "trace": trace}
    if "error" not in r and (b.get("workload_id") or b.get("gpu_required")):
        spec = r["workload"]
        out["resource"] = hub.call("compare_resource_costs", {"workload_id": b.get("workload_id"), "gpu_required": spec["gpu_required"],
                                                              "est_hours": spec["est_hours"], "density": spec["density"]}, trace)
    return jsonify(out)

@app.post("/api/simulate")
def simulate():
    b = request.get_json(force=True); trace = []
    r = hub.call("simulate_incident", {k: b.get(k) for k in ("kind", "workload_id", "destination_cluster", "unit_id", "profile")}, trace)
    if "error" in r: return jsonify({"error": r["error"], "trace": trace}), 400
    return jsonify({"simulation": r, "trace": trace})

@app.post("/api/approval/request")
def approval_request():
    trace = []; r = hub.call("request_operator_approval", {"simulation_id": request.get_json(force=True).get("simulation_id")}, trace)
    return (jsonify({**r, "trace": trace}), 400) if "error" in r else jsonify({**r, "trace": trace})

@app.post("/api/approval/decide")
def approval_decide():
    b = request.get_json(force=True); trace = []
    r = hub.call("record_approved_action", {"approval_id": b.get("approval_id"), "decision": b.get("decision"),
                                            "operator": b.get("operator") or "operator", "note": b.get("note") or ""}, trace)
    return (jsonify({**r, "trace": trace}), 400) if "error" in r else jsonify({**r, "trace": trace})

@app.get("/api/approvals")
def approvals():
    rows = db.q("SELECT a.*,s.proposed_action,s.result FROM approvals a JOIN simulations s USING(simulation_id) ORDER BY a.timestamp DESC, a.approval_id")
    for r in rows:
        res = json.loads(r.pop("result")); r["risks"] = res.get("risks", []); r["kind"] = res.get("kind"); r["moves"] = res.get("moves", [])
        r["safe_to_apply"] = res.get("safe_to_apply")
    return jsonify({"approvals": rows})

@app.get("/api/audit")
def audit():
    rows = db.q("SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT ?", (int(request.args.get("limit", 60)),))
    return jsonify({"entries": rows, "verify": db.verify_audit_chain()})

@app.post("/api/scenario")
def scenario():
    name = request.get_json(force=True).get("scenario", "rack07_incident")
    if name not in seedmod.SCENARIOS: return err("unknown scenario")
    r = seedmod.seed(name); app.scenario = name
    return jsonify(r)

@app.get("/api/examples")
def examples(): return jsonify({"examples": EXAMPLES, "tools": [{"name": n, "server": t["server"], "description": t["description"]} for n, t in hub.tools.items()]})

@app.get("/api/export/incident/<rack_id>")
def export_incident(rack_id):
    r = agent.report(rack_id)
    md = (r.get("data") or {}).get("markdown")
    return (md or "No report"), 200, {"Content-Type": "text/markdown; charset=utf-8", "Content-Disposition": f"attachment; filename=incident_{rack_id}.md"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
