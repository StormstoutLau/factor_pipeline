# RESEARCH L1/L2 消融臂 trivial 判定口径 (L1L2_TRIVIAL_CALIBER)

> **版本**: v1.0 (2026-11-16)
> **上游**: [RESEARCH_ABLATION_TRIVIAL_CALIBER.md v1.1](RESEARCH_ABLATION_TRIVIAL_CALIBER.md) (v3.4.8, L4 同族修复)
> **范围**: `AblationRunner.run_l1` / `run_l2` 中与 B3 参照实跑口径相同、却未标记
> `_is_trivial` 的臂; 以及「按实跑口径判定」在 base_config 为非默认值时的边界。

## §1 调研问题清单

- **Q1**: BH-FDR 的 `m` 如何定义? 把已知零效应的假设计入 `m` 的后果? (沿用 v3.4.8)
- **Q2**: 是否存在「预过滤无信息假设可提高检测力」的权威结论? (沿用 v3.4.8)
- **Q3**: `run_l1` 的 5 个消融臂在默认 `base_config` 下, 哪些与 B3 实跑口径相同?
- **Q4**: `run_l2` 的 2 个臂在默认 `base_config` 下, 哪些与 B3 实跑口径相同?
- **Q5**: B3 参照的 `pipeline_mode` 由谁决定? 调用方 `base_config.pipeline_mode` 是否有影响?
- **Q6**: `base_config.module_enabled` / `orthogonalization` 非默认时, 上述结论如何变化?
- **Q7**: `run_l1_decoupler` 的参照臂 (`L1_dynamic_ref`) 是否属于同一问题族?

## §2 学术文献调研

本轮不引入新引用。统计依据与 v3.4.8 完全同族, 复用两条已核实文献:

| 引用 | 标识 | 关键结论 | 状态 |
|------|------|---------|------|
| Benjamini & Hochberg (1995), JRSS-B 57(1):289-300 | DOI: 10.1111/j.2517-6161.1995.tb02031.x | `q_(i) = p_(i) · m / i`; `m` 为参与检验假设总数, `m` 增大会收紧阈值 | ✅ VERIFIED (v3.4.8 已核实) |
| Bourgon, Gentleman & Huber (2010), PNAS 107(21):9546-9551 | DOI: 10.1073/pnas.0914005107 | 以「与检验统计量独立」的准则先过滤无信息变量, 可在控制 FDR 前提下提升检测力 | ✅ VERIFIED (v3.4.8 已核实) |

**适用性**: 本轮处理的臂 Δ 恒为 0 (实跑口径与 B3 相同), 属结构零假设; 计入 `m`
只收紧其余臂阈值, 无信息增益。结论与 v3.4.8 一致, 不再重复推导。

## §3 工程事实 (F1-F14)

