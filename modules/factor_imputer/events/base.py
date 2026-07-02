# -*- coding: utf-8 -*-
"""
事件系统模块
提供发布-订阅模式的事件总线
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List


@dataclass
class Event:
    """事件基类"""

    type: str
    timestamp: datetime
    data: Dict[str, Any]


class EventBus:
    """事件总线"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """订阅事件"""
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """取消订阅"""
        with self._lock:
            if event_type in self._listeners:
                if callback in self._listeners[event_type]:
                    self._listeners[event_type].remove(callback)

    def publish(self, event: Event) -> None:
        """发布事件"""
        listeners = []
        with self._lock:
            listeners = self._listeners.get(event.type, []).copy()

        for callback in listeners:
            try:
                callback(event)
            except Exception as e:
                # 记录错误但不中断其他监听器
                import logging

                logging.getLogger("factor_imputer").error(f"事件处理失败: {e}", exc_info=True)

    def get_listeners(self, event_type: str) -> List[Callable]:
        """获取事件监听器"""
        with self._lock:
            return self._listeners.get(event_type, []).copy()


# 全局事件总线
_global_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    return _global_event_bus
