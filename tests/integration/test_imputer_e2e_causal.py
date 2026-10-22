# -*- coding: utf-8 -*-
"""
P2-3: 端到端 (E2E) 无前视测试 — 全管线因果性验证.

测试目标:
    通过 ImputerAdapter (生产路径) 完整跑一次 fit + transform, 验证:
    - 截断未来数据时, t 时刻插补结果不变 (因果性)
    - 不依赖 bfill (静态扫描已覆盖, 此处为行为层兜底)
    - lookahead_safe=True/False 两条路径都能跑通 (legacy 路径仅验证可运行, 不验证因果)

设计依据:
- Little & Rubin (2002) §4.3: fill within-unit first, then across-units
- Lopez de Prado (2018), Chapter on Cross-Validation Methods in Finance:
  Purged K-Fold 信息泄漏

注: 本测试使用合成数据, 不依赖实盘. 实盘 E2E 应在真实数据 pipeline 上跑,
由 pipelines_v2.py 集成测试覆盖 (本文件不重复).
"""
import numpy as np
import pandas as pd
import pytest

from factor_pipeline.adapters import ImputerAdapter


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def e2e_panel():
    """构造能暴露前视偏差的合成面板.

    设计:
    - S0 在 t=5 缺失, t=6 出现异常值 999 (bfill 会泄漏)
    - S1 在 t=4 缺失, t=5 有值 (因果填充应来自 t=3)
    - 共 12 行, 满足 RF shared_model 的 len(complete_rows) > 10 要求
    """
    dates = pd.date_range('2020-01-01', periods=12, freq='D')
    cols = ['S0', 'S1', 'S2']
    rng = np.random.default_rng(42)
    base = rng.standard_normal((12, 3)) * 10 + np.arange(12).reshape(-1, 1)
    data = base.copy()
    data[5, 0] = np.nan   # t=5: S0 缺失
    data[6, 0] = 999.0    # t=6: S0 异常值
    data[4, 1] = np.nan   # t=4: S1 缺失
    return pd.DataFrame(data, index=dates, columns=cols)


# =============================================================================
# E2E 因果性测试
# =============================================================================

class TestE2ECausalProperty:
    """端到端因果性: 截断未来数据, t 时刻插补结果应不变."""

    def test_ffill_ts_path_causal(self, e2e_panel):
        """strategy='ffill_ts' 生产路径: 截断未来, t=4 的 S1 填充应不变.

        ffill_ts 是当前生产路径 (adapters.py L236-240).
        """
        df_full = e2e_panel
        df_trunc = e2e_panel.iloc[:6].copy()  # 截断到 t=5

        # Full data
        imp1 = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp1.fit(df_full)
        r_full = imp1.transform(df_full.copy())

        # Truncated
        imp2 = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp2.fit(df_trunc)
        r_trunc = imp2.transform(df_trunc.copy())

        # t=4 的 S1 填充值: full 和 truncated 应一致 (因果性)
        val_full = r_full.iloc[4, 1]
        val_trunc = r_trunc.iloc[4, 1]
        assert abs(val_full - val_trunc) < 1e-9, \
            f"ffill_ts 因果性违反: t=4 S1 full={val_full}, trunc={val_trunc}"

    def test_ffill_ts_no_future_leakage(self, e2e_panel):
        """strategy='ffill_ts': 填充结果不应包含未来异常值 999."""
        df = e2e_panel
        imp = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp.fit(df)
        result = imp.transform(df.copy())

        # S0 在 t=5 缺失, 填充值不应是 t=6 的 999
        filled_s0_t5 = result.iloc[5, 0]
        assert abs(filled_s0_t5 - 999.0) > 1e-6, \
            f"ffill_ts 填充了未来异常值 999: S0[t=5]={filled_s0_t5}"

        # 更一般: 任何被填充的位置都不应是 999
        nan_mask = df.isnull()
        filled_mask = nan_mask & ~result.isnull()
        # 排除 t=6 原本就是 999 的位置
        for col in nan_mask.columns:
            col_nan = nan_mask[col]
            col_filled = col_nan & ~result[col].isnull()
            if col_filled.any():
                filled_vals = result.loc[col_filled, col]
                # 不应出现 999 (除非原数据 t=6 本就是 999, 但那个位置不在 nan_mask 中)
                assert not np.any(np.isclose(filled_vals.values, 999.0)), \
                    f"列 {col} 填充结果出现 999 (未来异常值泄漏): {filled_vals.values}"


class TestE2ELookaheadSafeOnOff:
    """lookahead_safe=True vs False 两条路径都应能跑通 (无异常)."""

    def test_lookahead_safe_true_runs(self, e2e_panel):
        """lookahead_safe=True: 生产路径应能跑通."""
        imp = ImputerAdapter(strategy='cross_sectional', lookahead_safe=True)
        imp.fit(e2e_panel)
        result = imp.transform(e2e_panel.copy())
        assert not result.isnull().any().any(), \
            "lookahead_safe=True 路径应填满所有 NaN"

    def test_lookahead_safe_false_runs(self, e2e_panel):
        """lookahead_safe=False: legacy 路径也应能跑通 (DEPRECATED, 不验证因果)."""
        imp = ImputerAdapter(strategy='cross_sectional', lookahead_safe=False)
        imp.fit(e2e_panel)
        result = imp.transform(e2e_panel.copy())
        assert not result.isnull().any().any(), \
            "lookahead_safe=False 路径应填满所有 NaN"


