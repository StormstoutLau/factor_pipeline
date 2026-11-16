# EXECUTION v3.4.8 — 消融臂 trivial 判定口径

> **版本**: v1.1 (2026-11-15, 步骤 6 review 后)
> **上游**: [RESEARCH_ABLATION_TRIVIAL_CALIBER.md](research/RESEARCH_ABLATION_TRIVIAL_CALIBER.md) v1.1 /
> DESIGN v1.1 (`docs/private/DESIGN_ABLATION_TRIVIAL_CALIBER.md`)
> **目标**: 无市值时 `L4_neutralization_industry+mktcap` 臂的 trivial 判定按实跑口径,
> 并从 BH-FDR 分母中排除; 退化时输出一次告警。

## §0 概览

| 项 | 值 |
|----|-----|
| 版本 | 3.4.8 (patch) |
| 生产代码改动 | **无** (仅 `backtest/ablation_runner.py`) |
| 测试改动 | 3 个既有用例更新 + 3 个新用例 |
| 依赖 | 无新增 / 无升级 |
| 公共接口 | `run_l4_oat` 签名不变; `AblationConfig` 字段不变 |

## §1 任务清单

| # | 任务 | 文件 | 验收 |
|---|------|------|------|
| E1 | trivial 判定改为实跑口径 + 退化告警 | `backtest/ablation_runner.py` | G1/G2/G5 |
| E2 | 更新 3 个既有断言 (2→3 / 6→5 / 无市值退化臂 trivial) | 3 个测试文件 | 全绿 |
| E3 | 新增 3 例: 无市值 trivial 集合 / 退化告警 / 有市值无告警 | `tests/test_backtest/test_ablation_knob_wiring.py` (复用既有 helper `_runner` / `_data` / `_capture_run_single` / `_make_market_cap`) | 全绿 |
| E4 | 版本 3.4.8 六锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / 2 个版本测试 | 7 passed + 手工 6/6 |
| E5 | 文档同步 | CHANGELOG / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI | 数字一致 |

## §2 工程细节

| 维度 | 结论 |
|------|------|
| 依赖 | 无新增; 仅用标准库 `logging` (已导入) |
| 接口/签名 | `run_l4_oat(factor_data, fwd_returns, industry_data=None, market_cap_data=None, b3_full_result=None)` 不变 |
| 兼容性 | 臂数 9、臂名、`config.neutralization` 原值均不变; 仅 `_is_trivial` 标记在无市值场景 +1 |
| 性能 | 告警在循环外调用一次; 循环内只增加一次字符串比较, 无 I/O |
| 缓存 | 不涉及 (`v2.3.0-cache` 无改动) |
| 低效操作 | 无; 不引入 DataFrame 拷贝或重复遍历 |
| 可观测性 | `logger.warning` (WARNING 级), 文案见 §3.2 |

## §3 代码变更

### 3.1 trivial 判定 ([ablation_runner.py L1135-L1149](../backtest/ablation_runner.py#L1135-L1149))

```python
        for param_name, options in oat_specs:
            for option in options:
                # v3.4.8: trivial 按**实跑口径**判定 — 无市值时
                # 'industry+mktcap' 臂不注入市值, 管线回落至仅行业,
                # 与无市值默认口径一致, 必须从 BH-FDR 分母中排除.
                effective_option = option
                if (param_name == 'neutralization'
                        and option == 'industry+mktcap'
                        and not market_cap_available):
                    effective_option = 'industry'
                is_trivial = (effective_option == defaults.get(param_name))
```

`market_cap_available = market_cap_data is not None` 在 `extra_kwargs` 构造处定义并复用
(与 L1098-L1101 的注入条件保持同一判据)。

### 3.2 退化告警 (循环前一次)

```python
        if not market_cap_available:
            logger.warning(
                "run_l4_oat: 未提供 market_cap_data — "
                "L4_neutralization_industry+mktcap 臂退化为仅行业中性化 "
                "(与无市值默认口径一致), 已标记为 trivial")
            # v3.4.8 (独立复审补充): 外部 B3 口径由调用方负责 (v3.4.6 O3),
            # runner 无法反推; 若其按市值口径计算, 该臂相对 B3 存在真实差异,
            # trivial 标记会把这一比较排除出 BH-FDR 分母.
            if b3_full_result is not None:
                logger.warning(
                    "run_l4_oat: 传入外部 b3_full_result 且未提供 market_cap_data — "
                    "外部 B3 口径未校验 (由调用方负责); 若其按市值口径计算, "
                    "trivial 判定会把真实差异排除出 BH-FDR 分母, "
                    "请同时传入 market_cap_data 以对齐口径")
```

> 文案不使用「与 B3 同口径」: `b3_full_result` 短路分支下 B3 由调用方构造,
> runner 无法校验其口径, 断言与 B3 一致会失真。

### 3.3 不动的部分

- `defaults` 字典 (L1129-L1133) 不变;
- `arm_kwargs` 分支 (L1145-L1149) 不变;
- `config.name` 与 `config.neutralization` 保持原值;
- `compare_all` 的 BH-FDR 过滤逻辑 (L1339-L1364) 不变。

## §4 测试规格 (TDD)

### 4.1 既有用例更新

