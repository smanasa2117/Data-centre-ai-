"""Resource MCP - energy, power, carbon and water estimates."""
from _common import make_server, audited
from backend.services import resource_model as rm, workload_matcher as wm
mcp = make_server("resource-mcp")
S = audited("resource")

@mcp.tool()
@S
def get_energy_metrics(cluster_id: str = "") -> dict:
    """Current IT/facility power, cost, carbon and water estimates per cluster (synthetic factors)."""
    return {"metrics": rm.energy_metrics(cluster_id or None)}

@mcp.tool()
@S
def compare_resource_costs(workload_id: str = "", gpu_required: int = 0, est_hours: float = 10, density: str = "medium") -> dict:
    """Estimated energy, cost, carbon and water of running a workload on each cluster. Shows trade-offs, does not optimise."""
    if workload_id:
        spec = wm.load_spec(workload_id)
        if not spec: return {"error": f"Unknown workload {workload_id}"}
    else:
        if gpu_required <= 0: return {"error": "Provide workload_id or gpu_required"}
        spec = {"workload_id": "AD-HOC", "gpu_required": gpu_required, "est_hours": est_hours, "density": density}
    return rm.compare_costs(spec)

if __name__ == "__main__": mcp.run("stdio")
