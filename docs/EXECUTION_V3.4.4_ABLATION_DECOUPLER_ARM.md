# EXECUTION V3.4.4 — AblationRunner `decoupler` 消融臂

> **版本**: v1.0 (2026-11-13)
> **方法**: 10 步 spec workflow §13.8 中任务裁剪（步骤 1-2-3-4-5-6-9-10）
> **上游**: [RESEARCH_ABLATION_DECOUPLER_ARM.md](research/RESEARCH_ABLATION_DECOUPLER_ARM.md) v1.0 / [DESIGN_ABLATION_DECOUPLER_ARM.md](private/DESIGN_ABLATION_DECOUPLER_ARM.md) v1.0
> **关联**: ADR-036（消融框架）、ADR-042（unified / dynamic_ab）、ADR-045（中性化 / AR 独立开关）

---

## §1 概览

v3.4.3（ADR-045）使 `module_enabled['decoupler']` 可独立关闭 AR 解耦，但 `AblationRunner.run_l1` 的所有臂都运行 unified 管道，`decoupler` 键不生效（RESEARCH A1–A4）。本任务新增 **within-mode** 的 L1 消融入口：

- 参照臂：`L1_dynamic_ref`（`dynamic_ab`，中性化 + AR 全开）
- 实验臂：`L1_decoupler_off`（`dynamic_ab`，`module_enabled={'decoupler': False}`）
- 两臂仅 `enable_ar` 不同，差异可归因于 AR 解耦。

**核心产出**:
1. `AblationRunner.run_l1_decoupler()`（2 臂，支持参照复用）
2. `_collect_rho_steps` 在 dynamic 中间数据存在时采集 `decoupler` ρ_step
3. `generate_report` 按需追加 `decoupler` 列
4. `run_l1` 的 `market_cap_data` 转发修复（R-1）
5. 新增 1 个测试文件（11 例）; 项目版本 3.4.4

---

