# -*- coding: utf-8 -*-
"""
管道 DAG（有向无环图）

基于 networkx 实现因子处理步骤的依赖关系管理。
替代原有的 PipelineOrderValidator.DEPENDENCIES 字典和 VALID_STEP_ORDERS 列表，
提供拓扑排序验证、路径查询、可视化能力。
"""

from typing import List, Tuple, Optional
import networkx as nx
from .config import StepType

# 学术与业界验证的标准处理顺序（保留为拓扑排序的参考基准）
_STANDARD_VALID_ORDERS: List[List[StepType]] = [
    [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.TRANSFORMATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
    [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
    [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.NEUTRALIZATION],
    [StepType.IMPUTATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
]


class PipelineDAG:
    """
    因子处理管道的依赖关系 DAG
    
    基于 networkx.DiGraph 管理步骤间的依赖关系，提供:
    - 拓扑排序验证
    - 合法顺序检查
    - 路径查询
    - 环路检测
    - DAG 可视化
    
    DAG 结构:
        IMPUTATION ──→ OUTLIER_DETECTION ──→ TRANSFORMATION
            │               │                      │
            │               └──────────────────────┤
            │                                      ▼
            ├──────────────────────────→ STANDARDIZATION
            │                                      │
            └──────────────────────────→ NEUTRALIZATION
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self._build_default_graph()
    
    def _build_default_graph(self):
        """构建默认的因子处理 DAG"""
        nodes = list(StepType)
        self.graph.add_nodes_from(nodes)
        
        edges = [
            (StepType.IMPUTATION, StepType.OUTLIER_DETECTION),
            (StepType.IMPUTATION, StepType.TRANSFORMATION),
            (StepType.IMPUTATION, StepType.STANDARDIZATION),
            (StepType.IMPUTATION, StepType.NEUTRALIZATION),
            (StepType.OUTLIER_DETECTION, StepType.TRANSFORMATION),
            (StepType.OUTLIER_DETECTION, StepType.STANDARDIZATION),
        ]
        self.graph.add_edges_from(edges)
    
    def add_edge(self, before: StepType, after: StepType):
        """添加依赖关系: before 必须在 after 之前"""
        self.graph.add_edge(before, after)
    
    def validate(self, steps: List[StepType], strict: bool = True) -> Tuple[bool, List[str]]:
        """
        验证步骤顺序是否满足 DAG 约束
        
        Parameters
        ----------
        steps : List[StepType]
            步骤类型列表
        strict : bool
            是否严格模式（检查是否在预定义标准顺序列表中）
        
        Returns
        -------
        is_valid : bool
            是否通过验证
        errors : List[str]
            错误信息列表
        """
        errors = []
        
        if not steps:
            errors.append("步骤列表为空")
            return False, errors
        
        # 1. 检查 IMPUTATION 必须是第一步
        if StepType.IMPUTATION in steps and steps[0] != StepType.IMPUTATION:
            errors.append(
                f"顺序错误: 第一步必须是插补(IMPUTATION)，当前第一步是 {steps[0].value}\n"
                f"原因: 去极值和标准化需要基于完整数据计算统计量，"
                f"缺失数据会导致阈值/参数估计有偏。"
            )
        
        # 2. 检查依赖关系（基于 DAG 祖先）
        present = set(steps)
        for i, step in enumerate(steps):
            ancestors = nx.ancestors(self.graph, step) & present
            for ancestor in ancestors:
                ancestor_idx = steps.index(ancestor)
                if ancestor_idx > i:
                    errors.append(
                        f"顺序错误: {step.value} 必须在 {ancestor.value} 之后\n"
                        f"原因: {self._get_reason(step, ancestor)}"
                    )
        
        # 3. 严格模式: 检查是否在预定义的标准顺序列表中
        if strict:
            is_valid_order = any(
                self._is_subsequence(steps, valid_order)
                for valid_order in _STANDARD_VALID_ORDERS
            )
            if not is_valid_order and len(errors) == 0:
                errors.append(
                    f"顺序警告: 当前顺序 {' → '.join(s.value for s in steps)} "
                    f"不在预定义的标准顺序列表中\n"
                    f"标准顺序示例: imputation → outlier → transformation → standardization → neutralization"
                )
        
        return len(errors) == 0, errors
    
    def suggest(self, steps: List[StepType]) -> List[StepType]:
        """
        返回满足 DAG 约束的拓扑排序建议
        
        使用优先级字典作为 tiebreaker，确保 NEUTRALIZATION 在最后，
        即使 DAG 中 NEUTRALIZATION 只依赖 IMPUTATION。
        """
        present = set(steps)
        subgraph = self.graph.subgraph(present)
        
        try:
            # lexicographical_topological_sort 按优先级升序选择下一个节点
            # 优先级: IMPUTATION(0) < OUTLIER(1) < TRANSFORMATION(2) < STANDARDIZATION(3) < NEUTRALIZATION(4)
            return list(nx.lexicographical_topological_sort(
                subgraph, key=lambda n: self._priority(n)
            ))
        except nx.NetworkXUnfeasible:
            return sorted(steps, key=lambda s: self._priority(s))
    
    def get_path(self, from_step: StepType, to_step: StepType) -> Optional[List[StepType]]:
        """获取两个步骤之间的最短路径，无路径返回 None"""
        try:
            return nx.shortest_path(self.graph, from_step, to_step)
        except nx.NetworkXNoPath:
            return None
    
    def get_all_paths(self, from_step: StepType, to_step: StepType) -> List[List[StepType]]:
        """获取两个步骤之间的所有简单路径"""
        try:
            return list(nx.all_simple_paths(self.graph, from_step, to_step))
        except nx.NetworkXNoPath:
            return []
    
    def visualize(self, output_path: str = "pipeline_dag.png"):
        """导出 DAG 可视化图片"""
        try:
            import matplotlib.pyplot as plt
            pos = nx.spring_layout(self.graph, seed=42)
            labels = {n: n.value for n in self.graph.nodes}
            nx.draw(
                self.graph, pos, labels=labels, with_labels=True,
                node_color='lightblue', node_size=2000, font_size=10,
                arrows=True, arrowsize=15
            )
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
        except ImportError:
            pass  # matplotlib 不可用时静默跳过
    
    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    
    @staticmethod
    def _is_subsequence(sub: List[StepType], full: List[StepType]) -> bool:
        """检查 sub 是否是 full 的子序列（保持相对顺序）"""
        it = iter(full)
        return all(step in it for step in sub)
    
    @staticmethod
    def _priority(step: StepType) -> int:
        """步骤优先级（用于排序回退）"""
        return {
            StepType.IMPUTATION: 0,
            StepType.OUTLIER_DETECTION: 1,
            StepType.TRANSFORMATION: 2,
            StepType.STANDARDIZATION: 3,
            StepType.NEUTRALIZATION: 4,
        }.get(step, 99)
    
    @staticmethod
    def _get_reason(step: StepType, required: StepType) -> str:
        """获取顺序要求的原因说明"""
        reasons = {
            (StepType.OUTLIER_DETECTION, StepType.IMPUTATION):
                "去极值(MAD/分位数)需要完整数据计算统计量，缺失值会导致阈值估计有偏",
            (StepType.TRANSFORMATION, StepType.IMPUTATION):
                "变换参数(如Box-Cox lambda)需要基于完整数据估计",
            (StepType.TRANSFORMATION, StepType.OUTLIER_DETECTION):
                "极值会严重扭曲变换参数估计，应先去除极值",
            (StepType.STANDARDIZATION, StepType.IMPUTATION):
                "标准化需要完整数据计算均值和标准差",
            (StepType.STANDARDIZATION, StepType.OUTLIER_DETECTION):
                "极值会显著影响标准化后的分布，应先去除",
            (StepType.NEUTRALIZATION, StepType.IMPUTATION):
                "中性化回归需要完整数据，缺失值会导致回归系数有偏",
        }
        return reasons.get((step, required), "必须保持此顺序以确保统计正确性")