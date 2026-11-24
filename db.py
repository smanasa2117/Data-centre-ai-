import json, sqlite3, hashlib, datetime as dt
from contextlib import contextmanager
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS clusters(cluster_id TEXT PRIMARY KEY,name TEXT,gpu_model TEXT,gpu_mem_gb INT,total_gpus INT,
  available_gpus INT,power_cap_kw REAL,cooling_type TEXT,rack_max_kw REAL,kw_per_gpu REAL,pue REAL,carbon_g_kwh REAL,speed_factor REAL,status TEXT);
CREATE TABLE IF NOT EXISTS racks(rack_id TEXT PRIMARY KEY,cluster_id TEXT,location TEXT,status TEXT,gpus INT,max_kw REAL,cooling_unit TEXT);
CREATE TABLE IF NOT EXISTS telemetry(id INTEGER PRIMARY KEY AUTOINCREMENT,rack_id TEXT,gpu_utilisation REAL,inlet_temp REAL,
  outlet_temp REAL,power_kw REAL,timestamp TEXT);
CREATE INDEX IF NOT EXISTS ix_tel ON telemetry(rack_id,timestamp);
CREATE TABLE IF NOT EXISTS workloads(workload_id TEXT PRIMARY KEY,cluster_id TEXT,rack_id TEXT,gpu_required INT,memory_required REAL,
  priority TEXT,deadline_hours REAL,est_hours REAL,density TEXT,arch TEXT,power_kw REAL,status TEXT,kind TEXT);
CREATE TABLE IF NOT EXISTS cooling_units(unit_id TEXT PRIMARY KEY,cluster_id TEXT,status TEXT,performance REAL,vibration REAL,
  temperature REAL,capacity_kw REAL,updated TEXT);
CREATE TABLE IF NOT EXISTS maintenance_records(record_id TEXT PRIMARY KEY,unit_id TEXT,description TEXT,date TEXT,status TEXT,kind TEXT);
CREATE TABLE IF NOT EXISTS incidents(incident_id TEXT PRIMARY KEY,rack_id TEXT,severity TEXT,evidence TEXT,status TEXT,
  signature TEXT,resolution TEXT,opened TEXT);
CREATE TABLE IF NOT EXISTS simulations(simulation_id TEXT PRIMARY KEY,incident_id TEXT,proposed_action TEXT,result TEXT,created TEXT);
CREATE TABLE IF NOT EXISTS approvals(approval_id TEXT PRIMARY KEY,simulation_id TEXT,decision TEXT,operator TEXT,note TEXT,timestamp TEXT);
CREATE TABLE IF NOT EXISTS audit_logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT,tool_name TEXT,details TEXT,
  timestamp TEXT,prev_hash TEXT,hash TEXT);
"""

def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

def iso(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ")

def parse(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)

def connect():
    c = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=15000")
    return c

@contextmanager
def conn():
    c = connect()
    try: yield c
    finally: c.close()

def q(sql, args=(), one=False):
    with conn() as c:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    return (rows[0] if rows else None) if one else rows

def run(sql, args=()):
    with conn() as c: c.execute(sql, args)

def init():
    with conn() as c: c.executescript(SCHEMA)

# ---- tamper-evident audit log (hash chain) --------------------------------
def audit(event_type, tool_name="", details=None):
    details = json.dumps(details if details is not None else {}, default=str, sort_keys=True)
    ts = iso(now())
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT hash FROM audit_logs ORDER BY log_id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "GENESIS"
        h = hashlib.sha256(f"{prev}|{event_type}|{tool_name}|{details}|{ts}".encode()).hexdigest()
        cur = c.execute("INSERT INTO audit_logs(event_type,tool_name,details,timestamp,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                  (event_type, tool_name, details, ts, prev, h))
        c.execute("COMMIT")
    return cur.lastrowid

def verify_audit_chain():
    prev, n = "GENESIS", 0
    for r in q("SELECT * FROM audit_logs ORDER BY log_id"):
        exp = hashlib.sha256(f"{prev}|{r['event_type']}|{r['tool_name']}|{r['details']}|{r['timestamp']}".encode()).hexdigest()
        if r["prev_hash"] != prev or r["hash"] != exp:
            return {"valid": False, "broken_at": r["log_id"], "checked": n}
        prev, n = r["hash"], n + 1
    return {"valid": True, "entries": n, "head": prev[:16]}
