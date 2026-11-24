import json
from backend import db
from backend.services import incident_simulator as sim

def wl(w): return db.q("SELECT * FROM workloads WHERE workload_id=?", (w,), one=True)

def test_move_simulation_improves_source_rack(fresh):
    r = sim.simulate_move("LLM-TRAIN-04", "B")
    s = r["racks"]["source"][0]
    assert s["after"] < s["before"] and r["safe_to_apply"]

def test_reject_records_without_executing(fresh):
    s = sim.simulate_move("LLM-TRAIN-04", "B"); a = sim.request_approval(s["simulation_id"])
    out = sim.record_decision(a["approval_id"], "rejected", "alice", "not now")
    assert out["decision"] == "rejected" and wl("LLM-TRAIN-04")["cluster_id"] == "A"

def test_approve_updates_only_simulated_state(fresh):
    s = sim.simulate_move("LLM-TRAIN-04", "B"); a = sim.request_approval(s["simulation_id"])
    out = sim.record_decision(a["approval_id"], "approved", "bob")
    assert wl("LLM-TRAIN-04")["cluster_id"] == "B" and out["applied_to_simulation"]
    assert db.q("SELECT available_gpus FROM clusters WHERE cluster_id='B'", one=True)["available_gpus"] == 112 - 64

def test_cannot_decide_twice(fresh):
    s = sim.simulate_move("LLM-TRAIN-04", "B"); a = sim.request_approval(s["simulation_id"])
    sim.record_decision(a["approval_id"], "rejected"); assert "error" in sim.record_decision(a["approval_id"], "approved")

def test_unsafe_move_is_blocked(fresh):
    r = sim.simulate_move("LLM-TRAIN-04", "C")       # memory/cooling/hardware incompatible
    assert not r["safe_to_apply"] and r["risks"][0].startswith("BLOCKED")
    a = sim.request_approval(r["simulation_id"])
    assert "error" in sim.record_decision(a["approval_id"], "approved") and wl("LLM-TRAIN-04")["cluster_id"] == "A"

def test_stale_simulation_revalidated_at_execution(fresh):
    s = sim.simulate_move("LLM-TRAIN-04", "B"); a = sim.request_approval(s["simulation_id"])
    db.run("UPDATE clusters SET available_gpus=2 WHERE cluster_id='B'")      # state changed after simulation
    out = sim.record_decision(a["approval_id"], "approved")
    assert "error" in out and wl("LLM-TRAIN-04")["cluster_id"] == "A"

def test_cooling_failure_evacuates_by_priority(fresh):
    r = sim.simulate_cooling_failure("CU-A1")
    assert r["affected_racks"] == ["R05", "R06", "R07", "R08"] and r["moves"][0]["workload_id"] == "LLM-TRAIN-04"
    assert all(m["to"] != "A" for m in r["moves"]) and not r["unplaced"]

def test_cooling_failure_reports_unplaceable_when_capacity_exhausted(fresh):
    db.run("UPDATE clusters SET available_gpus=0 WHERE cluster_id!='A'")
    r = sim.simulate_cooling_failure("CU-A1")
    assert len(r["unplaced"]) == 4 and not r["safe_to_apply"]

def test_audit_chain_detects_tampering(fresh):
    sim.simulate_move("LLM-TRAIN-04", "B")
    assert db.verify_audit_chain()["valid"]
    db.run("UPDATE audit_logs SET details='{}' WHERE log_id=2")
    assert not db.verify_audit_chain()["valid"]
