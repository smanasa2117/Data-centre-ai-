"""Thermal MCP - rack telemetry and thermal-stress estimates."""
from _common import make_server, audited
from backend.services import thermal_engine as te
mcp = make_server("thermal-mcp")
S = audited("thermal")

@mcp.tool()
@S
def get_rack_telemetry(rack_id: str, history_points: int = 12) -> dict:
    """Latest telemetry for a rack (GPU utilisation, power, inlet/outlet temperature) plus recent history and data-quality flags."""
    ctx = te.get_rack_context(rack_id)
    if not ctx: return {"error": f"Unknown rack {rack_id}"}
    rack, unit = ctx
    hist = te.get_history(rack_id, max(1, min(history_points, 96)))
    conf, issues = te.data_quality(hist, unit, rack)
    return {"rack_id": rack_id, "cluster_id": rack["cluster_id"], "cooling_unit": rack["cooling_unit"], "max_kw": rack["max_kw"],
            "latest": hist[-1] if hist else None, "history": hist, "inlet_trend_c_per_hour": te.inlet_trend_c_per_hour(hist),
            "data_confidence": conf, "data_issues": issues}

@mcp.tool()
@S
def estimate_thermal_stress(rack_id: str = "") -> dict:
    """Thermal-stress score (0-100) with evidence and confidence. Leave rack_id empty to rank all racks."""
    if rack_id: return te.estimate(rack_id)
    return {"ranking": [{k: e[k] for k in ("rack_id", "cluster_id", "score", "level", "confidence_level")} for e in te.rank_all()]}

@mcp.tool()
@S
def get_thermal_alerts() -> dict:
    """Active thermal and data-quality alerts with evidence and suggested next steps."""
    return {"alerts": te.alerts()}

if __name__ == "__main__": mcp.run("stdio")
