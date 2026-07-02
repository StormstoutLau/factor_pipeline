# -*- coding: utf-8 -*-
"""
性能监控模块
提供性能指标收集和报告
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict


@dataclass
class PerformanceMetric:
    """性能指标"""

    function_name: str = ""
    execution_time: float = 0.0
    memory_usage: float = 0.0
    call_count: int = 0


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics: Dict[str, PerformanceMetric] = defaultdict(lambda: PerformanceMetric())

    def monitor(self, func: Callable) -> Callable:
        """监控装饰器"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.time() - start_time
                metric = self.metrics[func.__name__]
                metric.function_name = func.__name__
                metric.execution_time += elapsed
                metric.call_count += 1

        return wrapper

    def get_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        return {
            name: {
                "total_time": metric.execution_time,
                "avg_time": metric.execution_time / metric.call_count if metric.call_count > 0 else 0,
                "total_memory": metric.memory_usage,
                "call_count": metric.call_count,
            }
            for name, metric in self.metrics.items()
        }

    def reset(self) -> None:
        """重置监控数据"""
        self.metrics.clear()
