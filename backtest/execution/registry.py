# -*- coding: utf-8 -*-
"""v3.8.0 模型注册表（进程内字典，形状照抄 PluginRegistry）。

实施依据：EXECUTION §2.3；重名注册抛 ValueError（不静默覆盖）。
"""
from typing import Dict, List

__all__ = ["ModelRegistry"]


class ModelRegistry(object):
    """按 ``model.name`` 装配的进程内注册表。"""

    def __init__(self):
        self._models = {}  # type: Dict[str, object]

    def register(self, model: object) -> None:
        """注册模型；重名直接报错，避免静默覆盖。"""
        name = getattr(model, "name", None)
        if not name:
            raise ValueError("模型缺少 name 属性")
        if name in self._models:
            raise ValueError("模型名重复: %s" % name)
        self._models[name] = model

    def get(self, name: str) -> object:
        """按名取模型；缺失抛 KeyError。"""
        if name not in self._models:
            raise KeyError("未注册模型: %s" % name)
        return self._models[name]

    def names(self) -> List[str]:
        """已注册模型名（插入顺序）。"""
        return list(self._models.keys())
