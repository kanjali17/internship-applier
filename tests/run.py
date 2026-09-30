"""Minimal test runner (no pytest needed): python3 tests/run.py"""
import importlib, pathlib, sys, traceback
here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import conftest  # noqa: F401  (sets example mode + path)
fails = n = 0
for f in sorted(here.glob("test_*.py")):
    m = importlib.import_module(f.stem)
    for name in [x for x in dir(m) if x.startswith("test_")]:
        n += 1
        try:
            getattr(m, name)()
        except Exception:
            fails += 1; print(f"FAIL {f.stem}.{name}"); traceback.print_exc(limit=1)
print(f"{n - fails}/{n} passed")
sys.exit(1 if fails else 0)
