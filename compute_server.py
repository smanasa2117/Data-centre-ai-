"""Compute MCP - GPU capacity, workload status and thermal-aware placement."""
from _common import make_server, audited
from backend import db
from backend.services import workload_matcher as wm
mcp = make_server("compute-mcp")
S = audited("compute")

@mcp.tool()
@S
def get_gpu_capacity(cluster_id: str = "") -> dict:
    """GPU totals/availability, hardware and cooling type per cluster."""
    rows = db.q("SELECT cluster_id,name,gpu_model,gpu_mem_gb,total_gpus,available_gpus,cooling_type,power_cap_kw,status FROM clusters"
                + (" WHERE cluster_id=?" if cluster_id else ""), (cluster_id,) if cluster_id else ())
    return {"clusters": rows} if rows else {"error": f"Unknown cluster {cluster_id}"}

@mcp.tool()
@S
def get_workload_status(workload_id: str = "", rack_id: str = "", cluster_id: str = "") -> dict:
    """Workloads filtered by id, rack or cluster."""
    sql, args, cond = "SELECT * FROM workloads", [], []
    for col, v in (("workload_id", workload_id), ("rack_id", rack_id), ("cluster_id", cluster_id)):
        if v: cond.append(f"{col}=?"); args.append(v)
    rows = db.q(sql + (" WHERE " + " AND ".join(cond) if cond else ""), tuple(args))
    return {"workloads": rows}

@mcp.tool()
@S
def find_suitable_cluster(workload_id: str = "", gpu_required: int = 0, memory_required: float = 0, priority: str = "normal",
                          deadline_hours: float = 48, est_hours: float = 10, density: str = "medium", arch: str = "any",
                          profile: str = "balanced", exclude_cluster: str = "") -> dict:
    """Rank clusters for a workload (existing id, or an ad-hoc spec) using hard eligibility checks plus the transparent
    weighted score S = 0.30G + 0.25T + 0.20P + 0.15C + 0.10D. profile: balanced | thermal_first | green."""
    if workload_id:
        spec = wm.load_spec(workload_id)
        if not spec: return {"error": f"Unknown workload {workload_id}"}
    else:
        if gpu_required <= 0: return {"error": "Provide workload_id, or gpu_required and memory_required"}
        spec = wm.load_spec(spec=dict(gpu_required=gpu_required, memory_required=memory_required, priority=priority,
                                       deadline_hours=deadline_hours, est_hours=est_hours, density=density, arch=arch))
    return wm.find_suitable_cluster(spec, profile, exclude=exclude_cluster or None)

if __name__ == "__main__": mcp.run("stdio")