## §2 变更清单

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | 新增 `DYNAMIC_L1_MODULES = ['decoupler']`; 新增 `run_l1_decoupler`; `_collect_rho_steps` 追加 decoupler 分支; `generate_report` 条件列; `run_l1` 转发 `market_cap_data` |
| `tests/test_backtest/test_ablation_decoupler_arm.py` | **新增** D1-D11（11 例） |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.4` |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 版本 3.4.3 → 3.4.4 |
| `CHANGELOG.md` / `README.md` / `docs/PROJECT_STATUS.md` / `CODE_WIKI.md` / `DECISIONS.md` | v3.4.4 条目、同步注、ADR-045 实现补充 |
| `docs/research/RESEARCH_ABLATION_DECOUPLER_ARM.md` / `docs/private/DESIGN_ABLATION_DECOUPLER_ARM.md` / 本文件 / `docs/audit/2026-11-13-ablation-decoupler-arm-audit.md` | 步骤 1-2 / 3-4 / 5-6 / 10 工件 |

---

## §3 E1 — 测试（TDD Red）

**文件**: `tests/test_backtest/test_ablation_decoupler_arm.py`

| 编号 | 用例 | 断言 |
|------|------|------|
| D1 | `test_run_l1_decoupler_returns_two_arms` | 返回 2 个结果，顺序 `[L1_dynamic_ref, L1_decoupler_off]`，`layer='L1'`，`baseline_level='B3'` |
| D2 | `test_ref_arm_routing_is_dynamic` | 参照臂 `routing_mode='dynamic'` 且 `module_enabled is None` |
| D3 | `test_off_arm_disables_decoupler_only` | 实验臂 `module_enabled == {'decoupler': False}` 且 `routing_mode='dynamic'` |
| D4 | `test_pipeline_mode_injected_dynamic_ab` | patch `FactorProcessingPipelineV2`，两次构造的 `pipeline_mode` 均为 `'dynamic_ab'` |
| D5 | `test_module_enabled_propagates` | 两次构造中仅实验臂 `module_enabled == {'decoupler': False}` |
| D6 | `test_dynamic_ref_result_reused` | 传入参照 → `run_single` 仅调用 1 次，且参照对象 identity 复用 |
| D7 | `test_rho_step_decoupler_computed` | dynamic 中间数据（`imputation`/`decoupling`）→ `rho_step['decoupler']` 存在且 `< 1.0` |
| D8 | `test_rho_step_decoupler_absent_for_unified` | unified 中间数据 → 无 `decoupler` 键，键集合仍为原 5 项 |
| D9 | `test_report_decoupler_column_conditional` | 有 decoupler 数据 → 表头含 `decoupler`；无 → 不含 |
| D10 | `test_run_l1_forwards_market_cap_data` | 传入市值 → 6 次 `run_single` 均收到该对象；未传 → 不出现该关键字 |
| D11 | `test_run_l1_decoupler_end_to_end` | 小规模合成面板真实运行：2 结果、IC 非 NaN、两臂 `rho_step` 均含 `decoupler` |

**Red 预期**: D1-D3 因方法不存在报 `AttributeError`；D7/D9/D10 因功能缺失断言失败；D4-D6/D8/D11 可能因方法缺失一并失败。

**运行**:
```
pytest tests/test_backtest/test_ablation_decoupler_arm.py -q
```

---

## §4 E2 — 实现（Green）

### 4.1 常量

```python
# v3.4.4: 仅在 dynamic_ab 下可测的 L1 步骤 (不并入 L1_MODULES,
# 以保持 unified/B0 的 ρ_step 键集合不变)
DYNAMIC_L1_MODULES = ['decoupler']
```

### 4.2 `run_l1_decoupler`

```python
def run_l1_decoupler(
    self,
    factor_data: Dict[str, pd.DataFrame],
    fwd_returns: pd.DataFrame,
    industry_data: Optional[pd.Series] = None,
    market_cap_data: Optional[pd.DataFrame] = None,
    dynamic_ref_result: Optional[AblationResult] = None,
) -> List[AblationResult]:
    results: List[AblationResult] = []

    # 仅非 None 时注入, 与 run_l1 一致, 保持既有 monkeypatch 签名兼容
    extra_kwargs = {}
    if market_cap_data is not None:
        extra_kwargs['market_cap_data'] = market_cap_data

    if dynamic_ref_result is not None:
        results.append(dynamic_ref_result)
    else:
        ref_config = AblationConfig(
            name='L1_dynamic_ref', layer='L1',
            routing_mode='dynamic', baseline_level='B3',
        )
        results.append(self.run_single(
            ref_config, factor_data, fwd_returns, industry_data,
            **extra_kwargs))

    off_config = AblationConfig(
        name='L1_decoupler_off', layer='L1',
        routing_mode='dynamic', module_enabled={'decoupler': False},
        baseline_level='B3',
    )
    results.append(self.run_single(
        off_config, factor_data, fwd_returns, industry_data,
        **extra_kwargs))
    return results
```

### 4.3 `_collect_rho_steps`

```python
steps = list(self.L1_MODULES)
if any('decoupling' in data for data in intermediate.values()):
    steps.append('decoupler')

for step in steps:
    ...
    elif step == 'decoupler':
        before = self._get_intermediate(intermediate, 'imputation', None)
        after = self._get_intermediate(intermediate, 'decoupling', None)
```

### 4.4 市值转发（R-1，两处断链）

```python
# run_l1 —— 入口转发
extra = {}
if market_cap_data is not None:
    extra['market_cap_data'] = market_cap_data
...
self.run_single(b3_config, factor_data, fwd_returns, industry_data, **extra)
```

```python
# run_single B3 分支 —— 向 _run_pipeline 转发
pipeline_kwargs = {}
if market_cap_data is not None:
    pipeline_kwargs['market_cap_data'] = market_cap_data
self._run_pipeline(
    config, factor_data, fwd_returns, industry_data, **pipeline_kwargs)
```

两处均"仅非 None 时注入"，以兼容既有 monkeypatch 测试签名。

### 4.5 `generate_report` 条件列

```python
rho_steps = list(self.L1_MODULES)
if any('decoupler' in r.rho_step for r in results):
    rho_steps.append('decoupler')
