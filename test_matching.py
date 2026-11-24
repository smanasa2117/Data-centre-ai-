from backend import db
from backend.services import workload_matcher as wm

def spec(**kw):
    base = dict(gpu_required=32, memory_required=40, density="medium", priority="normal", deadline_hours=48, est_hours=12)
    base.update(kw); return wm.load_spec(spec=base)

def test_rack07_workload_prefers_cluster_b(fresh):
    r = wm.find_suitable_cluster(wm.load_spec("LLM-TRAIN-04"))
    assert r["recommended"] == "B" and r["ranking"][0]["score"] > next(x for x in r["ranking"] if x["cluster_id"] == "A")["score"]

def test_ranking_is_reproducible(fresh):
    a = wm.find_suitable_cluster(wm.load_spec("LLM-TRAIN-04")); b = wm.find_suitable_cluster(wm.load_spec("LLM-TRAIN-04"))
    assert [(x["cluster_id"], x["score"]) for x in a["ranking"]] == [(x["cluster_id"], x["score"]) for x in b["ranking"]]

def test_insufficient_gpus_excludes_cluster(fresh):
    r = wm.find_suitable_cluster(spec(gpu_required=150, memory_required=20, density="low"))
    ex = {x["cluster_id"]: x["exclusion_reasons"] for x in r["excluded"]}
    assert any("insufficient GPUs" in s for s in ex["D"])   # D has only 108 free

def test_insufficient_memory_excludes(fresh):
    r = wm.find_suitable_cluster(spec(memory_required=100))
    assert "D" in [x["cluster_id"] for x in r["ranking"]] and all(x["cluster_id"] != "A" for x in r["ranking"])

def test_insufficient_power_excludes(fresh):
    db.run("UPDATE clusters SET power_cap_kw=power_cap_kw-300 WHERE cluster_id='B'")
    r = wm.find_suitable_cluster(spec(gpu_required=64, memory_required=20, density="medium"))
    assert any(x["cluster_id"] == "B" and any("power" in s for s in x["exclusion_reasons"]) for x in r["excluded"])

def test_high_score_never_overrides_hard_constraint(fresh):
    # make cluster B score highly on everything but give it too few GPUs: it must still be excluded
    db.run("UPDATE clusters SET available_gpus=4 WHERE cluster_id='B'")
    r = wm.find_suitable_cluster(spec(gpu_required=64, memory_required=40, density="medium"))
    assert "B" not in [x["cluster_id"] for x in r["ranking"]]

def test_air_cooled_cluster_rejects_high_density(fresh):
    r = wm.find_suitable_cluster(spec(gpu_required=16, memory_required=16, density="high"))
    assert any(x["cluster_id"] == "C" and any("cooling incompatible" in s for s in x["exclusion_reasons"]) for x in r["excluded"])

def test_deadline_infeasible_excluded(fresh):
    r = wm.find_suitable_cluster(spec(deadline_hours=5, est_hours=20))
    assert any("deadline" in " ".join(x["exclusion_reasons"]) for x in r["excluded"])

def test_profiles_change_weights_not_eligibility(fresh):
    a = wm.find_suitable_cluster(wm.load_spec("LLM-TRAIN-04"), "balanced"); g = wm.find_suitable_cluster(wm.load_spec("LLM-TRAIN-04"), "green")
    assert {x["cluster_id"] for x in a["ranking"]} == {x["cluster_id"] for x in g["ranking"]}
    assert abs(sum(wm.PROFILES["green"].values()) - 1) < 1e-9 and abs(sum(wm.PROFILES["balanced"].values()) - 1) < 1e-9

def test_score_formula_matches_spec_example():
    # worked example from the project brief. NOTE: the brief printed 67.5 for Cluster A, but the stated weights give 69.0.
    w = wm.PROFILES["balanced"]
    s = lambda g, t, p, c, d: w["G"]*g + w["T"]*t + w["P"]*p + w["C"]*c + w["D"]*d
    assert round(s(95, 40, 65, 60, 85), 1) == 69.0
    assert round(s(85, 90, 85, 90, 85), 1) == 87.0
