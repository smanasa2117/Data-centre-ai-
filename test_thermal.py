from backend import db
from backend.services import thermal_engine as te

def test_rack07_is_hottest_and_critical(fresh):
    r = te.rank_all()
    assert r[0]["rack_id"] == "R07" and r[0]["level"] == "Critical"
    assert 0 <= r[0]["score"] <= 100 and r[0]["confidence_level"] == "High"

def test_normal_scenario_has_no_critical(fresh):
    fresh("normal")
    assert all(e["level"] != "Critical" for e in te.rank_all())

def test_stale_and_mismatched_telemetry_lowers_confidence(fresh):
    fresh("stale_sensor")
    assert te.estimate("R11")["confidence"] < 80 and any(i["code"] == "stale" for i in te.estimate("R11")["issues"])
    assert any(i["code"] == "power_util_mismatch" for i in te.estimate("R03")["issues"])
    assert any(a["type"] == "data_quality" for a in te.alerts())

def test_missing_telemetry_is_reported_not_invented(fresh):
    db.run("DELETE FROM telemetry WHERE rack_id='R01'")
    e = te.estimate("R01")
    assert e["score"] is None and e["confidence"] == 0

def test_unknown_rack(fresh):
    assert "error" in te.estimate("R99")

def test_score_is_monotonic_in_inlet_temp(fresh):
    a = te.estimate("R05", overrides={"inlet_temp": 22})["score"]
    b = te.estimate("R05", overrides={"inlet_temp": 30})["score"]
    assert b > a