lines.append('| Experiment | ' + ' | '.join(rho_steps) + ' |')
...
for r in results:
    lines.append(
        f"| {r.config.name} | "
        + ' | '.join(_fmt(r.rho_step.get(s, float('nan')), 3) for s in rho_steps)
        + ' |'
    )
```

---

## §5 E3 — 版本与文档

- 项目版本 6 处锚点统一为 `3.4.4`（`__init__.py` / `config_v2.py` / `reporting.py` / `pyproject.toml` / 两个测试锚点）。
- 缓存代际不变：`v2.3.0-cache`（本次不改变中间产物数值；仅新增实验臂）。
- CHANGELOG / README / PROJECT_STATUS / CODE_WIKI / DECISIONS 同步。

---

## §6 工程细节检查（§13.5）

| 维度 | 检查项 | 结论 |
|------|--------|------|
| 工程细节 | 空数据 / 短序列 / 市值 None | 复用既有 `run_single` 与 Dynamic 降级路径 |
| 版本 | Python 最低版本 / 依赖 | 无新增依赖；沿用 pandas/numpy/scipy |
| 依赖 | 新增 import | 无 |
| 兼容 | 默认 `run_l1` 6 臂、unified ρ 5 键、报告 5 列 | 不变 |
| 接口 | `run_single` / `AblationConfig` / `_get_intermediate` 签名 | 与源码一致 |
| 签名 | 新方法全部关键字参数可选 | `market_cap_data` / `dynamic_ref_result` 默认 None |
| 低效操作 | 是否 N 次循环/重复拟合 | 每个臂 1 次管线拟合；参照可复用 |

---

## §7 TDD 验收标准

| 阶段 | 命令 | 期望 |
|------|------|------|
| Red | `pytest tests/test_backtest/test_ablation_decoupler_arm.py -q` | 至少 6 failed（方法/功能缺失） |
| Green | 同上 | **11 passed** |
| 定向回归 | `pytest tests/test_backtest/test_ablation_runner.py tests/test_backtest/test_ablation_decoupler_arm.py tests/test_dynamic_component_separability.py tests/test_fix3_version_unification.py -q` | 全绿 |
| 全量回归 | `pytest -q` | **1705 passed / 15 skipped / 0 failed** (1063.50s) |

---

## §8 风险与回滚

| 风险 | 缓解 |
|------|------|
| Dynamic 臂在小样本上 AR 拟合不稳定 | 沿用 ADR-040/041 的降级与 hold_back 逻辑；D11 使用足以拟合的合成面板 |
| 报告列变化影响字符串断言 | 仅当结果含 `decoupler` 键时新增列；既有测试结果不含该键 |
| 校验调用的 monkeypatch 不含 `market_cap_data` | `run_l1` 仅在参数非 None 时转发 |
| 版本锚点遗漏 | `test_fix3_version_unification.py` + 手工校验脚本双重覆盖 |

**回滚**: 删除 `run_l1_decoupler` 与 `DYNAMIC_L1_MODULES`、还原 `_collect_rho_steps`/`generate_report`/`run_l1` 三处改动；无数据迁移、无缓存失效。

---

## §9 Review 记录（步骤 6）

| 级别 | 检查项 | 结果 | 修正 |
|------|--------|------|------|
| 引用 | 学术引用与 RESEARCH 逐条一致 | ✅ | — |
| API | `AblationConfig` 字段名/默认值 | ✅ `routing_mode='dynamic'`, `module_enabled` | — |
| 签名 | `run_single` 的 `market_cap_data` 位置与关键字 | ✅ 关键字传入 | — |
| 中间数据键 | `'imputation'` / `'decoupling'` | ✅ `pipelines_v2.py:813/837` | — |
| 兼容 | 默认 run_l1 6 臂 / ρ 5 键 / 报告 5 列 | ✅ | 方案 A/B 已否决 |
| 算术 | 全量基线 1682 (v3.4.3 记录值) + 12 (R-2 补测未重跑) + 11 = 1705 | ✅ | — |
| 依赖 | 无新增依赖 | ✅ | — |
