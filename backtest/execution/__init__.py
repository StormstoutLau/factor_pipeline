# -*- coding: utf-8 -*-
"""v3.8.0 执行/容量模块（Core/Shell 分层）。

``__all__`` <= 5；需要 IO 的符号用 PEP 562 ``__getattr__`` 懒加载，
保证 ``import backtest.execution`` 不触发 shell/loaders（不依赖 pyarrow）。
"""
__all__ = ["CalibrationConfig", "run_calibration", "CalibrationUnavailable",
           "ModelRegistry", "has_pyarrow"]


def __getattr__(name):
    if name == "run_calibration":
        from .shell.runner import run_calibration
        return run_calibration
    if name == "has_pyarrow":
        from .shell.loaders import has_pyarrow
        return has_pyarrow
    raise AttributeError(name)


from .config import CalibrationConfig          # noqa: E402
from .ports import CalibrationUnavailable      # noqa: E402
from .registry import ModelRegistry            # noqa: E402
