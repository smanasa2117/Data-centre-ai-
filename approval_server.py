"""Approval & Simulation MCP - what-if simulation, human approval, tamper-evident audit trail."""
from _common import make_server, audited
from backend import db
from backend.services import incident_simulator as sim
mcp = make_server("approval-simulation-mcp")
S = audited("approval")

@mcp.tool()
@S
def simulate_incident(kind: str, workload_id: str = "", destination_cluster: str = "", unit_id: str = "",
                      incident_id: str = "", profile: str = "balanced") -> dict:
    """What-if simulation. kind='workload_move' (workload_id + destination_cluster) or kind='cooling_failure' (unit_id).
    Nothing real is executed."""
    if kind == "workload_move":
        if not workload_id or not destination_cluster: return {"error": "workload_move needs workload_id and destination_cluster"}
        return sim.simulate_move(workload_id, destination_cluster, incident_id or None, profile)
    if kind == "cooling_failure":
        if not unit_id: return {"error": "cooling_failure needs unit_id"}
        return sim.simulate_cooling_failure(unit_id, incident_id or None, profile)
    return {"error": "kind must be 'workload_move' or 'cooling_failure'"}

@mcp.tool()
@S
def request_operator_approval(simulation_id: str) -> dict:
    """Create a pending approval for a simulation. The agent can only REQUEST approval; a human decides."""
    return sim.request_approval(simulation_id)

@mcp.tool()
@S
def record_approved_action(approval_id: str, decision: str, operator: str = "operator", note: str = "") -> dict:
    """Record the operator's decision ('approved'|'rejected'). Approval only edits the SIMULATED state, after re-validation."""
    return sim.record_decision(approval_id, decision, operator, note)

@mcp.tool()
@S
def get_audit_log(limit: int = 25) -> dict:
    """Most recent audit entries (tool calls, simulations, decisions)."""
    return {"entries": db.q("SELECT log_id,event_type,tool_name,details,timestamp,hash FROM audit_logs ORDER BY log_id DESC LIMIT ?", (limit,))}

@mcp.tool()
@S
def verify_audit_chain() -> dict:
    """Verify the SHA-256 hash chain of the audit log to detect tampering."""
    return db.verify_audit_chain()

if __name__ == "__main__": mcp.run("stdio")
