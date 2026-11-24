"""Synthetic data-centre generator. Deterministic (seeded) so demos are repeatable.
Scenarios: rack07_incident (default) | normal | stale_sensor | capacity_crunch"""
import os, random, json, datetime as dt
from . import db
from .config import DB_PATH

SCENARIOS = {
    "rack07_incident": "Rack 07 runs hot: cooling unit CU-A1 degrading while LLM-TRAIN-04 ramps up.",
    "normal": "Healthy facility, all racks within normal operating range.",
    "stale_sensor": "Rack 07 incident plus a stale/missing sensor on R11 and a suspect power sensor on R03.",
    "capacity_crunch": "Rack 07 incident while Clusters B and D are nearly out of free GPUs.",
}

CLUSTERS = [  # id,name,model,mem,cooling,rack_max,kw/gpu,pue,carbon,speed,power_cap
    ("A", "Cluster A", "H100-80GB", 80, "rear_door_hx", 100, 1.00, 1.55, 620, 1.00, 330),
    ("B", "Cluster B", "H100-80GB", 80, "direct_liquid", 130, 1.00, 1.20, 410, 1.00, 440),
    ("C", "Cluster C", "A100-40GB", 40, "air_crah", 50, 0.55, 1.35, 380, 0.60, 150),
    ("D", "Cluster D", "H200-141GB", 141, "hybrid", 110, 1.05, 1.25, 250, 1.25, 380),
]
RACKS = {"C": ["R01", "R02", "R03", "R04"], "A": ["R05", "R06", "R07", "R08"],
         "B": ["R09", "R10", "R11", "R12"], "D": ["R13", "R14", "R15", "R16"]}
HALL = {"C": "Hall 1 / Row 1", "A": "Hall 1 / Row 2", "B": "Hall 2 / Row 1", "D": "Hall 2 / Row 2"}
UNIT = {"A": ("CU-A1", 380), "B": ("CU-B1", 520), "C": ("CU-C1", 170), "D": ("CU-D1", 420)}
SUPPLY = {"rear_door_hx": 19.0, "direct_liquid": 17.5, "air_crah": 20.0, "hybrid": 18.0}
RACK_GPUS = 72

# rack -> (util % now, util % 3h ago)
UTIL = {"R01": (38, 36), "R02": (46, 44), "R03": (52, 50), "R04": (30, 32),
        "R05": (62, 60), "R06": (68, 66), "R07": (94, 76), "R08": (48, 50),
        "R09": (72, 70), "R10": (58, 55), "R11": (66, 64), "R12": (45, 47),
        "R13": (84, 80), "R14": (88, 85), "R15": (81, 78), "R16": (76, 74)}

# workload: id,cluster,rack,gpus,mem/gpu,priority,deadline_h,est_h,density,arch,status,kind
WORKLOADS = [
    ("LLM-TRAIN-04", "A", "R07", 64, 70, "critical", 36, 20, "high", "H100", "running", "LLM training"),
    ("CV-INFER-02", "A", "R05", 24, 20, "normal", 72, 10, "medium", "any", "running", "Computer-vision inference"),
    ("SIM-CFD-01", "A", "R06", 32, 40, "normal", 48, 18, "medium", "any", "running", "Scientific simulation"),
    ("EMB-BATCH-03", "A", "R08", 24, 30, "low", 96, 30, "low", "any", "running", "Embedding batch job"),
    ("LLM-TRAIN-01", "B", "R09", 72, 75, "high", 60, 40, "high", "H100", "running", "LLM training"),
    ("LLM-SERVE-01", "B", "R10", 48, 60, "critical", 999, 999, "medium", "any", "running", "LLM serving"),
    ("VISION-TRAIN-02", "B", "R11", 56, 40, "normal", 72, 30, "high", "any", "running", "Vision model training"),
    ("ETL-BATCH-02", "C", "R01", 24, 16, "low", 120, 24, "low", "any", "running", "Data ETL"),
    ("INFER-SERVE-05", "C", "R02", 36, 24, "high", 999, 999, "low", "any", "running", "Inference serving"),
    ("LLM-FT-03", "D", "R13", 72, 100, "high", 48, 26, "high", "any", "running", "LLM fine-tuning"),
    ("GENAI-SERVE-02", "D", "R14", 72, 90, "critical", 999, 999, "medium", "any", "running", "GenAI serving"),
    ("PHYS-SIM-07", "D", "R15", 36, 60, "normal", 72, 20, "medium", "any", "running", "Physics simulation"),
]

