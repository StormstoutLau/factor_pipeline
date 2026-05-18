# -*- coding: utf-8 -*-
"""
流水线执行报告生成模块

提供结构化执行报告、性能摘要和数据血缘追踪功能。
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import time
import json

from .types import StepExecutionRecord, PipelineExecutionSummary


@dataclass
class PipelineExecutionReport:
    """流水线执行报告
    
    记录完整的流水线执行过程，包括每步的输入/输出、耗时、缺失率变化等。
    支持生成 Markdown、JSON 和纯文本格式的报告。
    
    Attributes
    ----------
    pipeline_name : str
        流水线名称
    pipeline_version : str
        流水线版本
    start_time : float
        开始时间戳
    end_time : float
        结束时间戳
    steps : list[StepExecutionRecord]
        步骤执行记录列表
    classification_results : dict | None
        分类结果（v2.0 智能流水线）
    """
    
    pipeline_name: str = "factor_pipeline"
    pipeline_version: str = "2.0.0"
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    steps: list[StepExecutionRecord] = field(default_factory=list)
    classification_results: Optional[dict[str, Any]] = None
    
    @property
    def total_duration_ms(self) -> float:
        """总执行时长（毫秒）"""
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000
    
    @property
    def total_duration_sec(self) -> float:
        """总执行时长（秒）"""
        return self.total_duration_ms / 1000
    
    @property
    def success(self) -> bool:
        """是否全部成功"""
        return all(step.get('error') is None for step in self.steps)
    
    @property
    def step_count(self) -> int:
        """步骤数量"""
        return len(self.steps)
    
    def add_step(self, record: StepExecutionRecord) -> None:
        """添加步骤执行记录"""
        self.steps.append(record)
    
    def finalize(self) -> None:
        """标记执行完成"""
        self.end_time = time.time()
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            'pipeline_name': self.pipeline_name,
            'pipeline_version': self.pipeline_version,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_duration_ms': self.total_duration_ms,
            'total_duration_sec': self.total_duration_sec,
            'success': self.success,
            'step_count': self.step_count,
            'steps': self.steps,
            'classification_results': self.classification_results,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """生成 JSON 格式报告"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)
    
    def to_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            f"# Pipeline Execution Report: {self.pipeline_name}",
            f"",
            f"**Version**: {self.pipeline_version}",
            f"**Status**: {'✅ Success' if self.success else '❌ Failed'}",
            f"**Duration**: {self.total_duration_sec:.3f}s",
            f"**Steps**: {self.step_count}",
            f"",
            f"## Steps Execution",
            f"",
            f"| Step | Type | Time (ms) | Input Shape | Output Shape | Missing Δ | Status |",
            f"|------|------|-----------|-------------|--------------|-----------|--------|",
        ]
        
        for step in self.steps:
            name = step.get('step_name', 'N/A')
            step_type = step.get('step_type', 'N/A')
            time_ms = step.get('execution_time_ms', 0)
            input_shape = step.get('input_shape', ('-', '-'))
            output_shape = step.get('output_shape', ('-', '-'))
            missing_before = step.get('input_missing_rate', 0)
            missing_after = step.get('output_missing_rate', 0)
            missing_delta = missing_after - missing_before
            error = step.get('error')
            status = '❌ Error' if error else '✅ OK'
            
            lines.append(
                f"| {name} | {step_type} | {time_ms:.2f} | "
                f"{input_shape} | {output_shape} | "
                f"{missing_delta:+.4f} | {status} |"
            )
        
        lines.extend([
            f"",
            f"## Performance Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Duration | {self.total_duration_sec:.3f}s |",
            f"| Average Step Time | {self.total_duration_sec / max(self.step_count, 1):.3f}s |",
            f"| Success Rate | {sum(1 for s in self.steps if not s.get('error'))}/{self.step_count} |",
        ])
        
        if self.classification_results:
            lines.extend([
                f"",
                f"## Classification Results",
                f"",
                f"```json",
                f"{json.dumps(self.classification_results, indent=2, ensure_ascii=False)}",
                f"```",
            ])
        
        return '\n'.join(lines)
    
    def to_text(self) -> str:
        """生成纯文本格式报告"""
        lines = [
            f"Pipeline: {self.pipeline_name} (v{self.pipeline_version})",
            f"Status: {'SUCCESS' if self.success else 'FAILED'}",
            f"Duration: {self.total_duration_sec:.3f}s",
            f"Steps: {self.step_count}",
            "-" * 60,
        ]
        
        for i, step in enumerate(self.steps, 1):
            name = step.get('step_name', 'N/A')
            time_ms = step.get('execution_time_ms', 0)
            error = step.get('error')
            status = 'FAIL' if error else 'OK'
            lines.append(f"  {i}. {name}: {time_ms:.2f}ms [{status}]")
            if error:
                lines.append(f"     Error: {error}")
        
        return '\n'.join(lines)


class PerformanceProfiler:
    """性能分析器
    
    收集并分析流水线各步骤的性能指标。
    """
    
    def __init__(self):
        self._records: list[dict[str, Any]] = []
    
    def record(self, step_name: str, step_type: str, 
               duration_ms: float, input_shape: tuple, output_shape: tuple) -> None:
        """记录性能数据"""
        self._records.append({
            'step_name': step_name,
            'step_type': step_type,
            'duration_ms': duration_ms,
            'input_shape': input_shape,
            'output_shape': output_shape,
            'timestamp': time.time(),
        })
    
    def get_summary(self) -> dict[str, Any]:
        """获取性能摘要"""
        if not self._records:
            return {}
        
        total_time = sum(r['duration_ms'] for r in self._records)
        times = [r['duration_ms'] for r in self._records]
        
        return {
            'total_steps': len(self._records),
            'total_time_ms': total_time,
            'avg_time_ms': total_time / len(self._records),
            'max_time_ms': max(times),
            'min_time_ms': min(times),
            'slowest_step': max(self._records, key=lambda r: r['duration_ms'])['step_name'],
            'fastest_step': min(self._records, key=lambda r: r['duration_ms'])['step_name'],
        }
    
    def get_bottlenecks(self, threshold_percent: float = 20.0) -> list[dict[str, Any]]:
        """获取瓶颈步骤（耗时超过总时间的阈值百分比）"""
        if not self._records:
            return []
        
        total_time = sum(r['duration_ms'] for r in self._records)
        threshold_ms = total_time * (threshold_percent / 100)
        
        return [
            {
                'step_name': r['step_name'],
                'duration_ms': r['duration_ms'],
                'percentage': (r['duration_ms'] / total_time) * 100,
            }
            for r in self._records
            if r['duration_ms'] >= threshold_ms
        ]
