import pytest
from agent.mcp_hub import MCPHub
from agent.orchestrator import Agent
from backend import db

@pytest.fixture(scope="module")
def hub():
    h = MCPHub(); yield h; h.close()

def test_all_five_servers_expose_tools(hub):
    assert {t["server"] for t in hub.tools.values()} == {"thermal", "compute", "maintenance", "resource", "approval"}
    for t in ("get_rack_telemetry", "estimate_thermal_stress", "get_gpu_capacity", "find_suitable_cluster", "get_workload_status", "get_equipment_history",
              "create_maintenance_request", "get_energy_metrics", "compare_resource_costs", "simulate_incident", "request_operator_approval", "record_approved_action"):
        assert t in hub.tools

def test_agent_rack07_workflow_uses_real_tools(hub, fresh):
    r = Agent(hub).handle("Why is Rack 07 overheating?")
    tools = [t["tool"] for t in r["trace"]]
    for t in ("estimate_thermal_stress", "get_workload_status", "get_equipment_history", "find_suitable_cluster", "simulate_incident", "request_operator_approval"):
        assert t in tools
    assert "unverified" in r["answer"] and "not a confirmed diagnosis" in r["answer"]
    assert r["data"]["approval"]["approval_id"] and db.verify_audit_chain()["valid"]

def test_agent_cannot_approve_actions(hub, fresh):
    assert "record_approved_action" not in [t["tool"] for t in Agent(hub).handle("Why is Rack 07 overheating?")["trace"]]

def test_tool_failure_is_reported_not_invented(hub, fresh):
    out = hub.call("get_rack_telemetry", {"rack_id": "R99"}); assert "error" in out
    out = hub.call("no_such_tool", {}); assert "error" in out

def test_unavailable_server_shows_failure_in_answer(fresh):
    h = MCPHub(); h.tool_server.pop("estimate_thermal_stress")       # simulate Thermal MCP being down
    r = Agent(h).handle("Which rack has the greatest thermal stress?"); h.close()
    assert "Tool failures" in r["answer"] and "R07" not in r["answer"].split("Tool failures")[0]

def test_audit_records_tool_calls(hub, fresh):
    hub.call("estimate_thermal_stress", {"rack_id": "R07"})
    assert db.q("SELECT 1 FROM audit_logs WHERE event_type='tool_call' AND tool_name='estimate_thermal_stress'")