class TestE2EAllStrategiesCausal:
    """所有支持 lookahead_safe 的 strategy 都应满足因果性."""

    @pytest.mark.parametrize("strategy", ["cross_sectional"])
    def test_strategy_causal(self, strategy, e2e_panel):
        """对每个支持 lookahead_safe 的 strategy 验证因果性 (截断不变性)."""
        df_full = e2e_panel
        df_trunc = e2e_panel.iloc[:6].copy()

        imp1 = ImputerAdapter(strategy=strategy, lookahead_safe=True)
        imp1.fit(df_full)
        r_full = imp1.transform(df_full.copy())

        imp2 = ImputerAdapter(strategy=strategy, lookahead_safe=True)
        imp2.fit(df_trunc)
        r_trunc = imp2.transform(df_trunc.copy())

        # 比较 t=4 S1 的填充值
        val_full = r_full.iloc[4, 1]
        val_trunc = r_trunc.iloc[4, 1]
        assert abs(val_full - val_trunc) < 1e-6, \
            f"{strategy} 因果性违反: t=4 S1 full={val_full}, trunc={val_trunc}"


# =============================================================================
# P2-3 补充: 静态扫描 + 严格因果性
# =============================================================================

class TestE2ESourceScan:
    """静态扫描: 验证生产路径源码不含前视操作.

    这是行为测试的兜底层 — 即便行为测试通过, 源码静态扫描能捕获
    "测试数据恰好没暴露" 的前视偏差.
    """

    def test_adapters_no_bfill_in_imputer_adapter(self):
        """adapters.py ImputerAdapter._transform_ffill_ts 不应使用 bfill."""
        import inspect
        from factor_pipeline.adapters import ImputerAdapter

        # 获取 _transform_ffill_ts 源码
        source = inspect.getsource(ImputerAdapter._transform_ffill_ts)
        # 排除注释和字符串中的 bfill
        bfill_in_code = False
        for line in source.split('\n'):
            stripped = line.split('#')[0]  # 去掉行内注释
            if '.bfill()' in stripped:
                # 粗略排除字符串字面量
                in_string = ('"' in stripped and stripped.index('"') < stripped.index('.bfill()')) or \
                           ("'" in stripped and stripped.index("'") < stripped.index('.bfill()'))
                if not in_string:
                    bfill_in_code = True
                    break
        assert not bfill_in_code, \
            "ImputerAdapter._transform_ffill_ts 含 .bfill() 调用 (前视偏差)"

    def test_imputers_no_bfill_in_module(self):
        """modules/factor_imputer/core/imputers.py 不应使用 bfill."""
        import inspect
        from factor_pipeline.modules.factor_imputer.core import imputers as imp_mod

        source = inspect.getsource(imp_mod)
        bfill_lines = []
        for i, line in enumerate(source.split('\n'), 1):
            stripped = line.split('#')[0]
            if '.bfill()' in stripped:
                in_string = ('"' in stripped and stripped.index('"') < stripped.index('.bfill()')) or \
                           ("'" in stripped and stripped.index("'") < stripped.index('.bfill()'))
                if not in_string:
                    bfill_lines.append((i, line.strip()))
        assert len(bfill_lines) == 0, \
            f"imputers.py 含 .bfill() 调用 (前视偏差未修复): {bfill_lines}"


class TestE2EStrictCausality:
    """严格因果性: 对多个时间点验证历史不变性.

    不仅验证 t=4, 而是验证 [0, t_trunc-1] 全部时间点都保持不变.
    """

    def test_ffill_ts_all_history_unchanged(self, e2e_panel):
        """ffill_ts: 截断后, [0, t_trunc-1] 全部行应与 full 一致."""
        df_full = e2e_panel
        t_trunc = 8  # 截断到 t=7 (含)
        df_trunc = e2e_panel.iloc[:t_trunc].copy()

        imp1 = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp1.fit(df_full)
        r_full = imp1.transform(df_full.copy())

        imp2 = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp2.fit(df_trunc)
        r_trunc = imp2.transform(df_trunc.copy())

        # 对比 [0, t_trunc-1] 每一行的填充值
        # 注: full 在 t=5 的 S0 (NaN, 应被 ffill 填为 t=4 的值 5.0)
        # trunc 在 t=5 的 S0 (NaN, 应同样被 ffill 填为 t=4 的值 5.0)
        np.testing.assert_allclose(
            r_full.iloc[:t_trunc].values,
            r_trunc.iloc[:t_trunc].values,
            rtol=1e-10, atol=1e-10,
            err_msg="ffill_ts 严格因果性失败: 截断后历史与 full 不一致"
        )

    def test_ffill_ts_no_future_dependency(self, e2e_panel):
        """ffill_ts: 修改未来数据 (t > t_check), 历史 [0, t_check] 应不变."""
        df = e2e_panel
        df_modified = df.copy()
        # 修改未来数据 (t=10, 11) 为异常值
        df_modified.iloc[10, :] = 9999.0
        df_modified.iloc[11, :] = -9999.0

        t_check = 8  # 检查 [0, 7] 是否不变

        imp1 = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp1.fit(df)
        r_orig = imp1.transform(df.copy())

        imp2 = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp2.fit(df_modified)
        r_mod = imp2.transform(df_modified.copy())

        # [0, t_check-1] 应完全一致 (因果: 不依赖未来数据)
        np.testing.assert_allclose(
            r_orig.iloc[:t_check].values,
            r_mod.iloc[:t_check].values,
            rtol=1e-10, atol=1e-10,
            err_msg="ffill_ts 未来数据依赖: 修改 t>t_check 后历史改变"
        )