def seed(scenario="rack07_incident", fresh=True):
    if scenario not in SCENARIOS: raise ValueError(f"unknown scenario {scenario}")
    if fresh and os.path.exists(DB_PATH):
        for ext in ("", "-wal", "-shm"):
            try: os.remove(DB_PATH + ext)
            except FileNotFoundError: pass
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db.init()
    rnd = random.Random(2026)
    t_now = db.now()
    healthy = scenario == "normal"
    crunch = scenario == "capacity_crunch"

    with db.conn() as c:
        c.execute("BEGIN")
        for (cid, name, model, mem, cool, rmax, kwg, pue, carb, speed, pcap) in CLUSTERS:
            c.execute("INSERT INTO clusters VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (cid, name, model, mem, 4 * RACK_GPUS, 0, pcap, cool, rmax, kwg, pue, carb, speed, "online"))
            for r in RACKS[cid]:
                c.execute("INSERT INTO racks VALUES(?,?,?,?,?,?,?)",
                          (r, cid, HALL[cid], "active", RACK_GPUS, rmax, UNIT[cid][0]))
        # cooling units
        perf = {"A": 0.60 if not healthy else 0.93, "B": 0.95, "C": 0.90, "D": 0.88}
        vib = {"A": 4.9 if not healthy else 2.1, "B": 2.0, "C": 2.6, "D": 2.4}
        for cid, (uid, cap) in UNIT.items():
            c.execute("INSERT INTO cooling_units VALUES(?,?,?,?,?,?,?,?)",
                      (uid, cid, "degraded" if perf[cid] < 0.75 else "operational", perf[cid], vib[cid],
                       16.0 + (7 if cid == "A" and not healthy else 0) * 0.5 + rnd.random() * 0.4, cap, db.iso(t_now)))
        # workloads
        for (wid, cid, rack, g, mem, pri, dl, est, dens, arch, st, kind) in WORKLOADS:
            kwg = next(x[6] for x in CLUSTERS if x[0] == cid)
            c.execute("INSERT INTO workloads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (wid, cid, rack, g, mem, pri, dl, est, dens, arch, round(g * kwg, 1), st, kind))
        # telemetry: 48 points, 5-minute cadence => 4 h of history
        for cid, racks in RACKS.items():
            cl = next(x for x in CLUSTERS if x[0] == cid)
            rmax, sup = cl[5], SUPPLY[cl[4]]
            for r in racks:
                u_now, u_old = UTIL[r]
                if healthy and r == "R07": u_now, u_old = 60, 58
                if crunch and r in ("R09", "R10", "R11", "R12"): u_now = max(u_now, 78)
                for i in range(48):  # i=47 is latest
                    frac = i / 47
                    ramp = frac ** 2 if r == "R07" and not healthy else frac
                    u = u_old + (u_now - u_old) * ramp + rnd.gauss(0, 1.2)
                    u = max(5, min(99, u))
                    # cooling performance for A degrades over the window; others stable
                    p_t = perf[cid] if not (cid == "A" and not healthy) else 0.95 - (0.95 - perf[cid]) * (frac ** 1.25)
                    load = (0.15 + 0.65 * u / 100)
                    power = rmax * load * (1 + rnd.gauss(0, 0.012))
                    inlet = sup + 14 * (1 - p_t) + 4 * (power / rmax) + rnd.gauss(0, 0.15)
                    outlet = inlet + 6 + 22 * (power / rmax) + rnd.gauss(0, 0.3)
                    ts = t_now - dt.timedelta(minutes=5 * (47 - i)) + dt.timedelta(seconds=0 if i == 47 else 0)
                    if i == 47: ts = t_now
                    row = [r, round(u, 1), round(inlet, 2), round(outlet, 2), round(power, 1), db.iso(ts)]
                    if scenario == "stale_sensor":
                        if r == "R11" and i >= 40: continue            # stale: no new readings for ~35 min
                        if r == "R03" and i == 47: row[4] = round(power * 2.1, 1)   # implausible power
                    c.execute("INSERT INTO telemetry(rack_id,gpu_utilisation,inlet_temp,outlet_temp,power_kw,timestamp) VALUES(?,?,?,?,?,?)", row)
        # maintenance history
        d = lambda days: db.iso(t_now - dt.timedelta(days=days))[:10]
        MR = [
            ("MR-0412", "CU-A1", "Fan module #2 replaced; airflow recalibrated", d(9), "completed", "corrective"),
            ("MR-0377", "CU-A1", "Quarterly filter and coil inspection", d(41), "completed", "preventive"),
            ("MR-0291", "CU-A1", "Coolant loop flush and pressure test", d(118), "completed", "preventive"),
            ("MR-0398", "CU-B1", "CDU pump service, seals replaced", d(55), "completed", "preventive"),
            ("MR-0405", "CU-C1", "Quarterly filter replacement", d(20), "completed", "preventive"),
            ("MR-0388", "CU-D1", "Heat-exchanger descaling", d(66), "completed", "preventive"),
            ("MR-0360", "CU-A1", "Rear-door heat-exchanger hose coupling re-seated", d(210), "completed", "corrective"),
        ]
        c.executemany("INSERT INTO maintenance_records VALUES(?,?,?,?,?,?)", MR)
        # historical incidents (used for pattern matching)
        INC = [
            ("INC-2025-114", "R06", "high", "Inlet +3C after service on rear-door unit, perf drop 14%", "closed",
             "high_util,cooling_perf_drop,recent_maintenance,vibration_high", "Loose hose coupling after service; re-seated, performance restored", d(210)),
            ("INC-2025-131", "R10", "medium", "Rack hot while 72-GPU training job started; cooling normal", "closed",
             "high_util,workload_ramp", "Pure workload heat; job rescheduled to lower-density cluster. No equipment fault", d(150)),
            ("INC-2026-027", "R03", "low", "Inlet reading +6C, power and util flat, outlet normal", "closed",
             "sensor_mismatch,stale_or_noisy", "Inlet sensor drift; sensor replaced", d(95)),
            ("INC-2026-052", "R14", "medium", "Low delta-T with high inlet, recirculation suspected", "closed",
             "low_delta_t,high_inlet,airflow", "Missing blanking panels; airflow containment restored", d(60)),
        ]
        c.executemany("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?)", INC)
        c.execute("COMMIT")
    recompute_clusters()
    if crunch:
        db.run("UPDATE clusters SET available_gpus=MIN(available_gpus,24) WHERE cluster_id IN('B')")
    db.audit("scenario_loaded", "seed", {"scenario": scenario})
    return {"scenario": scenario, "description": SCENARIOS[scenario]}

def recompute_clusters():
    """available_gpus = total - GPUs used by running workloads."""
    for cl in db.q("SELECT cluster_id,total_gpus FROM clusters"):
        used = db.q("SELECT COALESCE(SUM(gpu_required),0) u FROM workloads WHERE cluster_id=? AND status='running'",
                    (cl["cluster_id"],), one=True)["u"]
        db.run("UPDATE clusters SET available_gpus=? WHERE cluster_id=?", (cl["total_gpus"] - used, cl["cluster_id"]))

if __name__ == "__main__":
    import sys
    print(seed(sys.argv[1] if len(sys.argv) > 1 else "rack07_incident"))
