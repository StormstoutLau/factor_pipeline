# EXECUTION — L1/L2 消融臂 trivial 判定口径 (v3.4.9)

> **版本**: v1.0 (2026-11-16)
> **上游**: [RESEARCH v1.0](../research/RESEARCH_L1L2_TRIVIAL_CALIBER.md) /
> [DESIGN v1.0](private/DESIGN_L1L2_TRIVIAL_CALIBER.md)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 5-6

## §1 目标

1. `run_l2`: `L2_unified` 与 B3 实跑口径相同 → 标 `_is_trivial=True`;
2. `run_l1`: 按 `base_config` 实跑口径判定 5 个臂的 trivial 状态;
3. `run_l1` 的模块臂改为在 base 开关之上合并覆盖 (修复非默认 base 的归因污染);
4. 两类退化各有一次告警; 外部 `b3_full_result` 传入时提示口径未校验。

## §2 版本与缓存

| 项 | 值 |
|---|---|
| 项目版本 | **3.4.9** (6 处锚点) |
| 缓存代际 | **`v2.3.0-cache`** (不变) |
| 生产管线 | `pipelines_v2.py` **零改动** |
| 消融臂数 | L1 = 6 结果, L2 = 2 结果 (不变) |

## §3 代码变更 (`backtest/ablation_runner.py`)

### 3.1 新增模块级辅助函数 (L394 之后, `AblationRunner` 之前)

```python
# =============================================================================
# v3.4.9: L1/L2 trivial 口径判定辅助 (只读 base_config, 无副作用)
# =============================================================================

def _base_module_switches(base_config: Any) -> Dict[str, bool]:
    """读取 base_config 的模块开关 (None = 全启用)."""
    return dict(getattr(base_config, 'module_enabled', None) or {})


def _base_ortho_active(base_config: Any) -> bool:
    """base_config 是否真正启用正交化 (有配置且 enabled=True)."""
    ortho = getattr(base_config, 'orthogonalization', None)
    return bool(ortho is not None and getattr(ortho, 'enabled', False))
```

### 3.2 `run_l1` (L888-L941)

在 `extra_kwargs` 构造之后、B3 参照之前插入:

```python
        # v3.4.9: trivial 按 base_config 实跑口径判定 —
        # base 已关闭的模块 / 未启用正交化时, 对应臂与 B3 同口径,
        # 必须退出 BH-FDR 分母.
        base_modules = _base_module_switches(self.base_config)
        base_ortho = _base_ortho_active(self.base_config)
        degraded_arms = [
            f'L1_{module}_off'
            for module in ('imputer', 'winsorizer', 'scaler', 'neutralizer')
            if not base_modules.get(module, True)
        ]
        if not base_ortho:
            degraded_arms.append('L1_orthogonalizer_off')
        if degraded_arms:
            logger.warning(
                "run_l1: 以下臂与 B3 同口径 (base_config 未启用正交化或已关闭"
                "对应模块), 已标记为 trivial: %s", ", ".join(degraded_arms))
        if b3_full_result is not None:
            logger.warning(
                "run_l1: 传入外部 b3_full_result — 其 module_enabled / "
                "orthogonalization 未校验 (由调用方负责); 若与 base_config "
                "口径不同, trivial 标记可能反转")
```

模块臂循环改为:

```python
        for module in ['imputer', 'winsorizer', 'scaler', 'neutralizer']:
            config = AblationConfig(
                name=f'L1_{module}_off',
                layer='L1',
                # v3.4.9: 在 base 之上合并覆盖, 不再整体替换 —
                # 避免把 base 已关闭的其他模块重新打开 (归因污染).
                module_enabled={**base_modules, module: False},
                baseline_level='B3',
                _is_trivial=not base_modules.get(module, True),
            )
```

正交化臂改为:

```python
        ortho_config = AblationConfig(
            name='L1_orthogonalizer_off',
            layer='L1',
            ortho_enabled=False,
            baseline_level='B3',
            _is_trivial=not base_ortho,
        )
```

docstring 增补: 「v3.4.9: trivial 按 base_config 实跑口径判定; 外部 b3_full_result
的开关口径由调用方负责, runner 只提示不校验。」

### 3.3 `run_l2` (L1004-L1037)

```python
        # v3.4.9: L2_unified 与 B3 同口径 — routing_mode='full' 与 'unified'
        # 都注入 pipeline_mode='unified' (_run_pipeline 内的 else 分支),
        # 实跑逐位相同, 标记 trivial 退出 BH-FDR 分母.
        routing_configs = [
            ('L2_unified', 'unified', True),
            ('L2_dynamic', 'dynamic', False),
        ]
```

循环改为解包三元组并传入 `_is_trivial`:

```python
        for name, mode, is_trivial in routing_configs:
            config = AblationConfig(
                name=name,
                layer='L2',
                routing_mode=mode,
                baseline_level='B3',
                _is_trivial=is_trivial,
            )
```

外部 B3 分支之前:

