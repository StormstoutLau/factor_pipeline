# -*- coding: utf-8 -*-
"""v3.8.0 E0 — 无 pyarrow 导入冒烟（T380-56，design §16.5）。

红形态：子进程 ``ModuleNotFoundError: backtest.execution.core.impact``。
"""
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_CODE = r"""
import sys

class _Blocker(object):
    def find_spec(self, name, path=None, target=None):
        if name == "pyarrow" or name.startswith("pyarrow."):
            raise ImportError("pyarrow blocked by smoke test")
        return None

sys.meta_path.insert(0, _Blocker())
sys.path.insert(0, r"%(parent)s")
sys.path.insert(0, r"%(repo)s")

import backtest.execution.core.impact as impact
from backtest.execution.shell.loaders import has_pyarrow

assert has_pyarrow() is False, "has_pyarrow() 应为 False"
assert hasattr(impact, "SqrtImpact"), "impact 导入不完整"
print("SMOKE_OK")
"""


def test_import_without_pyarrow():
    """T380-56: 阻断 pyarrow 后 core 可导入且 has_pyarrow() 为 False。"""
    code = _CODE % {"parent": _REPO.parent, "repo": _REPO}
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=str(_REPO),
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "SMOKE_OK" in proc.stdout
