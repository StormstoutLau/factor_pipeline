# v3.4.2 断点监控调度 (O6) — 实施文档

**文档版本**: v1.1 (2026-11-12; v1.0 = 初稿; v1.1 = 异构复审修订)
**目标版本**: **v3.4.2**; 缓存 **`v2.3.0-cache`** (代际不变)
**变更性质**: 新增调度工具 (纯增量, 无统计逻辑/接口变更)
**实施方式**: TDD (Red → Green → 版本/文档)
**规范依据**: [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) v1.3 §13.8 — 中任务裁剪 (步骤 1-6-9-10, 省略 checklist 与一致性 review)
**任务来源**: [设计文档 §9 O6](analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) / [v3.4.0 实施文档 §3.7](EXECUTION_V3.4.0_UNIFIED_ROUTING.md)
**决策记录**: [ADR-044](../DECISIONS.md)

---

## §0 实施摘要

| 项 | 内容 |
|---|------|
| 核心改动 | 新增 `BreakMonitorScheduler`: daily / weekly / monthly 三档节拍, 周期键幂等, 失败不推进; 拒绝数值/tz-aware `as_of`, `cadence` 只读 |
| 不改 | `StructuralBreakMonitor` 类 (统计/自助/配置) 与 `monitor_structural_breaks()` (签名/行为) |
| 代码文件 | `backtest/structural_break_monitor.py` (+129/−2, 同文件同职责域) |
| 测试文件 | 新增 `tests/test_break_monitor_scheduler.py` (22 个测试方法 / 22 个 pytest 用例) |
| 版本同步 | 4 处版本声明 + 2 处测试锚点 |
| 文档 | ADR-044 / CHANGELOG / README / PROJECT_STATUS / ARCHITECTURE / DEV_PROGRESS / 本文档 |
| 验收关键 | 周期幂等、ISO 周跨年、异常不推进、重置、真实监控器集成 |

### 0.1 任务清单

| E | 目标 | 主要文件 | 验收 |
|---|------|---------|------|
| E1 | `BreakMonitorScheduler` 实现 | `backtest/structural_break_monitor.py` | S1–S21 通过 |
| E2 | TDD 测试 | `tests/test_break_monitor_scheduler.py` | Red 收集错误 → Green **22 passed** |
| E3 | 版本 / ADR-044 / 文档同步 | 15 个文件 (13 改 + 2 新增) | 版本统一 7 passed; 手工校验 5/5 |

### 0.2 规模与依赖

| 项 | 值 |
|----|-----|
| 新增测试方法 / pytest 用例 | 22 / **22** |
| 新增依赖 | **无** (仅 numpy/pandas) |
| 新增公开参数 / 配置字段 | **无** (新类, 不改既有签名) |
| 代码净变更 | **+129/−2** (`structural_break_monitor.py`) |
| 目标版本 / 缓存代际 | **v3.4.2** / **`v2.3.0-cache`** (不变) |

---

## §1 背景

v3.4.0 (ADR-042) 将结构突变监控定位为 "opt-in 只告警":
`FactorProcessingPipelineV2.monitor_structural_breaks()` 显式调用,
`StructuralBreakMonitor.detect(path)` 只读 AR(1) 路径。设计 §9 将
"断点监控调度" 记为 O6, 说明 "当前仅显式调用, 由运行框架决定 (周/月度任务)"。

该说明暴露一个可达性问题: **库内没有任何周期性触发路径**; 若运行框架
未显式调用 `monitor_structural_breaks()`, `break_alerts` 恒为空 —— 功能
存在但不会自动生效。O6 的目标是在 **不侵入处理链路** 的前提下, 给出
可复用的节拍契约。

---

## §2 设计

### 2.1 API

```python
from backtest.structural_break_monitor import BreakMonitorScheduler

scheduler = BreakMonitorScheduler(cadence='monthly')   # 'daily' | 'weekly' | 'monthly'
alerts = scheduler.run_if_due(
    as_of, pipeline.monitor_structural_breaks, factor_data,
    method='sup_f',
)
```

