import os, sys, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["GUARDIAN_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")   # before any backend import
import pytest
from backend import seed

@pytest.fixture()
def fresh():
    def _f(scenario="rack07_incident"): return seed.seed(scenario)
    _f(); return _f
