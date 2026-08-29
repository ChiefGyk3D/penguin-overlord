# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression test: the runners' DATA_DIR expression had an operator-precedence
bug — `a or b if cond else c` — that silently ignored the DATA_DIR env var
whenever /app/data didn't exist."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

RUNNERS = ["xkcd_runner.py", "comics_runner.py"]


@pytest.mark.parametrize("runner", RUNNERS)
def test_data_dir_env_var_is_respected(runner, tmp_path):
    """Import the runner module with DATA_DIR set and read back its value."""
    code = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location('runner_mod', r'{REPO_ROOT}/penguin-overlord/{runner}'); "
        "mod = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(mod); "
        "print(mod.DATA_DIR)"
    )
    env = dict(os.environ, DATA_DIR=str(tmp_path / "custom-data"))
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=env,
        cwd=REPO_ROOT / "penguin-overlord",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == str(tmp_path / "custom-data")
