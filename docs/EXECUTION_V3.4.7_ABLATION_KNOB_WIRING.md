# 执行: AblationRunner L3/L4 旋钮接线 (v3.4.7)

> **版本**: v1.0 (2026-11-15)
> **调研**: [RESEARCH_ABLATION_KNOB_WIRING.md](research/RESEARCH_ABLATION_KNOB_WIRING.md)
> **设计**: `docs/private/DESIGN_ABLATION_KNOB_WIRING.md`
> **规范**: [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) §13.8

---

## §1 概览

本版把消融框架的 L3/L4 自由度对齐到真实管线能力:

- **最小接线**: `StaticFactorPipeline` 去极值方法/分位点参数化 (默认值 = v3.4.6 硬编码, 零行为变更);
- **臂集合重建**: L4 20→9 结果, L3 25→7 结果; 删除的臂均为「不可接线或重复覆盖」;
- **可解释性**: 新增 `_wiring_status` 标记, CUSUM 诊断型臂全部 trivial 且不进入 BH-FDR 分母。

版本 **3.4.7**; 缓存代际 **`v2.3.0-cache`** 不变。

---

## §2 变更清单

| 文件 | 变更 |
|------|------|
| `pipelines_v2.py` | `PipelineV2Config` +3 字段; `StaticFactorPipeline.__init__` +3 参数; `_create_pipeline('static')` 注入 |
| `backtest/ablation_runner.py` | `AblationConfig._wiring_status`; `L4_OUTLIER_MAP`; `_apply_l4_overrides` 重写 outlier 段并删除死注入; `run_l4_oat` / `run_l3` 臂集合重建; 报告新增 `Wiring` 列 |
| `tests/test_backtest/test_ablation_runner.py` | 更新 L4/L3 臂数、trivial、注入断言; 删除已移除族的测试 |
| `tests/test_backtest/test_ablation_mktcap_alignment.py` | 臂数 25→7 / 20→9; 非中性化臂 16→5 |
| `tests/test_backtest/test_ablation_knob_wiring.py` | **新增** E1-E12 |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.6 → 3.4.7 |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.7` |
| `CHANGELOG.md` / `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` / `CODE_WIKI.md` | 发版同步 |

---

## §3 测试规格 (E1-E12)

| # | 用例 | 断言 |
|---|------|------|
| E1 | `test_run_l4_oat_returns_9` | 9 结果 = B3 + 8 臂 |
| E2 | `test_run_l4_outlier_arm_configs` | 4 臂的 `outlier_method` 字段正确 |
| E3 | `test_l4_outlier_maps_to_static_config` | `3sigma→z_score`; `mad→mad`; `1pct→(percentile,1,99)`; `5pct→(percentile,5,95)` |
| E4 | `test_l4_missing_drop_disables_imputer` | `module_enabled['imputer'] is False` |
| E5 | `test_l4_neutralization_market_cap_rules` | `industry` 臂不带市值; `none` / `industry+mktcap` 带 |
| E6 | `test_l4_trivial_count` | 2 trivial / 6 non-trivial |
| E7 | `test_run_l3_returns_7` | 7 结果 = B3 + 6 CUSUM |
| E8 | `test_l3_arms_are_diagnostic_and_trivial` | 6 臂 `_is_trivial=True` 且 `_wiring_status='diagnostic'` |
| E9 | `test_l3_removed_families_absent` | 无 `L3_ewma_*` / `L3_threshold_*` / `L3_winsorize_*` / `L3_correction_*` |
| E10 | `test_pipeline_default_outlier_params` | config 默认 `percentile/1.0/99.0`; 管道 outlier 步骤参数同值 |
| E11 | `test_non_percentile_skips_percentiles` | `outlier_method='mad'` → adapter `method=='mad'` |
| E12 | `test_l3_all_trivial_bh_empty` | 6 全 trivial → `apply_bh_fdr([])`, 无显著, 总比较 6 |

---

## §4 代码

### §4.1 `pipelines_v2.PipelineV2Config`

`static_transformation_method` 之后新增:

```python
    # v3.4.7: Static 管道去极值参数 (默认值与 v3.4.6 硬编码一致, 零行为变更)
    static_outlier_method: str = 'percentile'
    static_outlier_percentile_lower: float = 1.0
    static_outlier_percentile_upper: float = 99.0
```

### §4.2 `StaticFactorPipeline.__init__`

```python
    def __init__(self, ..., module_enabled=None,
                 outlier_method: str = 'percentile',
                 outlier_percentile_lower: float = 1.0,
                 outlier_percentile_upper: float = 99.0):
        ...
        outlier_kwargs = {}
        if outlier_method in ('percentile', 'quantile'):
            outlier_kwargs = {
                'percentile_lower': outlier_percentile_lower,
                'percentile_upper': outlier_percentile_upper,
            }
        self.steps = [
            ...
            ('outlier', ProcessingAdapter(process_type='outlier', method=outlier_method,
                                          enabled=me.get('winsorizer', True),
                                          **outlier_kwargs)),
            ...
        ]
```

### §4.3 `_create_pipeline('static')`

```python
            return StaticFactorPipeline(
                ...,
                module_enabled=module_enabled,
                outlier_method=self.config.static_outlier_method,
                outlier_percentile_lower=self.config.static_outlier_percentile_lower,
                outlier_percentile_upper=self.config.static_outlier_percentile_upper,
            )
