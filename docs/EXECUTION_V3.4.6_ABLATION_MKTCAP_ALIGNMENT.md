# 执行: AblationRunner L3/L4 市值口径对齐 (v3.4.6)

> **版本**: v1.0 (2026-11-13)
> **调研**: [RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md](research/RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md)
> **设计**: `docs/private/DESIGN_ABLATION_MKTCAP_ALIGNMENT.md`
> **规范**: [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) §13.8

---

## §1 概览

v3.4.4/v3.4.5 补齐了 L1/L2/Baseline 的市值转发后, L3/L4 成为仅剩的两层「无市值入口」。
本版为 `run_l3` / `run_l4_oat` 增加 `market_cap_data`, 并解决由此暴露的
L4 `neutralization` 自由度空转问题 (RESEARCH F5/F8)。

**核心产出**:
- `run_l3`: B3 + 24 个臂统一注入市值 (与 B3 同口径)
- `run_l4_oat`: B3 + 18 个臂注入 (16 个非中性化臂 + `none` / `industry+mktcap`),
  但 `neutralization='industry'` 臂显式跳过 (管线收到市值会自动切
  `industry_marketcap`); 默认口径随数据可用性切换
- 版本 **3.4.6**; 缓存代际不变 **`v2.3.0-cache`**

---

## §2 变更清单

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | `run_l3` / `run_l4_oat` 新增 `market_cap_data`; 注入规则与默认口径 |
| `tests/test_backtest/test_ablation_mktcap_alignment.py` | **新增** E1-E7 (7 例) |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.5 → 3.4.6 |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.6` |
| `CHANGELOG.md` / `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` / `CODE_WIKI.md` | 发版同步 |

---

## §3 测试规格 (E1-E7)

| # | 用例 | 断言 |
|---|------|------|
| E1 | `test_run_l3_forwards_market_cap_to_all_arms` | 25 次调用均带同一对象 |
| E2 | `test_run_l3_omits_market_cap_when_absent` | 无该关键字 (monkeypatch 签名兼容) |
| E3 | `test_run_l4_forwards_market_cap_to_non_neutralization_arms` | outlier/scaler/missing/time_align/data_window 臂均带 |
| E4 | `test_run_l4_neutralization_industry_arm_skips_market_cap` | `industry` 臂不带; `industry+mktcap` 与 `none` 臂带 |
| E5 | `test_run_l4_default_neutralization_switches_with_market_cap` | 默认臂名为 `L4_neutralization_industry+mktcap` 且 `_is_trivial=True`; `L4_neutralization_industry` 非 trivial |
| E6 | `test_run_l4_without_market_cap_keeps_legacy_defaults` | 默认 `L4_neutralization_industry` trivial; 全臂无该关键字 |
| E7 | `test_b3_reference_receives_market_cap` | 两者不传 `b3_full_result` 时, B3 调用带市值 |

---

## §4 代码

### §4.1 `run_l4_oat`

```python
        results = []
        extra_kwargs = {}
        if market_cap_data is not None:
            extra_kwargs['market_cap_data'] = market_cap_data

        if b3_full_result is not None:
            results.append(b3_full_result)
        else:
            b3_config = AblationConfig(name='B3_full', layer='baseline', baseline_level='B3')
            results.append(self.run_single(
                b3_config, factor_data, fwd_returns, industry_data, **extra_kwargs))
```

默认口径:

```python
        defaults = {
            ...
            'neutralization': (
                'industry+mktcap' if market_cap_data is not None else 'industry'),
            ...
        }
```

臂级分支:

```python
        for param_name, options in oat_specs:
            for option in options:
                is_trivial = (option == defaults[param_name])
                config = AblationConfig(...)
                # 'industry' 臂要求「仅行业」; 管线收到市值会自动切 industry_marketcap
                arm_kwargs = extra_kwargs
                if param_name == 'neutralization' and option == 'industry':
                    arm_kwargs = {}
                results.append(self.run_single(
                    config, factor_data, fwd_returns, industry_data, **arm_kwargs))
```

### §4.2 `run_l3`

B3 与全部 24 个臂统一 `**extra_kwargs`。

---

## §5 版本

3.4.6 (6 处锚点), 缓存代际 `v2.3.0-cache` 不变, 无新增依赖。

---

## §6 工程检查

```powershell
python -m pytest tests/test_backtest/test_ablation_mktcap_alignment.py -q
python -m pytest tests/test_backtest/ -q
python -m pytest tests -q
```

---

## §7 验收

| 层级 | 结果 |
|------|------|
| 新增 E1-E7 | **8 passed** (Red: 6 failed / 2 passed; 0.14s) |
| 定向回归 | ablation_runner + decoupler 臂 + 本文件 → **113 passed** (18.14s) |
| 版本统一 | `test_fix3_version_unification.py` **7 passed** + 手工校验 **5/5** (6/6 锚点) |
| 全量回归 | `pytest tests -q` → **1715 passed / 15 skipped / 0 failed** (2525.38s) |
| 审计 | [2026-11-13-ablation-mktcap-alignment-audit.md](audit/2026-11-13-ablation-mktcap-alignment-audit.md) → P0/P1 = 0, 92 分 **A** |

---

## §8 风险

| # | 风险 | 处置 |
|---|------|------|
| R1 | L4 `neutralization='industry'` 臂与其他臂口径不同, 可能被误读为「口径不一致」 | 该臂的 DOF **就是**中性化口径, 差异是设计意图; 代码注释 + 本文档明示 |
| R2 | 调用方传入的 `b3_full_result` 若未含市值, 参照与实验臂仍不一致 | 文档明示 (RESEARCH O3), 不在 runner 内强校验以避免破坏既有调用 |
| R3 | L3/L4 其余开关空转 (RESEARCH O1) 未被本任务修复 | 登记为独立任务, 避免把「入口修复」与「旋钮映射」混为一个变更 |
| R4 | 传市值后 L3/L4 数值会变化 (此前恒为行业口径) | 属预期修复; 未传市值路径零变化, 既有基线可复现 |

---

## §9 Review

| 检查 | 结论 |
|------|------|
| 是否覆盖 RESEARCH 全部结论 | ✅ F1-F12 → §2/§4 |
| 测试是否可失败 (Red) | ✅ 实现前 7 例均应失败 (方法不接受该参数 → TypeError) |
| 是否与 v3.4.5 模式一致 | ✅ 同一 `extra_kwargs` 惯用法 |
