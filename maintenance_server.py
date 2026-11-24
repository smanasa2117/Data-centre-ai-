"""Maintenance MCP - equipment history, cooling-unit state, incident memory and maintenance requests."""
import uuid
from _common import make_server, audited
from backend import db
from backend.services import investigator as inv
mcp = make_server("maintenance-mcp")
S = audited("maintenance")

@mcp.tool()
@S
def get_equipment_history(unit_id: str) -> dict:
    """Maintenance records for a cooling unit, newest first."""
    if not db.q("SELECT 1 FROM cooling_units WHERE unit_id=?", (unit_id,)): return {"error": f"Unknown cooling unit {unit_id}"}
    return {"unit_id": unit_id, "records": db.q("SELECT * FROM maintenance_records WHERE unit_id=? ORDER BY date DESC", (unit_id,))}

@mcp.tool()
@S
def get_cooling_unit_status(unit_id: str = "", rack_id: str = "") -> dict:
    """Cooling-unit status, performance (0-1), vibration (mm/s) and temperature, by unit id or by the rack it serves."""
    if rack_id:
        r = db.q("SELECT cooling_unit FROM racks WHERE rack_id=?", (rack_id,), one=True)
        if not r: return {"error": f"Unknown rack {rack_id}"}
        unit_id = r["cooling_unit"]
    rows = db.q("SELECT * FROM cooling_units" + (" WHERE unit_id=?" if unit_id else ""), (unit_id,) if unit_id else ())
    return {"units": rows} if rows else {"error": f"Unknown cooling unit {unit_id}"}

@mcp.tool()
@S
def find_similar_incidents(tags: str) -> dict:
    """Closed historical incidents whose signature overlaps the comma-separated tags (e.g. 'high_util,cooling_perf_drop')."""
    return {"similar": inv.similar_incidents([t.strip() for t in tags.split(",") if t.strip()])}

@mcp.tool()
@S
def open_incident(rack_id: str, severity: str, evidence: str, signature: str = "") -> dict:
    """Open an incident record for a rack."""
    iid = f"INC-{uuid.uuid4().hex[:6].upper()}"
    db.run("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?)", (iid, rack_id, severity, evidence, "open", signature, None, db.iso(db.now())))
    return {"incident_id": iid, "status": "open"}

@mcp.tool()
@S
def create_maintenance_request(unit_id: str, description: str, priority: str = "normal", operator_confirmed: bool = False) -> dict:
    """Prepare a maintenance request. Without operator_confirmed=true it is only a DRAFT and is not submitted."""
    if not db.q("SELECT 1 FROM cooling_units WHERE unit_id=?", (unit_id,)): return {"error": f"Unknown cooling unit {unit_id}"}
    rid = f"MR-{uuid.uuid4().hex[:5].upper()}"
    status = "open" if operator_confirmed else "draft_awaiting_operator_confirmation"
    db.run("INSERT INTO maintenance_records VALUES(?,?,?,?,?,?)", (rid, unit_id, f"[{priority}] {description}", db.iso(db.now())[:10], status, "requested"))
    return {"record_id": rid, "status": status}

if __name__ == "__main__": mcp.run("stdio")