| 成员 | 语义 |
|------|------|
| `due(as_of)` | 纯查询: 周期键与上次运行不同则 True; 首次调用 True |
| `mark_run(as_of)` | 手工登记一次运行 (自定义流程用) |
| `run_if_due(as_of, func, *args, **kwargs)` | 到期才执行; **回调成功后** 才推进状态; 未到期返回 None |
| `reset()` | 清空状态, 下次调用重新到期 |
| `cadence` | 只读节拍档位 (运行中不可改) |
| `runs` / `last_run_as_of` | 累计登记次数 (含手工 `mark_run`) / 上次登记 as_of |

### 2.2 周期键

| cadence | 周期键 | 示例 |
|---------|--------|------|
| `daily` | `(年, 月, 日)` | 同日不同时刻幂等 |
| `weekly` | ISO `(ISO 年, ISO 周)` | 2025-12-28 (2025-W52) → 2025-12-29 (2026-W01) 到期; 2026-01-04 仍在 W01 跳过 |
| `monthly` | `(年, 月)` | 2026-01-31 与 2026-01-01 同键 |

### 2.3 关键决策

1. **库内节拍器, 不引入外部调度**: 约 110 行纯状态机 (含 docstring), 无新依赖;
   `cron` / APScheduler 把幂等语义推给调用方, 本类直接内置;
2. **不侵入 `transform`**: 违背 v3.4.0 "监控只告警" 定位, 且使耗时不可预期;
3. **失败不推进**: 回调抛异常时状态不变, 同周期可重试, 避免一次异常吞掉整月监控;
4. **无后台线程/定时器**: 生命周期与线程安全成本远超收益, 节拍由运行框架注入;
5. **weekly 用 ISO 周**: 跨公历年边界不重复、不漏跑;
6. **状态驻内存**: 跨进程持久化由调用方落盘 `last_run_as_of` 并 `mark_run` 回填;
7. **输入显式校验**: 数值型 `as_of` 会被 pandas 解释为 1970 纳秒时间戳, 一律
   `ValueError`; tz-aware 值拒绝并提示去除时区, 避免同一时刻产生不同周期键;
8. **非线程安全是显式前提**: `due` 与 `mark_run` 非原子, 要求单线程串行;
   并发由调用方加锁, 不在库内引入锁 (无生产并发场景)。

### 2.4 边界与不做

- `as_of` 接受 naive 的 `str` / `date` / `datetime` / `Timestamp` /
  `np.datetime64`; `None` / `NaT` / 不可解析输入 / 数值型 / tz-aware → `ValueError`;
- 周期键**变化即到期**, 因此历史回放会再次运行并重复告警 (文档明示, 非缺陷);
- 同进程、同周期、串行成功后的重复调用幂等; `reset()` 或进程重启后重新到期;
- 不提供季度/年度节拍 (无需求, 可由调用方组合 `monthly` 实现);
- 不做每因子独立节拍 (节拍是运行级, 因子循环在一次运行内完成);
- 不持久化调度状态。

---

## §3 兼容性

- **兼容**: `StructuralBreakMonitor` 类 / `monitor_structural_breaks()` /
  `BreakMonitorConfig` / 管道配置字段全部不变;
- **新增**: `BreakMonitorScheduler` 类 (纯增量, 无 `__all__` 变更);
- **输入约束 (新增类自身)**: 数值型与 tz-aware `as_of` 抛 `ValueError`;
  该约束仅作用于新类, 不影响既有监控器;
- **数值**: 零变化; 缓存代际仍为 `v2.3.0-cache`;
- **迁移**: 无需迁移; 未使用调度器的调用方行为完全不变。

---

## §4 TDD 测试 (S1–S21 场景 / 22 个测试方法)

