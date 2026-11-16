# CHECKLIST v3.4.8 — 消融臂 trivial 判定口径

> **版本**: v1.0 (2026-11-15)
> **对照工件**: [EXECUTION v1.1](../EXECUTION_V3.4.8_ABLATION_TRIVIAL_CALIBER.md) /
> [RESEARCH v1.1](../research/RESEARCH_ABLATION_TRIVIAL_CALIBER.md) / DESIGN v1.1
> **使用方式**: 步骤 10 审计时逐项勾选, 任一项未勾选即不得发版。

## A. 代码落地 (E1)

- [x] A1 `run_l4_oat` 中 `market_cap_available = market_cap_data is not None`
- [x] A2 无市值时 `industry+mktcap` 臂 `effective_option` 归一为 `industry`
- [x] A3 `is_trivial` 基于 `effective_option` 计算
- [x] A4 退化告警在双层循环**之外**只调用一次, 文案含「退化为仅行业」(且不硬断言「与 B3 同口径」)
- [x] A5 `config.name` / `config.neutralization` 保持原值不变
- [x] A6 `defaults` / `arm_kwargs` / `compare_all` BH 过滤逻辑零改动
- [x] A7 `pipelines_v2.py` 零改动
- [x] A8 外部 `b3_full_result` + 无市值时追加一条「外部 B3 口径未校验」提示

## B. 测试 (E2/E3)

- [x] B1 `test_ablation_knob_wiring.py::test_l4_trivial_count` 断言 3 trivial / 5 非平凡
- [x] B2 `test_ablation_runner.py::test_l4_oat_marks_trivial_configs` 断言 3 / 5
- [x] B3 `test_ablation_mktcap_alignment.py` 无市值用例改为断言该臂 trivial (并更名)
- [x] B4 新增 T1 无市值 trivial 集合
- [x] B5 新增 T2 退化告警恰 1 条
- [x] B6 新增 T3 有市值 trivial 集合不变且无告警
- [x] B7 Red 阶段确认失败 (5 failed / 107 passed), Green 阶段 112 passed
- [x] B8 独立复审补充 T4: 外部 B3 + 无市值 → 口径提示恰 1 条, trivial 不变 (定向 3 文件 113 passed)

## C. 回归

- [x] C1 定向回归 `tests/test_backtest` 全绿: 580 passed / 8 skipped (1338.27s); T4 追加后 3 文件复跑 113 passed, 全目录由 C2 全量覆盖
- [x] C2 全量回归 passed ≥ 1723, failed = 0 → **1728 passed / 15 skipped / 0 failed** (2143.86s, T4 追加后复跑)
- [x] C3 版本统一测试 7 passed + 手工 6/6

## D. 文档

- [x] D1 CHANGELOG 新增 v3.4.8 段 (行为变更 + 兼容性)
- [x] D2 PROJECT_STATUS 路标与 §2 表更新
- [x] D3 DEV_PROGRESS 路标与模块影响
- [x] D4 CODE_WIKI 头部版本与 `run_l4_oat` 描述
- [x] D5 EXECUTION §5 验收表填入实测值 (A1-A7 全部实测)

## E. 一致性与发版

- [x] E1 六锚点均为 3.4.8
- [x] E2 文档数字与实测一致 (trivial 3/5, 告警 1 条 + 外部 B3 提示 1 条, 新增用例 4)
- [x] E3 CONSISTENCY_REVIEW 判定 PASS
- [x] E4 audit 报告 P0/P1 = 0
