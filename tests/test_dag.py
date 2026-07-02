# -*- coding: utf-8 -*-
"""
PipelineDAG 单元测试

测试范围:
1. 默认 DAG 构建（节点、边）
2. validate() 合法性验证
3. suggest() 拓扑排序建议
4. get_path() / get_all_paths() 路径查询
5. 环路检测
6. 与当前 PipelineOrderValidator 行为一致
"""

import sys
import os
import pytest

# 添加项目根目录到路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from factor_pipeline.config import StepType


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def dag():
    from factor_pipeline.dag import PipelineDAG
    return PipelineDAG()


# =============================================================================
# 1. 默认 DAG 构建
# =============================================================================

class TestDAGConstruction:
    """测试 DAG 的默认构建"""

    def test_has_all_step_types(self, dag):
        """所有 StepType 都应该在 DAG 中"""
        for step_type in StepType:
            assert step_type in dag.graph.nodes, f"{step_type} 不在 DAG 中"

    def test_is_acyclic(self, dag):
        """DAG 必须是无环的"""
        import networkx as nx
        assert nx.is_directed_acyclic_graph(dag.graph), "DAG 中存在环路"

    def test_imputation_has_no_ancestors(self, dag):
        """IMPUTATION 应该是根节点（无祖先）"""
        import networkx as nx
        ancestors = nx.ancestors(dag.graph, StepType.IMPUTATION)
        assert len(ancestors) == 0, f"IMPUTATION 不应有祖先，实际有: {ancestors}"

    def test_imputation_is_ancestor_of_all(self, dag):
        """IMPUTATION 应该是所有其他步骤的祖先"""
        import networkx as nx
        for step_type in StepType:
            if step_type == StepType.IMPUTATION:
                continue
            ancestors = nx.ancestors(dag.graph, step_type)
            assert StepType.IMPUTATION in ancestors, \
                f"IMPUTATION 应该是 {step_type} 的祖先"

    def test_outlier_before_transformation(self, dag):
        """OUTLIER_DETECTION 应该在 TRANSFORMATION 之前"""
        import networkx as nx
        assert StepType.OUTLIER_DETECTION in nx.ancestors(dag.graph, StepType.TRANSFORMATION)

    def test_outlier_before_standardization(self, dag):
        """OUTLIER_DETECTION 应该在 STANDARDIZATION 之前"""
        import networkx as nx
        assert StepType.OUTLIER_DETECTION in nx.ancestors(dag.graph, StepType.STANDARDIZATION)


# =============================================================================
# 2. validate() 步骤验证
# =============================================================================

