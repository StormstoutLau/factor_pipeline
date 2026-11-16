# CHECKLIST v3.4.9 — L1/L2 消融臂 trivial 判定口径

> **版本**: v1.0 (2026-11-16)
> **对照工件**: [EXECUTION v1.0](../EXECUTION_V3.4.9_L1L2_TRIVIAL_CALIBER.md) /
> [RESEARCH v1.0](../research/RESEARCH_L1L2_TRIVIAL_CALIBER.md) / DESIGN v1.0
> **使用方式**: 步骤 10 审计时逐项勾选, 任一项未勾选即不得发版。

## A. 代码落地 (E1)

- [x] A1 新增 `_base_module_switches` / `_base_ortho_active` 两个模块级辅助函数
- [x] A2 `run_l1` 模块臂 `module_enabled={**base_modules, module: False}` (合并而非替换)
- [x] A3 `run_l1` 模块臂 `_is_trivial = not base_modules.get(module, True)`
- [x] A4 `run_l1` 正交化臂 `_is_trivial = not base_ortho` (`orthogonalization is not None and enabled`)
- [x] A5 `run_l1` 退化告警在循环外**只调用一次**, 文案含「与 B3 同口径」
- [x] A6 `run_l1` 外部 `b3_full_result` 传入时追加「未校验」提示
- [x] A7 `run_l2` 的 `L2_unified` 标 `_is_trivial=True`, `L2_dynamic` 为 `False`
- [x] A8 `run_l2` 外部 `b3_full_result` 传入时追加「未校验」提示
- [x] A9 臂数 / 臂名 / `AblationConfig` 字段不变; `compare_all` 零改动
- [x] A10 `pipelines_v2.py` 零改动

## B. 测试 (E2/E3)

- [x] B1 E1 默认 base: `run_l1` trivial 集合 = `{L1_orthogonalizer_off}`, 6 结果 / 4 非平凡
- [x] B2 E2 默认 base: `run_l2` trivial 集合 = `{L2_unified}`, 2 结果
- [x] B3 E3 退化告警恰 1 条且含「与 B3 同口径」+ `L1_orthogonalizer_off`
- [x] B4 E4 base 启用正交化 → 该臂非平凡且告警 0 条
- [x] B5 E5 base `{'imputer': False}` → imputer 臂 trivial; scaler 臂非平凡且保留 `imputer: False`
- [x] B6 E6 外部 B3 → `run_l1` / `run_l2` 各 1 条「未校验」, trivial 集合不变
- [x] B7 E7 标记与臂字段一致 (ortho 臂 `ortho_enabled=False`; `L2_dynamic.routing_mode='dynamic'`)
- [x] B8 Red 阶段确认失败 (≥4 failed), Green 阶段全绿

## C. 回归

- [x] C1 定向回归: 4 个消融测试文件 **133 passed** (11.57s); `tests/test_backtest` **588 passed / 8 skipped** (837.23s)
- [x] C2 全量回归 passed ≥ 1728, failed = 0 → **1735 passed / 15 skipped / 0 failed** (1559.39s)
- [x] C3 版本统一测试 7 passed + 手工 6/6

## D. 文档

- [x] D1 CHANGELOG 新增 v3.4.9 段 (行为变更 + 兼容性 + 遗留)
- [x] D2 PROJECT_STATUS §1/§2 更新
- [x] D3 DEV_PROGRESS 路标与模块影响
- [x] D4 CODE_WIKI `run_l1` / `run_l2` 描述与头部版本
- [x] D5 EXECUTION §5 验收表填入实测值 (A1-A7)

## E. 一致性与发版

- [x] E1 六锚点均为 3.4.9
- [x] E2 文档数字与实测一致 (trivial 1/1, 告警 1 条, 提示 2 条, 新增用例 7)
- [x] E3 CONSISTENCY_REVIEW 判定 PASS
- [x] E4 audit 报告 P0/P1 = 0