| 用例 | 断言 |
|------|------|
| S1 | daily: 同日不同时刻幂等, 次日到期 |
| S2 | weekly: ISO 周跨年 (2025-W52 → 2026-W01), 同周跨公历年不重复 |
| S3 | monthly: 同月回退日期同键, 次月到期 |
| S4 | 非法 cadence → `ValueError` (消息含三档合法值) |
| S5 | 非法 `as_of` (None/NaT/'not-a-date'/object) → `ValueError`; `date`/`datetime` 可接受 |
| S6 | `run_if_due` 每周期只执行一次, 跳过返回 None, `runs`/`last_run_as_of` 正确 |
| S7 | 回调异常不推进状态, 同周期仍到期 |
| S8 | `reset()` 重新到期并清零计数 |
| S9 | 与真实 `StructuralBreakMonitor` 集成: 月内第二次返回 None, 次月再次返回 dict |
| S10 | weekly 同周号不同 ISO 年 (2025-W01 vs 2026-W01) 必须到期 |
| S11 | daily/monthly 键包含年份: 同月日/同月跨年必须到期 |
| S12 | 回调返回 None 仍推进状态 (`runs=1`, 同周期不再到期) |
| S13 | 数值型 `as_of` (int/float/np.int64/np.float64) → `ValueError`; `np.datetime64` 可用 |
| S14 | tz-aware `as_of` (Timestamp/ISO 偏移串) → `ValueError` |
| S15 | `cadence` 只读 (赋值抛 `AttributeError`) |
| S16 | ISO 53 周年: 2027-01-03 仍属 2026-W53, 2027-01-04 到期 |
| S17 | 失败后同周期真实重试: 成功一次, `runs=1`, `last_run_as_of` 推进 |
| S18 | 闰日: 2028-02-29 同日幂等, 2028-03-01 到期 |
| S19 | `run_if_due` 入口校验失败时回调零调用、状态不变 |
| S20 | 历史回放 (周期键回退) 再次执行并计数 |
| S21 | `mark_run` 每次调用计数 (含重复登记) |

**结果**: Red = 收集错误 (`ImportError: cannot import name 'BreakMonitorScheduler'`)
→ Green = **22 passed in 0.40s**。

---

## §5 验收

| 命令 | 结果 |
|------|------|
| `pytest tests/test_break_monitor_scheduler.py -q` | **22 passed** (0.40s) |
| `pytest tests/test_break_monitor_scheduler.py tests/test_structural_break_monitor.py tests/test_fix3_version_unification.py tests/test_unified_routing.py -q` | **57 passed** (22.20s) |
| `python tests/test_backtest/verify_fix3_manual.py` | **5/5 通过** (6 处版本位置, 缓存独立) |

---

## §6 异构复审发现与处置 (2026-11-12)

三路独立只读复审 (语义 / 测试 / 文档契约), **无 P0/P1 代码缺陷**。处置如下:

| 来源 | 发现 | 级别 | 处置 |
|------|------|------|------|
| 语义 | 并发下 `due`→`mark_run` 非原子, 同周期可能重复执行 | P2 | docstring/ADR 显式声明单线程前提, 不加锁 |
| 语义 | 数值型 `as_of` 被 pandas 解释为 1970 纳秒时间戳, 静默漏跑 | P2 | `ValueError` 拒绝 + S13 |
| 语义 | tz-aware 同一时刻可产生不同周期键 | P2 | 拒绝 tz-aware + S14 |
| 语义 | `cadence` 可写, 运行中改档导致键碰撞 | P3 | 改只读属性 + S15 |
| 语义/文档 | `runs` 含 `mark_run` 计数、回放/重置后重跑、`None` 歧义 | P3 | docstring/ADR/本文档限定语义 |
| 测试 | weekly 键 ISO 年分量、daily/monthly 年份分量无断言约束 | P2 | S10 / S11 |
| 测试 | 回调返回 None 未覆盖 (变异存活) | P2 | S12 |
| 测试 | 53 周年、闰日、失败重试、入口校验、回放、`mark_run` 计数 | P3 | S16–S21 |
| 文档 | `+74 行` / `9 个方法` / `30 行` / `12 个文件` 与实测不符 | P1/P2 | 改为 `+129/−2` / 22 例 / 约 110 行 / 15 个文件 |
| 文档 | DEV_PROGRESS 路标停在 v3.4.0; PROJECT_STATUS 日期与 §4 表头过期 | P1/P2 | 已同步 |
| 文档 | "生产中不可达 / 永远为空" 绝对化 | P1 | 限定为"库内无周期触发路径; 未显式调用则恒为空" |
| 契约 | 11 处代码/测试仍写 "暂用号 ADR-042" | P3 | 清理为 ADR-042 (历史分析文档保留原文) |

## §7 后续 (不在本版范围)

- 调度状态跨进程持久化 (DuckDB / 文件) — 有真实跨进程需求时再设计;
- 每因子独立节拍 — 当前按运行级节拍, 若因子数量增大导致单次运行过慢,
  可在外层按因子分片;
- 节假日历感知 (仅交易日触发) — 当前按自然日/ISO 周/自然月, 与运行框架
  的交易日循环叠加即可, 无需内建日历。