```python
        if b3_full_result is not None:
            logger.warning(
                "run_l2: 传入外部 b3_full_result — 其 pipeline_mode 未校验 "
                "(由调用方负责); 若不为 unified, L2_unified 与 L2_dynamic "
                "的 trivial 标记均可能反转")
```

docstring 增补: 「v3.4.9: L2_unified 与 B3 同口径 (均为 unified), 标记 trivial。」

## §4 测试变更 (`tests/test_backtest/test_ablation_knob_wiring.py`)

新增类 `TestL1L2TrivialCaliber` (E1-E7), 复用文件内 `_data()` / `_capture_run_single()`;
新增本地 helper `_runner_with(base_config)` 以注入自定义 `PipelineV2Config`。

| # | 用例 | 断言 |
|---|------|------|
| E1 | `test_run_l1_marks_ortho_arm_trivial` | trivial 集合 `{L1_orthogonalizer_off}`, 6 结果, 4 非平凡 |
| E2 | `test_run_l2_marks_unified_arm_trivial` | trivial 集合 `{L2_unified}`, 2 结果 |
| E3 | `test_run_l1_emits_degradation_warning` | 恰 1 条含「与 B3 同口径」且含 `L1_orthogonalizer_off` |
| E4 | `test_run_l1_with_active_ortho_keeps_arm_non_trivial` | base 含 `orthogonalization(enabled=True)` → 非平凡, 告警 0 条 |
| E5 | `test_run_l1_merges_base_module_switches` | base `{'imputer': False}` → imputer 臂 trivial 且 dict == `{'imputer': False}`; scaler 臂非平凡且 dict == `{'imputer': False, 'scaler': False}` |
| E6 | `test_external_b3_emits_caliber_hint` | `run_l1` / `run_l2` 各 1 条「未校验」; trivial 集合不变 |
| E7 | `test_trivial_flags_match_arm_fields` | ortho 臂 `ortho_enabled is False`; `L2_dynamic.routing_mode == 'dynamic'` 且非 trivial |

对既有测试的影响: `test_run_l1_returns_6_results` / `test_run_l2_returns_2_results`
只断言臂数与臂名, 不需修改。

## §5 验收标准

| # | 标准 | 实测 |
|---|------|------|
| A1 | 默认 base 下 L1 trivial = 1, L2 trivial = 1 | ✅ E1/E2 (5 臂中 1 trivial / 2 臂中 1 trivial) |
| A2 | 退化告警恰 1 条, 外部参照提示各 1 条 | ✅ E3 / E5 / E6 |
| A3 | 臂数 / 臂名 / 臂字段 (除 `_is_trivial`) 不变 | ✅ 既有 6/2 结果用例 + E7 |
| A4 | `pipelines_v2.py` 无 diff | ✅ `git diff --stat` 仅 `ablation_runner.py` + 测试文件 |
| A5 | 定向回归全绿 | ✅ 4 个消融文件 133 passed; `tests/test_backtest` 588 passed / 8 skipped (837.23s) |
| A6 | 全量回归 0 failed | ✅ 1735 passed / 15 skipped / 0 failed (1559.39s) |
| A7 | 六锚点 = 3.4.9 | ✅ 版本测试 7 passed + 手工 6/6 |

## §6 兼容性

- **默认 `base_config`**: 处理输出逐位不变; 仅 `_is_trivial` 标记与 BH 分母变化
  (L1 5→4, L2 2→1)。属口径修正, 非回归;
- **非默认 `module_enabled`**: 臂的开关由「整体替换」改为「合并覆盖」, 输出可能变化
  — 这是归因修正, 需在 CHANGELOG 标注;
- **公共接口**: `run_l1` / `run_l2` 签名、臂名、`AblationConfig` 字段均不变。

## §7 文档同步清单

CHANGELOG / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI (`run_l1` / `run_l2` 描述);
本文件 §5 回填实测; CHECKLIST / CONSISTENCY_REVIEW / audit 报告。

## §8 步骤 6 review 记录 (2026-11-16, v1.0)

| 检查维度 | 检查方式 | 结果 |
|---------|---------|------|
| 行号锚点 | 回读 `ablation_runner.py` L394 / L888-941 / L1004-1037 与 `config_v2.py` L258 | ✅ 一致 |
| API 真实性 | `logger` 模块级已定义; `Dict` / `Any` 已导入; `AblationConfig(_is_trivial=...)` 为既有用法 (L1231); `OrthogonalizationConfig` 位于 `config_v2.py` 且默认 `enabled=False` | ✅ |
| 测试可实施性 | `_capture_run_single` 已支持 `**kwargs`; `_data()` 可直接复用; E4 需 `OrthogonalizationConfig(enabled=True)` + `PipelineV2Config(orthogonalization=...)`, 两处均为既有公开构造 | ✅ |
| 与 DESIGN 一致 | E1-E7 与 DESIGN §5 表格逐条对应 | ✅ |
| 过度断言 | 未声称「修复后所有臂都真实接线」; 仅声明 L1 的 ortho 臂与 L2 的 unified 臂为口径复制 | ✅ |

**review 结论**: PASS (0 幻觉, 0 需删改片段)。文档状态 v1.0。