| 文件:行 | 旧断言 | 新断言 |
|---------|--------|--------|
| `test_ablation_knob_wiring.py` L137-L152 | 2 trivial / 6 非平凡 | 3 trivial (集合含 `L4_neutralization_industry+mktcap`) / 5 非平凡 |
| `test_ablation_runner.py` L1327-L1348 | 2 trivial / 6 非平凡 | 3 trivial / 5 非平凡 |
| `test_ablation_mktcap_alignment.py` L186-L198 | 无市值时 `industry+mktcap` 非 trivial | 该类设为 trivial; 用例更名为 `test_run_l4_without_market_cap_marks_degraded_arm_trivial` |

### 4.2 新增用例 (`tests/test_backtest/test_ablation_knob_wiring.py`, 新类 `TestL4TrivialCaliber`)

> 复用同文件既有 helper (`_runner` / `_data` / `_capture_run_single` / `_make_market_cap`),
> 不新建测试文件, 避免 helper 重复。

| # | 用例 | 断言 |
|---|------|------|
| T1 | `test_no_mktcap_marks_mktcap_arm_trivial` | 无市值: trivial 集合 == {`L4_outlier_method_winsorize_1pct`, `L4_neutralization_industry`, `L4_neutralization_industry+mktcap`} |
| T2 | `test_no_mktcap_emits_degradation_warning` | `caplog` 捕获恰 1 条 WARNING, 文案含 `退化为仅行业` |
| T3 | `test_with_mktcap_trivial_set_unchanged` | 传市值: trivial == {`winsorize_1pct`, `industry+mktcap`}, 且无 `退化为仅行业` 告警 |
| T4 | `test_external_b3_without_mktcap_emits_caliber_hint` | 外部 B3 + 无市值: `results[0] is external_b3`; 恰 1 条 `外部 B3 口径未校验`; 退化告警仍 1 条; trivial 集合不受影响 |

### 4.3 Red → Green 预期

- **Red**: 3 个既有用例全部失败 (2/6 旧断言) + 3 个新用例全部失败 (T1/T3 集合不符, T2 无告警);
- **Green**: 上述 6 例全通过, 定向回归 (`tests/test_backtest`) 全绿;
- **独立复审补充**: T4 于复审后追加, 覆盖「外部 B3 + 无市值」提示分支
  (新增用例总数 4, 定向 3 文件 113 passed)。

## §5 验收标准

| # | 标准 | 实测 | 状态 |
|---|------|------|------|
| A1 | 无市值 9 臂 / 3 trivial / 5 非平凡 | 9 / 3 / 5 (`test_l4_trivial_count`, `test_no_mktcap_marks_mktcap_arm_trivial`) | ✅ |
| A2 | 有市值 9 臂 / 2 trivial / 6 非平凡 | 2 trivial (`test_with_mktcap_trivial_set_unchanged`, `test_run_l4_with_market_cap_switches_default`) | ✅ |
| A3 | 退化告警恰 1 条, 有市值 0 条; 外部 B3 时追加口径提示 1 条 | T2 = 1 条; T3 = 0 条; T4 = 口径提示 1 条且 trivial 不变 | ✅ |
| A4 | `pipelines_v2.py` diff 为空 | 本版未触碰 (仅 `ablation_runner.py`) | ✅ |
| A5 | 定向回归 passed 数 | 580 passed / 8 skipped (1338.27s) | ✅ |
| A6 | 全量回归 passed/skipped | 1728 passed / 15 skipped / 0 failed (2143.86s, T4 追加后复跑) | ✅ |
| A7 | 版本六锚点 = 3.4.8 | 版本测试 7 passed + 手工 6/6 | ✅ |

## §6 回滚

单点改动: 还原 `effective_option` 映射与告警块, 并把 3 个既有断言改回 2/6 即可。
不涉及数据、缓存或配置迁移。

---

## §7 步骤 6 review 记录 (2026-11-15, 幻觉消除 review #2)

| 检查维度 | 检查方式 | 结果 |
|---------|---------|------|
| 签名准确性 | 回读 [ablation_runner.py L1072-L1079](../backtest/ablation_runner.py#L1072-L1079) | ✅ `run_l4_oat(factor_data, fwd_returns, industry_data=None, market_cap_data=None, b3_full_result=None)` 一致 |
| 行号准确性 | 回读 L1098-1101 / L1112-1152 / L1339-1364; 测试 L137-152 / L1327-1348 / L186-198 | ✅ 全部一致 |
| 测试可行性 | 新用例复用同文件 helper (`_runner` / `_data` / `_capture_run_single` / `_make_market_cap`), 已核实均存在 (L52-L83) | ✅ 原「新建文件」方案已改为同文件新类, 避免 helper 复制 |
| 依赖与导入 | 仅 `logging` (L38 已导入); 测试侧 `caplog` 为 pytest 内置 | ✅ 无新增依赖 |
| 兼容性断言 | 臂数/臂名/`config.neutralization` 不变由既有 E1/E2 断言持续守护 | ✅ |
| 低效操作 | 告警在循环外; 循环内仅一次字符串比较 | ✅ |
| 与 DESIGN 一致性 | E1-E5 对应 DESIGN §4.3 的 E1-E5; N1-N5 未被违反 | ✅ |

**review 结论**: PASS (2 处修正: 新用例落位改为既有文件; Red 预期表述)。EXECUTION 更新为 v1.1。
