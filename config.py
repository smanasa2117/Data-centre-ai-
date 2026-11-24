"""Central configuration. All thresholds are ILLUSTRATIVE prototype values,
not universal safety limits - validate against a real facility before use."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("GUARDIAN_DB", str(ROOT / "data" / "guardian.db"))

# --- thermal stress model -------------------------------------------------
# each factor maps a raw reading linearly from (low -> 0) to (high -> 100)
STRESS_RANGES = {
    "inlet_temp":   (21.0, 29.0),   # deg C
    "gpu_util":     (50.0, 100.0),  # %
    "power_load":   (0.40, 1.00),   # fraction of rack max kW
    "cooling_def":  (0.0, 0.5),     # 1 - cooling performance
    "trend":        (0.0, 3.0),     # deg C per hour inlet rise
}
STRESS_WEIGHTS = {"inlet_temp": 0.30, "gpu_util": 0.15, "power_load": 0.20,
                  "cooling_def": 0.20, "trend": 0.15}
STRESS_LEVELS = [(70, "Critical"), (50, "Elevated"), (30, "Watch"), (0, "Normal")]
STALE_AFTER_MIN = 10          # telemetry older than this is "stale"

# --- workload matching ----------------------------------------------------
PROFILES = {   # weights for G,T,P,C,D,E  (E = energy/carbon, optional)
    "balanced":      dict(G=0.30, T=0.25, P=0.20, C=0.15, D=0.10, E=0.00),
    "thermal_first": dict(G=0.20, T=0.40, P=0.15, C=0.15, D=0.10, E=0.00),
    "green":         dict(G=0.25, T=0.20, P=0.15, C=0.10, D=0.10, E=0.20),
}
POWER_SAFETY_MARGIN = 1.10    # require 10 % margin above estimated draw
TARIFF_PER_KWH = 0.11         # USD, synthetic
