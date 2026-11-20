# -*- coding: utf-8 -*-
"""v3.8.0 E0 — 耦合元测试（T380-53 ~ T380-55）。

红形态：``AssertionError``（core 文件缺失）。
"""
import ast
from pathlib import Path

_CORE = (Path(__file__).resolve().parents[1]
         / "backtest" / "execution" / "core")
_EXPECTED = {
    "__init__.py", "impact.py", "spread.py", "classification.py",
    "decay.py", "bootstrap.py",
}
_BANNED_MODULES = {"os", "pathlib", "logging", "pyarrow", "duckdb", "pandas"}


def _sources():
    assert _CORE.is_dir(), "core 目录不存在: %s" % _CORE
    files = {p.name for p in _CORE.glob("*.py")}
    missing = _EXPECTED - files
    assert not missing, "core 模块缺失: %s" % sorted(missing)
    return [p for p in sorted(_CORE.glob("*.py")) if p.name != "__init__.py"]


def test_core_has_no_io():
    """T380-53: core 无 IO / 无 pandas / 无 open()。"""
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in _BANNED_MODULES, (
                        "%s: import %s" % (path.name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                top = (node.module or "").split(".")[0]
                assert top not in _BANNED_MODULES, (
                    "%s: from %s" % (path.name, node.module))
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id == "open":
                    raise AssertionError("%s: 调用 open()" % path.name)


def test_core_no_reverse_dependency():
    """T380-54: core 不 import shell / runner。"""
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for bad in ("from ..shell", "import ..shell", "from ..runner"):
            assert bad not in text, "%s 含反向依赖 %s" % (path.name, bad)


def test_core_all_bounded():
    """T380-55: 每个 core 模块 __all__ <= 5 且无 '*'。"""
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        alls = [n for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__all__"
                        for t in n.targets)]
        assert alls, "%s 缺少 __all__" % path.name
        names = ast.literal_eval(alls[0].value)
        assert isinstance(names, list) and len(names) <= 5, (
            "%s __all__ 超限: %s" % (path.name, names))
        assert "*" not in names, "%s __all__ 含 '*'" % path.name
