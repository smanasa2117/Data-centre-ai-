"""AI operations agent. Two modes:
 * demo (default, no API key needed): a deterministic planner chooses MCP tools from the request, calls them,
   and composes the answer ONLY from returned tool data - so nothing can be hallucinated.
 * llm (optional): set ANTHROPIC_API_KEY to let an LLM plan tool calls and explain the results (agent/llm.py)."""
import re
from backend.services import investigator as inv
from backend.config import PROFILES
from .prompts import SYSTEM_PROMPT

RACK_RE = re.compile(r"\brack\s*0?(\d{1,2})\b|\bR0?(\d{1,2})\b", re.I)
UNIT_RE = re.compile(r"\bCU-[A-D]\d\b", re.I)
WL_RE = re.compile(r"\b([A-Z]{2,}(?:-[A-Z]+)*-\d{2})\b")
CL_RE = re.compile(r"\bcluster\s*([A-D])\b", re.I)

def _rack(msg):
    m = RACK_RE.search(msg)
    return f"R{int(m.group(1) or m.group(2)):02d}" if m else None

class Agent:
    def __init__(self, hub, llm=None):
        self.hub, self.llm = hub, llm

    # ------------------------------------------------------------------ entry
    def handle(self, message, profile="balanced"):
        trace = []
        if self.llm:
            try: return self.llm.run(self.hub, message, trace, SYSTEM_PROMPT)
            except Exception as e: trace.append({"server": "llm", "tool": "llm_error", "args": {}, "ms": 0, "status": "error", "note": str(e)})
        return self._demo(message, profile, trace)

    def _demo(self, msg, profile, trace):
        low = msg.lower()
        rack, unit = _rack(msg), (UNIT_RE.search(msg).group(0).upper() if UNIT_RE.search(msg) else None)
        wl = WL_RE.search(msg.upper()); wl = wl.group(1) if wl else None
        cl = CL_RE.search(msg); cl = cl.group(1).upper() if cl else None
        if "green" in low or "carbon" in low and "profile" in low: profile = "green"
        c = lambda t, a=None: self.hub.call(t, a, trace)
        approve = re.search(r"\bSIM-[A-F0-9]{6}\b", msg.upper())

        if approve and "approv" in low:
            return self._pack(trace, "approval", self._approval_only(c, approve.group(0)))
        if "audit" in low or "tamper" in low:
            return self._pack(trace, "audit", self._audit(c))
        if wl and cl and re.search(r"move|moved|migrat|what if|what would happen|shift", low):
            return self._pack(trace, "simulation", self._move(c, wl, cl, profile))
        if (unit or "cooling" in low or "cooler" in low) and re.search(r"unavailable|fail|down|offline|outage|lost|loss", low):
            u = unit or "CU-A1"
            return self._pack(trace, "simulation", self._cooling_failure(c, u, profile))
        if re.search(r"maintenance|history|service record", low) and (unit or rack):
            return self._pack(trace, "maintenance", self._maintenance(c, unit, rack))
        if rack and re.search(r"why|overheat|hot|investigat|temperature|cooling problem|diagnos|incident|check", low):
            return self._pack(trace, "investigation", self._investigate(c, rack, profile))
        if re.search(r"energy|carbon|cost|water|power use|co2|emission", low):
            return self._pack(trace, "resource", self._resource(c, wl))
        if not wl and re.search(r"stress|hottest|greatest|ranking|rank racks", low):
            return self._pack(trace, "rank", self._rank(c, focus=rack))
        if wl or re.search(r"suitable|which cluster|placement|where should|schedule", low) or re.search(r"\d+\s*gpus?", low):
            return self._pack(trace, "placement", self._placement(c, msg, wl, profile))
        if rack:
            return self._pack(trace, "rank", self._rank(c, focus=rack))
        if re.search(r"stress|hottest|hot\b|greatest|rank|most|thermal|temperature|status|overview", low):
            return self._pack(trace, "rank", self._rank(c))
        return self._pack(trace, "help", {"answer": "I can investigate racks, rank thermal stress, find thermal-aware workload placements, "
                                                   "simulate moves or cooling failures, review maintenance history and compare energy/carbon cost. "
                                                   "Try one of the example questions.", "data": {}})

    def _pack(self, trace, kind, out):
        out["kind"], out["trace"] = kind, trace
        out["mode"] = "demo (deterministic planner, answer composed from MCP tool results only)"
        errs = [t for t in trace if t["status"] == "error"]
        if errs: out["answer"] += "\n\n**Tool failures:** " + "; ".join(f"{t['tool']}" for t in errs) + ". Results that depend on them are not shown rather than guessed."
        return out

    # ------------------------------------------------------------------ skills
    def _rank(self, c, focus=None):
        r = c("estimate_thermal_stress")
        if "error" in r: return {"answer": f"Could not retrieve thermal data: {r['error']}", "data": {}}
        top = r["ranking"][:5]
        lines = [f"**{x['rack_id']}** (Cluster {x['cluster_id']}): {x['score']}/100, {x['level']}, confidence {x['confidence_level']}" for x in top]
        first = top[0]
        detail = c("estimate_thermal_stress", {"rack_id": focus or first["rack_id"]})
        ev = "; ".join(f"{e['factor']} {e['reading']}" for e in detail.get("evidence", [])[:3])
        ans = (f"Highest thermal stress: **{(focus or first['rack_id'])}**.\n\nTop racks:\n- " + "\n- ".join(lines) +
               f"\n\nWhy {detail['rack_id']}: {ev}.\n\n_Scores are prototype estimates from synthetic telemetry._")
        return {"answer": ans, "data": {"ranking": r["ranking"], "detail": detail}}

    def report(self, rack):
        """Read-only investigation (no incident/simulation/approval side effects) used for report export."""
        return self._investigate(lambda t, a=None: self.hub.call(t, a, []), rack, 'balanced', act=False)

    def _investigate(self, c, rack, profile, act=True):
        est = c("estimate_thermal_stress", {"rack_id": rack})
        if "error" in est: return {"answer": est["error"], "data": {}}
        tel = c("get_rack_telemetry", {"rack_id": rack, "history_points": 12})
        wls = c("get_workload_status", {"rack_id": rack}).get("workloads", [])
        unit = (c("get_cooling_unit_status", {"rack_id": rack}).get("units") or [None])[0]
        maint = c("get_equipment_history", {"unit_id": unit["unit_id"]}).get("records", []) if unit else []
        hist = tel.get("history", [])
        tags = inv.derive_tags(est, unit, maint, hist)
        similar = c("find_similar_incidents", {"tags": ",".join(tags)}).get("similar", []) if tags else []
        rep = inv.build_report(rack, est, wls, unit, maint, similar, hist)
        data = {"report": rep, "estimate": est, "markdown": inv.to_markdown(rep)}
        parts = [f"**{rep['title']}** - {rep['status']}.",
                 "**Observed evidence**\n" + "\n".join(f"- {o['fact']}" for o in rep["observed_evidence"][:5]),
                 "**Possible contributing factors (unverified)**\n" + "\n".join(f"{i}. {h['factor']} ({h['support']} support)" for i, h in enumerate(rep["possible_factors"], 1))]
        if act and est["level"] in ("Critical", "Elevated"):
            c("open_incident", {"rack_id": rack, "severity": est["level"].lower(), "evidence": "; ".join(x["factor"] + " " + x["reading"] for x in est["evidence"][:3]), "signature": ",".join(tags)})
            main = max(wls, key=lambda w: w["power_kw"]) if wls else None
            if main:
                pl = c("find_suitable_cluster", {"workload_id": main["workload_id"], "profile": profile})
                data["placement"] = pl
                alt = next((r for r in pl.get("ranking", []) if not r["is_current"]), None)
                if alt:
                    sim = c("simulate_incident", {"kind": "workload_move", "workload_id": main["workload_id"], "destination_cluster": alt["cluster_id"]})
                    if "error" not in sim:
                        ap = c("request_operator_approval", {"simulation_id": sim["simulation_id"]})
                        data["simulation"], data["approval"] = sim, ap
                        r0 = sim["racks"]["source"][0]
                        parts.append(f"**Suggested response (simulation only):** move {main['workload_id']} to Cluster {alt['cluster_id']} (score {alt['score']}). "
                                     f"Simulated {rack} stress {r0['before']} -> {r0['after']}. Approval **{ap.get('approval_id')}** is awaiting an operator decision.")
                        if r0["after"] >= 30: parts.append(f"Note: {rack} stays at {r0['level_after']} after the move, which points to the cooling unit itself, not just the workload.")
        parts.append("**Recommended next steps**\n" + "\n".join(f"- {s}" for s in rep["recommended_next_steps"]))
        parts.append(f"_{rep['caveat']}_")
        return {"answer": "\n\n".join(parts), "data": data}

    def _placement(self, c, msg, wl, profile):
        args = {"profile": profile}
        if wl: args["workload_id"] = wl
        else:
            g = re.search(r"(\d+)\s*gpus?", msg, re.I); m = re.search(r"(\d+)\s*gb", msg, re.I)
            if not g: return {"answer": "Tell me which workload (e.g. LLM-TRAIN-04) or its size, e.g. '32 GPUs, 40 GB per GPU'.", "data": {}}
            args.update(gpu_required=int(g.group(1)), memory_required=float(m.group(1)) if m else 16,
                        density="high" if re.search(r"train|high", msg, re.I) else "medium")
        r = c("find_suitable_cluster", args)
        if "error" in r: return {"answer": r["error"], "data": {}}
        if not r["ranking"]:
            return {"answer": "No cluster passes the hard eligibility checks:\n- " + "\n- ".join(f"Cluster {x['cluster_id']}: " + "; ".join(x["exclusion_reasons"]) for x in r["excluded"]), "data": {"placement": r}}
        b = r["ranking"][0]
        lines = [f"{x['rank']}. **Cluster {x['cluster_id']}** score {x['score']}" + (" (current)" if x["is_current"] else "") +
                 f" - thermal headroom {x['details']['thermal_headroom_kw']} kW, power headroom {x['details']['power_headroom_kw']} kW, cooling {x['details']['cooling_type']}" for x in r["ranking"]]
        exc = [f"Cluster {x['cluster_id']}: " + "; ".join(x["exclusion_reasons"]) for x in r["excluded"]]
        ans = (f"Recommended: **Cluster {b['cluster_id']}** (score {b['score']}, profile *{profile}*).\n\n" + "\n".join(lines) +
               ("\n\n**Excluded (hard checks):**\n- " + "\n- ".join(exc) if exc else "") +
               f"\n\nFormula: `{r['formula']}`. The ranking comes from the deterministic matcher, not the language model."
               + ("\n\n" + " ".join(r["notes"]) if r["notes"] else ""))
        data = {"placement": r}
        if wl:
            data["resource"] = c("compare_resource_costs", {"workload_id": wl})
        return {"answer": ans, "data": data}

    def _move(self, c, wl, dest, profile):
        sim = c("simulate_incident", {"kind": "workload_move", "workload_id": wl, "destination_cluster": dest, "profile": profile})
        if "error" in sim: return {"answer": sim["error"], "data": {}}
        ap = c("request_operator_approval", {"simulation_id": sim["simulation_id"]})
        s0, cl = sim["racks"]["source"][0], sim["clusters"]
        ans = (f"Simulation **{sim['simulation_id']}**: move {wl} from Cluster {sim['from']} to Cluster {dest}.\n\n"
               f"- Source rack {s0['rack_id']}: stress {s0['before']} ({s0['level_before']}) -> {s0['after']} ({s0['level_after']})\n"
               f"- Cluster {sim['from']} thermal headroom {cl[sim['from']]['before']['thermal_headroom_kw']} -> {cl[sim['from']]['after']['thermal_headroom_kw']} kW\n"
               f"- Cluster {dest} thermal headroom {cl[dest]['before']['thermal_headroom_kw']} -> {cl[dest]['after']['thermal_headroom_kw']} kW; hottest rack -> {cl[dest]['after']['max_rack_stress']}\n\n"
               f"**Risks:** " + " ".join(sim["risks"]) + f"\n\nApproval **{ap.get('approval_id')}** is awaiting an operator decision. {sim['disclaimer']}")
        return {"answer": ans, "data": {"simulation": sim, "approval": ap}}

    def _cooling_failure(self, c, unit, profile):
        st = c("get_cooling_unit_status", {"unit_id": unit})
        sim = c("simulate_incident", {"kind": "cooling_failure", "unit_id": unit, "profile": profile})
        if "error" in sim: return {"answer": sim["error"], "data": {}}
        ap = c("request_operator_approval", {"simulation_id": sim["simulation_id"]}) if sim["moves"] else {}
        mv = "\n".join(f"- {m['workload_id']} ({m['priority']}, {m['gpus']} GPUs): Cluster {m['from']} -> **Cluster {m['to']}** (score {m['score']})" for m in sim["moves"])
        un = ("\n\n**Could not be re-placed:** " + ", ".join(u["workload_id"] for u in sim["unplaced"])) if sim["unplaced"] else ""
        ans = (f"If **{unit}** becomes unavailable: racks {', '.join(sim['affected_racks'])} in Cluster {sim['cluster']} lose cooling and "
               f"{len(sim['affected_workloads'])} workloads are affected.\n\nProposed evacuation plan (priority order):\n{mv}{un}\n\n"
               + ("Approval **%s** is awaiting an operator decision. " % ap.get("approval_id") if ap else "") + sim["disclaimer"])
        return {"answer": ans, "data": {"simulation": sim, "approval": ap, "unit": st}}

    def _maintenance(self, c, unit, rack):
        if not unit:
            u = c("get_cooling_unit_status", {"rack_id": rack}).get("units", [{}])[0]; unit = u.get("unit_id")
        if not unit: return {"answer": "No cooling unit found.", "data": {}}
        h = c("get_equipment_history", {"unit_id": unit}); st = c("get_cooling_unit_status", {"unit_id": unit})
        if "error" in h: return {"answer": h["error"], "data": {}}
        u = st["units"][0]
        ans = (f"**{unit}** is '{u['status']}' (performance {u['performance']*100:.0f}%, vibration {u['vibration']} mm/s).\n\nMaintenance history:\n" +
               "\n".join(f"- {r['date']} {r['record_id']} [{r['kind']}]: {r['description']}" for r in h["records"]))
        return {"answer": ans, "data": {"history": h, "unit": st}}

    def _resource(self, c, wl):
        if wl:
            r = c("compare_resource_costs", {"workload_id": wl})
            if "error" in r: return {"answer": r["error"], "data": {}}
            rows = "\n".join(f"- Cluster {e['cluster_id']}: {e['runtime_h']} h, {e['facility_kwh']} kWh, ${e['cost_usd']}, {e['carbon_kg']} kgCO2, {e['water_l']} L water" for e in r["estimates"])
            lo = r["lowest"]
            return {"answer": f"Estimated resource cost of {wl} by cluster (synthetic factors):\n{rows}\n\nLowest cost: {lo['cost_usd']}, carbon: {lo['carbon_kg']}, water: {lo['water_l']}, fastest: {lo['runtime_h']}. {r['note']}", "data": {"resource": r}}
        r = c("get_energy_metrics")
        rows = "\n".join(f"- Cluster {m['cluster_id']}: {m['facility_kw']} kW facility load, ${m['cost_per_hour_usd']}/h, {m['carbon_kg_per_hour']} kgCO2/h" for m in r.get("metrics", []))
        return {"answer": "Current energy metrics:\n" + rows, "data": {"metrics": r}}

    def _audit(self, c):
        v = c("verify_audit_chain"); log = c("get_audit_log", {"limit": 8})
        ans = (f"Audit chain is **{'valid' if v.get('valid') else 'BROKEN'}** ({v.get('entries', v.get('checked'))} entries checked)." )
        return {"answer": ans, "data": {"verify": v, "log": log}}

    def _approval_only(self, c, sim_id):
        ap = c("request_operator_approval", {"simulation_id": sim_id})
        if "error" in ap: return {"answer": ap["error"], "data": {}}
        return {"answer": f"Approval **{ap['approval_id']}** created for {sim_id}. Only a human operator can approve or reject it (Simulation & Approval tab).", "data": {"approval": ap}}