| # | 事实 | 证据 |
|---|------|------|
| F1 | `AblationConfig.routing_mode` 默认 `'full'` | [ablation_runner.py L326](../../backtest/ablation_runner.py#L326) |
| F2 | `routing_mode='full'` 与 `'unified'` 均注入 `pipeline_mode='unified'`; 仅 `'dynamic'` 注入 `'dynamic_ab'` | [ablation_runner.py L566-L575](../../backtest/ablation_runner.py#L566-L575) |
| F3 | `run_l2` 构造 `L2_unified` (`routing_mode='unified'`) 与 `L2_dynamic` (`'dynamic'`), 均未设置 `_is_trivial` | [ablation_runner.py L1011-L1037](../../backtest/ablation_runner.py#L1011-L1037) |
| F4 | `run_l1` 构造 4 个 `module_enabled={module: False}` 臂 + 1 个 `ortho_enabled=False` 臂, 均未设置 `_is_trivial` | [ablation_runner.py L915-L939](../../backtest/ablation_runner.py#L915-L939) |
| F5 | `module_enabled` 的生效方式是**整体替换** (`config.module_enabled or module_override`), 不与 `base_config.module_enabled` 合并 | [ablation_runner.py L549-L551](../../backtest/ablation_runner.py#L549-L551) |
| F6 | 关闭正交化的前提是 `modified_config.orthogonalization is not None`; 为 `None` 时静默跳过 | [ablation_runner.py L553-L559](../../backtest/ablation_runner.py#L553-L559) |
| F7 | `PipelineV2Config.orthogonalization` 默认 `None` | [pipelines_v2.py L492-L494](../../pipelines_v2.py#L492-L494) |
| F8 | 仅当 `orthogonalization is not None and enabled=True` 才挂载 `OrthogonalizerAdapter` | [pipelines_v2.py L1088-L1094](../../pipelines_v2.py#L1088-L1094) |
| F9 | `PipelineV2Config.module_enabled` 默认 `None` (不覆盖) | [pipelines_v2.py L520-L522](../../pipelines_v2.py#L520-L522) |
| F10 | Adapter 层按 key 读取开关, 缺省 `True` (全启用) | [pipelines_v2.py L801-L804](../../pipelines_v2.py#L801-L804) |
| F11 | `compare_all` 用 `non_trivial_indices` 排除 trivial 比较; trivial 的 `is_significant` 强制 `False` | [ablation_runner.py L1367-L1391](../../backtest/ablation_runner.py#L1367-L1391) |
| F12 | L1-L4 消融表共用表头, 已含 `Wiring` 列 | [ablation_runner.py L1516-L1536](../../backtest/ablation_runner.py#L1516-L1536) |
| F13 | 既有测试只断言臂数与臂名, 无 trivial 断言 | [test_ablation_runner.py L593-L640](../../tests/test_backtest/test_ablation_runner.py#L593-L640) |
| F14 | v3.4.8 已建立「实跑口径判定 + 循环外一次告警 + 外部参照口径提示」模式 | [EXECUTION v3.4.8 §3.1-§3.2](../EXECUTION_V3.4.8_ABLATION_TRIVIAL_CALIBER.md) |

## §4 退化臂清单 (Q3-Q5)

### 4.1 `run_l2`

B3 参照的 `AblationConfig` 为默认值 → `routing_mode='full'` → 经 F2 注入
`pipeline_mode='unified'`。`L2_unified` 同样注入 `'unified'`, 且两臂其余字段全同
→ **实跑口径逐位相同**。

`L2_dynamic` 注入 `'dynamic_ab'`, 与 B3 不同 → 非平凡。

**结论**: 默认 `base_config` 下 `run_l2` 的 BH 分母应为 1 (`L2_dynamic`), 现为 2。

### 4.2 `run_l1`

- 4 个 `module_enabled` 臂 (F4): 默认 `base_config.module_enabled is None` (F9),
  臂关闭目标模块后确实改变管线 → 4 臂均非平凡。
- `L1_orthogonalizer_off` (F4): 臂设置 `ortho_enabled=False`, 但 F6 要求
  `orthogonalization is not None` 才生效; 默认 `base_config` 为 `None` (F7),
  且 F8 表明无配置即无 hook → **与 B3 逐位相同**。

**结论**: 默认 `base_config` 下 `run_l1` 的 BH 分母应为 4, 现为 5。

### 4.3 B3 的 `pipeline_mode` 决定权 (Q5)

F2 对 `routing_mode in ('full', 'unified')` 一律写入 `'unified'`,
因此**即使调用方把 `base_config.pipeline_mode` 设为 `'dynamic_ab'`, B3 参照也会被
覆写为 `'unified'`**。`L2_unified` 的 trivial 判定只依赖这一条, 与 `base_config` 无关。

例外: 调用方通过 `b3_full_result` 传入**外部构造**的 B3 时, runner 不校验其
`pipeline_mode` (与 v3.4.6 O3 同一责任划分)。此时 `L2_unified` 可能非平凡,
`L2_dynamic` 反而平凡 — runner 无法反推, 只能提示。

### 4.4 `base_config` 非默认时的边界 (Q6)

| `base_config` 状态 | 现状 | 正确处理 |
|---|---|---|
| `module_enabled` 含 `{m: False}` | 臂 `{m2: False}` **整体替换** (F5), 会把 base 已关闭的 `m` 重新打开 → 臂相对 B3 混入「恢复 base」效应 | 臂应在 base 基础上覆盖: `{**base, m2: False}` — 只改变目标模块 |
| `module_enabled` 已含目标模块 `False` | 臂 override 后实际仍关闭, 与 B3 同口径, 但未标 trivial | 按实跑口径判 trivial |
| `orthogonalization` 存在且 `enabled=True` | `L1_orthogonalizer_off` 真实生效, 非平凡 | 判据须读取 base 而非固定 `True`/`False` |
| `orthogonalization` 存在但 `enabled=False` | 无 hook (F8), 与 B3 同口径 | 判 trivial |

**结论**: 判据必须是**运行时可求值的**, 不能按臂名硬编码; 同时应用合并语义修复
F5 的污染问题。默认 `base_config` 下两者皆不改变既有输出秩。

### 4.5 `run_l1_decoupler` (Q7)

参照臂为 `L1_dynamic_ref` (显式 `routing_mode='dynamic'`, 中性化 + AR 全开),
不是 B3; 实验臂 `module_enabled={'decoupler': False}` 真实关闭 AR →
**不属于本问题族**, 本轮不改。

## §5 待核实项 (⚠️ UNVERIFIABLE)

- 无新增文献, 无需外部核实。
- F5 的「整体替换」为代码直读结论; `module_enabled` 在 Adapter 层的缺省 `True`
  由 F10 佐证, 但未逐 Adapter 列举全部 key, 仅覆盖 L1 的 4 个模块。

## §6 调研结论

1. **可直接引用**: BH (1995) 的 `m` 定义与 Bourgon et al. (2010) 的独立过滤结论;
   `_is_trivial` 语义 = 「与 baseline 同口径」。
2. **已证实**: 默认 `base_config` 下 `L2_unified` 与 `L1_orthogonalizer_off`
   均为 B3 的实跑复制, 却计入 BH 分母 (F2/F3/F6/F7/F8/F9)。
3. **已证实**: `run_l1` 的 `module_enabled` 覆盖是整体替换, 对非默认 base 会污染归因 (F5)。
4. **处置方向**:
   - `run_l2`: `L2_unified` 标 `_is_trivial=True`; 外部 `b3_full_result` 时提示口径未校验;
   - `run_l1`: 按 `base_config.module_enabled` / `orthogonalization` 实跑口径判定 trivial;
     臂的 `module_enabled` 改为在 base 之上合并覆盖; 退化时一次告警;
   - 报告不加新列: `Wiring` 保持 `wired` / `diagnostic` 两值, 不引入第三值;
     trivial 仍只在数据层 (`_is_trivial`) 表达, 与 v3.4.8 的 L4 处理一致。
5. **不做**: 不改 `run_l1_decoupler`; 不改臂数/臂名; 不改 `compare_all`; 不动生产管线。

## §7 步骤 2 review 记录 (2026-11-16, v1.0)

| 检查维度 | 检查方式 | 结果 |
|---------|---------|------|
| 引用真实性 | 本轮无新引用; BH (1995) / Bourgon et al. (2010) 沿用 v3.4.8 已核实条目, DOI 与卷期一致 | ✅ 无臆造 |
| 行号准确性 | 逐条回读 `ablation_runner.py` L326 / L549-575 / L915-939 / L1011-1037 / L1367-1391 / L1516-1536、`pipelines_v2.py` L492-494 / L520-522 / L801-804 / L1088-1094、测试 L593-640 | ✅ 全部一致 |
| 符号准确性 | `routing_mode` / `module_enabled` / `ortho_enabled` / `orthogonalization` / `_is_trivial` / `non_trivial_indices` / `_wiring_status` 均真实存在 | ✅ |
| 结论可推导性 | `L2_unified` 退化由 F1+F2+F3 推出; `L1_orthogonalizer_off` 退化由 F4+F6+F7+F8 推出; F5 污染结论由代码直读 | ✅ |
| 过度断言 | ① 首稿称「`Wiring` 可标 `default`」属越界设计 (该字段语义是接线状态, 非口径状态), 已删除并改为「不引入第三值」; ② `pipeline_mode` 覆写结论限定在 `run_single` 的内部路径, 已注明外部 `b3_full_result` 例外 | ✅ 已修正 2 处 |

**review 结论**: PASS (0 幻觉; 2 处过度断言已就地修正)。文档状态 v1.0。