class TestDAGValidate:
    """测试 validate() 方法的合法性验证"""

    def test_valid_full_order(self, dag):
        """标准五步顺序应该通过验证"""
        steps = [
            StepType.IMPUTATION,
            StepType.OUTLIER_DETECTION,
            StepType.TRANSFORMATION,
            StepType.STANDARDIZATION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert valid, f"标准五步顺序应该通过验证，错误: {errors}"

    def test_valid_order_without_transformation(self, dag):
        """跳过 TRANSFORMATION 的顺序应该通过验证"""
        steps = [
            StepType.IMPUTATION,
            StepType.OUTLIER_DETECTION,
            StepType.STANDARDIZATION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert valid, f"跳过 TRANSFORMATION 应该通过验证，错误: {errors}"

    def test_valid_order_without_outlier(self, dag):
        """跳过 OUTLIER_DETECTION 的顺序应该通过验证"""
        steps = [
            StepType.IMPUTATION,
            StepType.STANDARDIZATION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert valid, f"跳过 OUTLIER_DETECTION 应该通过验证，错误: {errors}"

    def test_valid_minimal_order(self, dag):
        """最小三步顺序应该通过验证"""
        steps = [
            StepType.IMPUTATION,
            StepType.OUTLIER_DETECTION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert valid, f"最小三步顺序应该通过验证，错误: {errors}"

    def test_invalid_imputation_not_first(self, dag):
        """IMPUTATION 不在第一位应该失败"""
        steps = [
            StepType.OUTLIER_DETECTION,
            StepType.IMPUTATION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert not valid, "IMPUTATION 不在第一位应该失败"
        assert any("第一步" in e for e in errors), f"错误信息应包含'第一步'，实际: {errors}"

    def test_invalid_transformation_before_outlier(self, dag):
        """TRANSFORMATION 在 OUTLIER_DETECTION 之前应该失败"""
        steps = [
            StepType.IMPUTATION,
            StepType.TRANSFORMATION,
            StepType.OUTLIER_DETECTION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert not valid, "TRANSFORMATION 在 OUTLIER 之前应该失败"
        assert any("必须" in e for e in errors), f"错误信息应包含'必须'，实际: {errors}"

    def test_invalid_standardization_before_imputation(self, dag):
        """STANDARDIZATION 在 IMPUTATION 之前应该失败"""
        steps = [
            StepType.STANDARDIZATION,
            StepType.IMPUTATION,
            StepType.NEUTRALIZATION,
        ]
        valid, errors = dag.validate(steps, strict=True)
        assert not valid, "STANDARDIZATION 在 IMPUTATION 之前应该失败"

    def test_empty_steps(self, dag):
        """空步骤列表应该失败"""
        valid, errors = dag.validate([], strict=True)
        assert not valid, "空步骤列表应该失败"

    def test_non_strict_mode_accepts_unusual_order(self, dag):
        """非严格模式应该接受不在预定义列表中的顺序"""
        # 仅仅 IMPUTATION + NEUTRALIZATION（跳过中间步骤）
        steps = [StepType.IMPUTATION, StepType.NEUTRALIZATION]
        valid, errors = dag.validate(steps, strict=False)
        # 这个顺序满足依赖关系（IMPUTATION 在 NEUTRALIZATION 之前）
        assert valid, f"非严格模式应该接受有效顺序，错误: {errors}"

    def test_strict_mode_rejects_unusual_order(self, dag):
        """严格模式应该拒绝不在预定义列表中的顺序"""
        # [IMPUTATION, NEUTRALIZATION, STANDARDIZATION] 满足 DAG 约束
        # （NEUTRALIZATION 只依赖 IMPUTATION，STANDARDIZATION 只依赖 IMPUTATION+OUTLIER）
        # 但不满足 VALID_STEP_ORDERS（所有标准顺序中 STANDARDIZATION 都在 NEUTRALIZATION 之前）
        steps = [StepType.IMPUTATION, StepType.NEUTRALIZATION, StepType.STANDARDIZATION]
        valid, errors = dag.validate(steps, strict=True)
        assert not valid, "严格模式应该拒绝不在预定义列表中的顺序"


# =============================================================================
# 3. suggest() 拓扑排序建议
# =============================================================================

class TestDAGSuggest:
    """测试 suggest() 方法的排序建议"""

    def test_suggest_reversed_order(self, dag):
        """反转的顺序应该被修正为正确顺序"""
        reversed_steps = [
            StepType.NEUTRALIZATION,
            StepType.STANDARDIZATION,
            StepType.TRANSFORMATION,
            StepType.OUTLIER_DETECTION,
            StepType.IMPUTATION,
        ]
        suggested = dag.suggest(reversed_steps)
        assert suggested[0] == StepType.IMPUTATION, \
            f"IMPUTATION 应该是第一位，实际第一位: {suggested[0]}"
        assert suggested[-1] == StepType.NEUTRALIZATION, \
            f"NEUTRALIZATION 应该是最后一位，实际最后一位: {suggested[-1]}"

    def test_suggest_preserves_existing_valid_order(self, dag):
        """已经正确的顺序应该保持不变"""
        steps = [
            StepType.IMPUTATION,
            StepType.OUTLIER_DETECTION,
            StepType.TRANSFORMATION,
            StepType.STANDARDIZATION,
            StepType.NEUTRALIZATION,
        ]
        suggested = dag.suggest(steps)
        assert suggested == steps, f"已正确顺序不应改变，实际: {suggested}"

    def test_suggest_all_steps(self, dag):
        """suggest 应该返回所有输入步骤，不丢失不增加"""
        steps = [
            StepType.NEUTRALIZATION,
            StepType.IMPUTATION,
            StepType.STANDARDIZATION,
        ]
        suggested = dag.suggest(steps)
        assert set(suggested) == set(steps), \
            f"suggest 不应丢失或增加步骤，输入: {steps}，输出: {suggested}"


# =============================================================================
# 4. 路径查询
# =============================================================================

class TestDAGPaths:
    """测试路径查询功能"""

    def test_get_path_imputation_to_neutralization(self, dag):
        """IMPUTATION 到 NEUTRALIZATION 应该有路径"""
        path = dag.get_path(StepType.IMPUTATION, StepType.NEUTRALIZATION)
        assert path is not None, "IMPUTATION 到 NEUTRALIZATION 应该有路径"
        assert path[0] == StepType.IMPUTATION
        assert path[-1] == StepType.NEUTRALIZATION

    def test_get_path_reverse_returns_none(self, dag):
        """反向路径（NEUTRALIZATION → IMPUTATION）应该返回 None"""
        path = dag.get_path(StepType.NEUTRALIZATION, StepType.IMPUTATION)
        assert path is None, "反向路径应该返回 None"

    def test_get_all_paths_imputation_to_neutralization(self, dag):
        """IMPUTATION 到 NEUTRALIZATION 应该有多条路径"""
        paths = dag.get_all_paths(StepType.IMPUTATION, StepType.NEUTRALIZATION)
        assert len(paths) >= 1, f"至少有 1 条路径，实际: {len(paths)}"

    def test_get_path_no_path(self, dag):
        """两个无依赖关系的步骤之间应该没有路径（如果存在的话）"""
        # 在当前 DAG 中，所有步骤都有依赖关系
        # 但 STANDARDIZATION 到 OUTLIER_DETECTION 没有直接路径
        path = dag.get_path(StepType.STANDARDIZATION, StepType.OUTLIER_DETECTION)
        assert path is None, "STANDARDIZATION 到 OUTLIER_DETECTION 不应该有路径"


# =============================================================================
# 5. 环路检测
# =============================================================================

class TestDAGCycleDetection:
    """测试环路检测能力"""

    def test_no_cycle_by_default(self, dag):
        """默认 DAG 不应该有环"""
        import networkx as nx
        assert nx.is_directed_acyclic_graph(dag.graph)

    def test_detect_cycle_after_adding_cycle_edge(self, dag):
        """添加环路边后应该检测到"""
        import networkx as nx
        # 添加一条反向边
        dag.graph.add_edge(StepType.NEUTRALIZATION, StepType.IMPUTATION)
        assert not nx.is_directed_acyclic_graph(dag.graph), \
            "添加反向边后应该检测到环路"


# =============================================================================
# 6. 与原有 VALID_STEP_ORDERS 行为一致性
# =============================================================================

class TestDAGCompatibility:
    """确保 PipelineDAG 的行为与原有 VALID_STEP_ORDERS 一致"""

    # 原有 VALID_STEP_ORDERS 中定义的所有合法顺序
    KNOWN_VALID_ORDERS = [
        [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.TRANSFORMATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
        [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
        [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.NEUTRALIZATION],
        [StepType.IMPUTATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
    ]

    def test_all_known_valid_orders_pass(self, dag):
        """所有原有 VALID_STEP_ORDERS 中的顺序都应该通过 DAG 验证"""
        for order in self.KNOWN_VALID_ORDERS:
            valid, errors = dag.validate(order, strict=True)
            assert valid, \
                f"原有合法顺序 {[s.value for s in order]} 应该通过 DAG 验证，错误: {errors}"

    def test_imputation_first_rule(self, dag):
        """IMPUTATION 必须是第一步的规则保持一致"""
        invalid = [StepType.OUTLIER_DETECTION, StepType.IMPUTATION, StepType.NEUTRALIZATION]
        valid, _ = dag.validate(invalid, strict=True)
        assert not valid, "IMPUTATION 不在第一位应该失败"

    def test_neutralization_not_first(self, dag):
        """NEUTRALIZATION 不能作为第一步"""
        invalid = [StepType.NEUTRALIZATION, StepType.IMPUTATION]
        valid, _ = dag.validate(invalid, strict=True)
        assert not valid, "NEUTRALIZATION 不能作为第一步"


# =============================================================================
# 7. add_edge 动态添加依赖
# =============================================================================

class TestDAGDynamicEdges:
    """测试动态添加依赖边"""

    def test_add_edge_creates_dependency(self, dag):
        """添加边后应该创建新的依赖关系"""
        import networkx as nx
        # 添加一条不存在的边
        dag.add_edge(StepType.NEUTRALIZATION, StepType.STANDARDIZATION)
        ancestors = nx.ancestors(dag.graph, StepType.STANDARDIZATION)
        assert StepType.NEUTRALIZATION in ancestors, \
            "添加边后 NEUTRALIZATION 应该是 STANDARDIZATION 的祖先"