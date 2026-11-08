"""Lets `python -m pytest` run the script-style tests in this folder.

Each test_*.py is a standalone script that exits non-zero on failure, so
pytest runs each one in a subprocess as a single test item instead of
importing it.
"""
import os
import subprocess
import sys

import pytest


def pytest_collect_file(parent, file_path):
    if file_path.name.startswith("test_") and file_path.suffix == ".py":
        return ScriptFile.from_parent(parent, path=file_path)


class ScriptFile(pytest.File):
    def collect(self):
        yield ScriptItem.from_parent(self, name=self.path.stem)


class ScriptItem(pytest.Item):
    def runtest(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, str(self.path)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env)
        if r.returncode != 0:
            raise AssertionError(r.stdout[-3000:] + r.stderr[-3000:])

    def reportinfo(self):
        return self.path, 0, self.name
