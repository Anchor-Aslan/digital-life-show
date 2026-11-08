"""Run the full test suite. Standard library only.

Each file in tests/ is a self-contained script: it prints a check-by-check
report and exits non-zero if any check fails. This runner executes every
script in a fresh process and summarises the results.

    python run_tests.py          # summary
    python run_tests.py -v       # also print each script's own report
"""
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
COUNT = re.compile(r"通过\s*(\d+)\s*项，失败\s*(\d+)\s*项")


def main():
    verbose = "-v" in sys.argv[1:]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    failed, checks = [], 0
    for path in TESTS:
        name = os.path.basename(path)
        r = subprocess.run([sys.executable, path], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           env=env, cwd=ROOT)
        n = sum(int(a) + int(b) for a, b in COUNT.findall(r.stdout))
        checks += n
        ok = r.returncode == 0
        print("  %s  %-40s %s" % ("PASS" if ok else "FAIL", name,
                                  ("%d checks" % n) if n else ""))
        if verbose or not ok:
            print(r.stdout + r.stderr)
        if not ok:
            failed.append(name)
    print("-" * 60)
    print("%d/%d test files passed, %d individual checks"
          % (len(TESTS) - len(failed), len(TESTS), checks))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
