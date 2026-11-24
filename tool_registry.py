"""Maps natural-language intents to MCP tools (documentation + used by the UI help panel)."""
INTENTS = {
    "rank":        ["estimate_thermal_stress"],
    "investigate": ["estimate_thermal_stress", "get_rack_telemetry", "get_workload_status", "get_cooling_unit_status",
                    "get_equipment_history", "find_similar_incidents", "open_incident", "find_suitable_cluster",
                    "simulate_incident", "request_operator_approval"],
    "placement":   ["find_suitable_cluster", "compare_resource_costs"],
    "move":        ["simulate_incident", "request_operator_approval"],
    "cooling_fail": ["get_cooling_unit_status", "get_equipment_history", "simulate_incident", "request_operator_approval"],
    "maintenance": ["get_equipment_history", "get_cooling_unit_status"],
    "resource":    ["get_energy_metrics", "compare_resource_costs"],
    "audit":       ["verify_audit_chain", "get_audit_log"],
}
EXAMPLES = [
    "Which GPU rack is experiencing the greatest thermal stress?",
    "Why is Rack 07 overheating?",
    "Which cluster is most suitable for LLM-TRAIN-04?",
    "What would happen if we moved LLM-TRAIN-04 to Cluster B?",
    "What workloads could be moved if cooling unit CU-A1 becomes unavailable?",
    "What maintenance history is associated with CU-A1?",
    "Compare energy and carbon cost for LLM-TRAIN-04",
    "Verify the audit trail",
]