```

### §4.4 `AblationConfig`

```python
    # ── M5 修正: 平凡比较标记 ──
    _is_trivial: bool = False
    # v3.4.7: 接线状态 — 'wired' (作用于处理链) | 'diagnostic' (只改诊断)
    _wiring_status: str = 'wired'
```

L3 保留字段 (`ewma_halflife` / `ewma_alpha` / `routing_threshold_scale` / `winsorize_ratio` /
`correction_method`) 与 L4 保留字段 (`scaler_method` / `time_align` / `data_window`) 加注释:
`保留字段, 本版起无消费者`.

### §4.5 `_apply_l4_overrides`

```python
    # 臂名 → (method, percentile_lower, percentile_upper)
    L4_OUTLIER_MAP = {
        '3sigma': ('z_score', None, None),
        'mad': ('mad', None, None),
        'winsorize_1pct': ('percentile', 1.0, 99.0),
        'winsorize_5pct': ('percentile', 5.0, 95.0),
    }

        if ablation_config.outlier_method is not None:
            try:
                method, lower, upper = self.L4_OUTLIER_MAP[
                    ablation_config.outlier_method]
            except KeyError:
                raise ValueError(...)
            modified_config.static_outlier_method = method
            if lower is not None:
                modified_config.static_outlier_percentile_lower = lower
                modified_config.static_outlier_percentile_upper = upper
```

删除: `_l4_outlier_method` / `_l4_scaler_method` / `_l4_imputer_strategy(median,knn)` /
`_l4_time_align` / `_l4_data_window` / `_l4_neutralization` 注入 (复审收口: 中性化口径完全由
runner 层 `market_cap_data` 转发控制, `industry` / `industry+mktcap` 臂不写 config)。

### §4.6 `run_l4_oat`

```python
        oat_specs = [
            ('outlier_method', ['3sigma', 'mad', 'winsorize_1pct', 'winsorize_5pct']),
            ('missing_method', ['drop']),
            ('neutralization', ['none', 'industry', 'industry+mktcap']),
        ]
        defaults = {
            'outlier_method': 'winsorize_1pct',
            'neutralization': (
                'industry+mktcap' if market_cap_data is not None else 'industry'),
        }
```

### §4.7 `run_l3`

```python
        for k in [0.25, 0.5, 0.75]:
            config = AblationConfig(
                name=f'L3_cusum_oat_k{k}', layer='L3', baseline_level='B3',
                cusum_k=k, cusum_h=5.5,
                _is_trivial=True, _wiring_status='diagnostic',
            )
        for h in [4.0, 5.5, 7.0]:
            config = AblationConfig(
                name=f'L3_cusum_oat_h{h}', layer='L3', baseline_level='B3',
                cusum_k=0.5, cusum_h=h,
                _is_trivial=True, _wiring_status='diagnostic',
            )
```

### §4.8 `generate_report`

L1-L4 表新增 `Wiring` 列:

```python
f"| {r.config.name} | ... | {_sig_mark(c)} | "
f"{getattr(r.config, '_wiring_status', 'wired')} |"
```

---

## §5 版本

3.4.7 (6 处锚点), 缓存代际 `v2.3.0-cache` 不变, 无新增依赖。

---

## §6 工程检查

```powershell
python -m pytest tests/test_backtest/test_ablation_knob_wiring.py -q
python -m pytest tests/test_backtest/ -q
python -m pytest tests -q
```

---

## §7 验收

| 层级 | 结果 |
|------|------|
| TDD Red | ✅ 16 failed (新增 E1-E12 + 更新后的臂数/注入断言在原实现上全部失败) |
| TDD Green | ✅ `test_ablation_knob_wiring.py` / `test_ablation_mktcap_alignment.py` / `test_ablation_runner.py` 全部通过 |
| 定向回归 | ✅ `tests/test_backtest`: 576 passed, 8 skipped (24:02) |
| 版本统一 | ✅ `verify_fix3_manual.py`: 5/5 (6 处锚点 = 3.4.7, 缓存 `v2.3.0-cache` 独立) |
| 全量回归 | ✅ 1723 passed, 15 skipped (41:49; 基线 1715 + 新增 8) |
| 审计 | ✅ P0/P1 = 0, 93 分 (A), PASS |

---

## §8 风险

| # | 风险 | 处置 |
|---|------|------|
| R1 | 臂数量下降被误读为功能回退 | §1 + CHANGELOG 明示删除项均为不可接线/重复覆盖 |
| R2 | 既有测试断言旧臂数 | 先改测试 (Red) 再改实现 (Green) |
| R3 | 默认去极值参数与 v3.4.6 不一致 | E10 锁定三元组; 全量回归兜底 |
| R4 | 保留的 `AblationConfig` 死字段被再次使用 | docstring 标注 + 审计登记 |

---

## §9 Review

| 检查 | 结论 |
|------|------|
| 覆盖 RESEARCH 全部处置建议 | ✅ O2-O5 逐条落地; O1 由 `_wiring_status` 解决 |
| 测试是否可失败 (Red) | ✅ 旧实现无 `static_outlier_*` 字段 → E3/E10/E11 失败; 臂数断言失败 |
| 零默认行为变更 | ✅ 三元组同值, `outlier_kwargs` 仅在 percentile/quantile 分支构造 |
| 是否触碰 ADR-040/042 | ✅ 否 |
