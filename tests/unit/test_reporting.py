# -*- coding: utf-8 -*-
"""
报告生成模块单元测试

测试 PipelineExecutionReport 和 PerformanceProfiler 的功能。
"""

import pytest
import time
import json

from factor_pipeline.reporting import PipelineExecutionReport, PerformanceProfiler


class TestPipelineExecutionReport:
    """流水线执行报告测试"""
    
    def test_default_creation(self):
        """测试默认创建"""
        report = PipelineExecutionReport()
        assert report.pipeline_name == "factor_pipeline"
        assert report.pipeline_version == "2.0.0"
        assert report.step_count == 0
        assert report.success is True  # 无步骤时默认为成功
    
    def test_add_step(self):
        """测试添加步骤记录"""
        report = PipelineExecutionReport()
        step = {
            'step_name': 'imputer',
            'step_type': 'imputation',
            'execution_time_ms': 100.0,
            'input_shape': (100, 50),
            'output_shape': (100, 50),
            'input_missing_rate': 0.05,
            'output_missing_rate': 0.0,
        }
        report.add_step(step)
        
        assert report.step_count == 1
        assert report.steps[0]['step_name'] == 'imputer'
    
    def test_success_with_error(self):
        """测试有错误时 success 为 False"""
        report = PipelineExecutionReport()
        step = {
            'step_name': 'imputer',
            'step_type': 'imputation',
            'execution_time_ms': 100.0,
            'error': 'Something went wrong',
        }
        report.add_step(step)
        
        assert report.success is False
    
    def test_finalize(self):
        """测试标记完成"""
        report = PipelineExecutionReport()
        time.sleep(0.01)
        report.finalize()
        
        assert report.end_time > 0
        assert report.total_duration_sec > 0
    
    def test_to_dict(self):
        """测试字典转换"""
        report = PipelineExecutionReport(pipeline_name='test')
        report.add_step({'step_name': 'step1', 'execution_time_ms': 50.0})
        report.finalize()
        
        d = report.to_dict()
        assert d['pipeline_name'] == 'test'
        assert d['step_count'] == 1
        assert 'total_duration_ms' in d
    
    def test_to_json(self):
        """测试 JSON 转换"""
        report = PipelineExecutionReport()
        report.add_step({'step_name': 'step1', 'execution_time_ms': 50.0})
        
        json_str = report.to_json()
        # 验证是有效的 JSON
        parsed = json.loads(json_str)
        assert parsed['pipeline_name'] == 'factor_pipeline'
    
    def test_to_markdown(self):
        """测试 Markdown 生成"""
        report = PipelineExecutionReport()
        report.add_step({
            'step_name': 'imputer',
            'step_type': 'imputation',
            'execution_time_ms': 100.0,
            'input_shape': (100, 50),
            'output_shape': (100, 50),
            'input_missing_rate': 0.05,
            'output_missing_rate': 0.0,
        })
        
        md = report.to_markdown()
        assert '# Pipeline Execution Report' in md
        assert 'imputer' in md
        assert 'imputation' in md
    
    def test_to_text(self):
        """测试纯文本生成"""
        report = PipelineExecutionReport()
        report.add_step({
            'step_name': 'imputer',
            'execution_time_ms': 100.0,
        })
        
        text = report.to_text()
        assert 'Pipeline:' in text
        assert 'imputer' in text
    
    def test_with_classification_results(self):
        """测试包含分类结果"""
        report = PipelineExecutionReport()
        report.classification_results = {
            'pb_factor': {'type': 'static', 'confidence': 0.95},
            'momentum_factor': {'type': 'mixed', 'confidence': 0.87},
        }
        
        md = report.to_markdown()
        assert 'Classification Results' in md


class TestPerformanceProfiler:
    """性能分析器测试"""
    
    def test_empty_profiler(self):
        """测试空分析器"""
        profiler = PerformanceProfiler()
        assert profiler.get_summary() == {}
        assert profiler.get_bottlenecks() == []
    
    def test_record_and_summary(self):
        """测试记录和摘要"""
        profiler = PerformanceProfiler()
        profiler.record('imputer', 'imputation', 100.0, (100, 50), (100, 50))
        profiler.record('standardizer', 'standardization', 50.0, (100, 50), (100, 50))
        
        summary = profiler.get_summary()
        assert summary['total_steps'] == 2
        assert summary['total_time_ms'] == 150.0
        assert summary['avg_time_ms'] == 75.0
        assert summary['max_time_ms'] == 100.0
        assert summary['min_time_ms'] == 50.0
        assert summary['slowest_step'] == 'imputer'
        assert summary['fastest_step'] == 'standardizer'
    
    def test_bottlenecks(self):
        """测试瓶颈检测"""
        profiler = PerformanceProfiler()
        profiler.record('step1', 'type1', 100.0, (100, 50), (100, 50))
        profiler.record('step2', 'type2', 30.0, (100, 50), (100, 50))
        profiler.record('step3', 'type3', 20.0, (100, 50), (100, 50))
        
        # 总时间 150ms，20% 阈值 = 30ms
        # step1 (100ms >= 30ms) 和 step2 (30ms >= 30ms) 都是瓶颈
        bottlenecks = profiler.get_bottlenecks(threshold_percent=20.0)
        assert len(bottlenecks) == 2
        assert bottlenecks[0]['step_name'] == 'step1'
        assert bottlenecks[0]['percentage'] == (100.0 / 150.0) * 100
    
    def test_no_bottlenecks(self):
        """测试无瓶颈情况"""
        profiler = PerformanceProfiler()
        profiler.record('step1', 'type1', 10.0, (100, 50), (100, 50))
        profiler.record('step2', 'type2', 10.0, (100, 50), (100, 50))
        
        # 总时间 20ms，90% 阈值 = 18ms
        bottlenecks = profiler.get_bottlenecks(threshold_percent=90.0)
        assert len(bottlenecks) == 0
