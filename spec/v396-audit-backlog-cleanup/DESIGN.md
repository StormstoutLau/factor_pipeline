# 设计文档：v3.9.6 清尾包（P-016 + P-015 + P-014）

---
id: v396-audit-backlog-cleanup-DESIGN
type: design
version: 1.3
status: verified（Step 4 复审 PASS；v1.3 Step 8 勘误 D2 行表述，见修订）
date: 2026-11-21
depends: [v396-audit-backlog-cleanup-RESEARCH]
upstream: null
---

> **Feature**: 审计遗留清尾——P-016（测试有效性 2×P2 + 3×P3）、P-015（3×P3）、P-014（文献元数据订正）
> **创建日期**: 2026-11-21
> **状态**: v1.3 verified（Step 4 复审 PASS；Step 5 尾对与 Step 8 勘误见修订记录）
> **修订记录**: v1.3（2026-11-21）Step 8 一致性审查：§2.1 D2 行「事件输出不含 `r_t`」表述勘误 → 「事件返回仅含 demean 后的 `rt` 键、无原始 `ret_t`（期望值须硬编码）」（与 RESEARCH §3.2-②、IMPLEMENTATION §9.1-6 对齐）。v1.2（2026-11-21）Step 5 尾对：D4 常数用例原写 `rt=0` 会因 `Σa·x²=0` 触发退化分支返回 NaN，改为 `rt=+2%`（§2.1 D4、IMPLEMENTATION §4.5 同步）；v1.1 Step 4 复审修正 F-1（D1 用例 2→4 月）、F-2（`ret_t` 作用域）、F-3（`@needs_pyarrow`）；v1.0 Step 3 初稿。
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.4 verified**
> **包版本**: 3.9.6（patch；U-3 裁决 A，见 RESEARCH §6/§8.3）
> **批次档位**: **T1**（只动 `tests/` + 1 个脚本参数 + 文档；不改 `backtest/execution/core/` 实现）

---

## 1. 设计目标

在不改变任何默认工件与实现语义的前提下，把三批审计遗留**真正收口**：

1. P-016：让「重抽样共享索引」「脚本层截面 demean」「T3100_3 恒真断言」「T3100_9 端点」「reversal_counts 键集」五项**具备可失败的断言**；
2. P-015：补 `plateau` 的 core 直接契约测试、让衰减曲线 md 标题跟随包版本、用真实低覆盖数据跑通 `--force-coverage` 的 exit 0/2 双分支；
3. P-014：订正 Chen & Velikov 期刊元数据（RFS → JFQA）。

**明确不做**：不改 `cross_section_reversal` / `plateau` / `coverage_gate` 的实现；不调阈值；不改 `cost_by_h` / `net(h)` / 容量读数；不重跑研究结论。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| P-016①：`idx` 只在 impact.py L313-314 抽一次，三组共用；bootstrap 为函数内 import | **D1**：用 `monkeypatch.setattr(backtest.effect_size, ...)` 计数桩，断言**调用 1 次**且 buy/sell 区间都取自该次抽样 | RESEARCH §3.2-①、§9.2-1/2 |
| P-016②： demean 在脚本 L192，事件返回仅含 demean 后的 `rt` 键、无原始 `ret_t`（期望值须硬编码） | **D2**：函数级测试——全 4 码全期恒定权重（仅首期产生 Δw）构造 4 个事件，断言 `rt == ret − mean(ret)` 且 `Σrt ≈ 0`（不新增生产返回值） | RESEARCH §3.2-②、§9.2-3 |
| P-016③：T3100_3 的 `assert np.allclose(base, shifted)` 数学恒等 | **D3**：删除该恒真断言，改为「demean 幅度」断言（`max|base−raw| == |raw.mean()|`、`base.mean()≈0`），保留非恒真对照 | RESEARCH §3.2-③、§9.2-4/5 |
| P-016④：T3100_9 端点由 `_interval` 构造保证，缺常数输入 | **D4**：增常数用例 `rt=+2%, rt1=−1%, side=+1` → `bps` 三分位均 `100.0`（`lo==point==hi`）；**不可用 `rt=0`**（`Σa·x²=0` 会走退化分支返回 NaN） | RESEARCH §3.2-④、§9.2-6 |
| P-016⑤：`reversal_counts` 仅逐字段断言 | **D5**：`set(counts) == 15 键字面量` 整体断言 | RESEARCH §3.2-⑤ |
| P-015①：`plateau` 仅被 T394-4 间接覆盖 | **D6**：core 直接契约测试 6 例（空/`sd=0` 并列/`>=` 边界/边界外/排序/单点） | RESEARCH §3.3-1、§9.2-9 |
| P-015②：md 标题硬编码 `v3.9.3` | **D7**：标题改 `'# v%s alpha 衰减曲线（FO-1）' % factor_pipeline.__version__`，延迟导入单一版本源 | RESEARCH §3.3-2、§9.2-10 |
| P-015③：`--force-coverage` 只有字符串契约测试；CLI 无 `--minute-root` | **D8**：新增 opt-in `--minute-root`（默认 `None`，零行为变更）+ 真实低覆盖 E2E（exit 2 / exit 0 + 留痕） | RESEARCH §3.3-3、§6 U-1/U-2、§8.1/§8.2 |
| P-014：两处 Chen & Velikov 期刊元数据错配（L699/L860） | **D9**：改为 JFQA 58(3):968-1004 + DOI；L859 的 Kelley RFS 不动 | RESEARCH §3.4、§9.1-9 |
| U-3=A：本批为 patch | **D10**：包版本 3.9.6，落 6 处（4 码 + 2 测试断言） | RESEARCH §6/§8.3 |

### 2.2 相关 ADR

| ADR | 决策 | 对本设计的影响 |
|-----|------|--------------|
| ADR-0001（论证驱动） | 禁止无证据归因 | D3 删除恒真断言、D8 用实测体积（233 MB）写入风险表 |
| ADR-0002（职责边界） | 明确职责内/外 | 「强制放行」策略留 script；`coverage_gate` 保持纯判定，不改 |

### 2.3 职责边界

- **职责内**：测试有效性、CLI 测试接缝、报告标题版本、文献元数据；
- **职责外**：`core/` 实现（含 `plateau` 与 `cross_section_reversal`）、覆盖度阈值、成本/容量口径、`out/` 默认工件、新增依赖。

## 3. 架构设计

### 3.1 变更面

```
tests/test_execution_capacity.py ── D1~D5（P-016 五项）
tests/test_execution_decay.py ───── D6/D7（plateau 6 例 + md 标题）
tests/test_minute_panels.py ─────── D8（--minute-root 契约 + 真实低覆盖 E2E）
scripts/verify_capacity_impact.py ─ D7（标题参数化）+ D8（新增 --minute-root）
docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md ── D9（2 行）
版本 6 处 ───────────────────────── D10（3.9.6）
```

- `backtest/execution/core/decay.py`、`core/impact.py`、`shell/panels.py` **零改动**；
- 默认路径（不传 `--minute-root`、不传 `--decay-curve-json`）**零行为变更**。

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|------|------|------|------|------|
| `test_execution_capacity.py::_csr_arrays` | 复用 8 事件合成样本 | — | 5 个 ndarray | 既有 |
| `test_execution_capacity.py::test_T396_1…5` | P-016 五项断言 | `_csr_arrays` / `_event_panel` | pass/fail | `impact`、`vci` |
| `test_execution_decay.py::test_T396_6…` | `plateau` 直接契约 | 字面量 dict | pass/fail | `core.decay` |
| `test_execution_decay.py::test_T396_7` | md 标题随包版本 | `assemble_decay_curve` 合成 payload | pass/fail | `vci`、`factor_pipeline` |
| `test_minute_panels.py::test_T396_8` | `--minute-root` 契约 | `--help` 文本 + 默认 cfg | pass/fail | `subprocess` |
| `test_minute_panels.py::test_T396_9` | 真实低覆盖 E2E | 裁剪后的单月 feather | exit 2 / exit 0 + 留痕 | `subprocess` |
| `scripts::main` | `--minute-root` 覆盖入口 | CLI 值 | `CalibrationConfig` | argparse |
| `scripts::_decay_curve_md` | 标题版本化 | payload | md 文本 | `factor_pipeline.__version__` |

### 3.3 数据流

1. **D2** 测试构造 `P`（4 码 × 4 形成日，`mask` 全 True）→ `w` 全期恒定 0.25 → `build_reversal_events(P, w)` → 取 `rt`：期望 `ret_t[code] − mean(ret_t.values())`；
2. **D1** 计数桩返回**首次**全 1 月索引、**再次**全 0 月索引（n_months=4 ≥3，绕开 impact.py L309 退化分支）→ 若实现重复抽样，第 2 次调用命中 0 月使 sell 无事件 → NaN，可被断言捕获；
3. **D8** E2E：复制/重写一个月 feather（裁 30% 码）→ `--minute-root <tmp>` → 门禁 `universe_ratio≈0.7 < 0.90` → 无 force `return 2`；加 force → 追加 `coverage_gate_forced: …` 并 exit 0；
4. **D7** `_decay_curve_md` 首行取 `factor_pipeline.__version__`。

### 3.4 控制流

`pytest` →（D8）`subprocess.run([sys.executable, script, "--calibrate", "--minute-root", tmp, ...])` → `build_panels` → `MinutePanelBuilder.build` → `coverage_gate` → `return 2` 或 force 留痕 → `run_calibration` → 写 tmp JSON。

## 4. 接口定义

### 4.1 CLI 新增参数（`scripts` argparse 区 L693-697 之后）

```python
    ap.add_argument('--minute-root', default=None,
                    help='分钟数据根目录（测试/诊断用；默认沿用 CalibrationConfig）')
```

```python
        overrides = {}
        if args.minute_root:
            overrides['minute_root'] = args.minute_root
        cfg = CalibrationConfig(data_root=args.data_root, **overrides)
```

- 不传 → `overrides` 为空 → 与 v3.9.5 构造完全一致（默认 `E:\Level 1 Data`）；
- 传空串视同不传（`if args.minute_root`）。

### 4.2 标题版本化（scripts `_decay_curve_md`）

```python
def _decay_curve_md(payload):
    """衰减曲线 md（口径 / m / net / verdict / bootstrap / warnings 六节）。"""
    from factor_pipeline import __version__ as _pkg_version
    ...
    lines = [
        '# v%s alpha 衰减曲线（FO-1）' % _pkg_version, '',
```

- 脚本顶部已 `sys.path.insert(0, str(ROOT))`（ROOT = `f:\Coding`）→ `import factor_pipeline` 解析到仓根 `__init__.py` L58；
- 延迟导入：仅 `--decay-curve-json` 分支付出导入成本；
- 无 try/except 静默回退——导入失败应当显式报错（避免再次出现版本漂移）。

### 4.3 P-016① 共享索引测试（T396-1，v1.1 修正后构造）

```python
def test_T396_1_bootstrap_shared_index(monkeypatch):
    """T396-1: bootstrap 只抽 1 次，buy/sell 共用同一索引（n_months=4 绕开退化分支）。"""
    import backtest.effect_size as es
    from backtest.execution.core.impact import cross_section_reversal

    n_boot, n_months = 50, 4
    calls = []
    plan = [np.ones((n_boot, n_months), dtype=np.int64),      # 第 1 次：全 1 月
            np.zeros((n_boot, n_months), dtype=np.int64)]     # 第 2 次：全 0 月

    def spy(n, n_bootstrap=1000, block_size=1, seed=None):
        calls.append(1)
        return plan[len(calls) - 1]

    monkeypatch.setattr(es, "stationary_bootstrap_indices", spy)
    # 5 事件 / 4 月：buy 全部 rt=+2%、rt1=-2%（y=-2% → bps=+200）；
    # 仅 month1 含 1 笔 sell（rt=+2%、rt1=+3%、side=-1 → y=-3% → bps=+300）。
    # 全样本 point 与 month1 重采样值一致 → 一次抽样下 lo==hi==point。
    rt = np.full(5, 0.02)
    rt1 = np.array([-0.02, -0.02, 0.03, -0.02, -0.02])
    side = np.array([1.0, 1.0, -1.0, 1.0, 1.0])
    weight = np.full(5, 0.5)
    month = np.array([0, 1, 1, 2, 3], dtype=np.int64)

    out = cross_section_reversal(rt, rt1, side, weight, month, n_bootstrap=50)
    assert len(calls) == 1                    # 共享 ⇔ 只抽一次
    assert out["buy"]["point"] == pytest.approx(200.0)
    assert out["buy"]["lo"] == out["buy"]["hi"] == pytest.approx(200.0)
    assert out["sell"]["point"] == pytest.approx(300.0)
    assert out["sell"]["lo"] == out["sell"]["hi"] == pytest.approx(300.0)
```

构造约束（v1.1 新增）：① `n_months ≥ 3`（否则 L309 退化分支）；② 所有 buy 事件 `rt1` 相同，使全样本 point 等于重采样月值，`lo==hi==point` 才成立；③ month0（回退索引）不含 sell，破坏共享即 NaN。

### 4.4 P-016② 脚本层 demean（T396-2）

```python
def test_T396_2_script_demean_zero_mean():
    """T396-2: 形成日截面 demean 后 Σrt≈0，且逐值等于 ret − mean(ret)。"""
    vci, P, _w, _dates, form_dates = _event_panel()
    w = pd.DataFrame(0.25, index=form_dates,
                     columns=P["close"].columns)   # 全期恒定 → 仅首期 4 个事件
    out = vci.build_reversal_events(P, w)
    raw = np.array([0.02, 0.01, 0.03, 0.00])       # _event_panel.ret_t 字面量（硬编码）
    expected = raw - raw.mean()                    # = [0.005, -0.005, 0.015, -0.015]
    assert out["counts"]["n_events"] == 4 and out["counts"]["n_buy"] == 4
    assert np.allclose(np.sort(out["rt"]), np.sort(expected))
    assert abs(float(np.sum(out["rt"]))) < 1e-12
```

- 依赖 `_event_panel` 的 `ret_t` 字面量（L389-390）；不触发任何过滤（`impl_daily` 全 False）。

### 4.5 P-015③ E2E（T396-9）

```python
@needs_pyarrow
@needs_minutes
@needs_daily
def test_T396_9_force_coverage_e2e(tmp_path):
    """T396-9: 真实低覆盖 → 无 force exit 2；有 force exit 0 且工件留痕。"""
    root = _trim_month(tmp_path, "2020-02", keep_ratio=0.7)
    cmd = [sys.executable, str(SCRIPT), "--calibrate",
           "--minute-root", str(root),
           "--calibration-json", str(tmp_path / "c1.json")]
    strict = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    assert strict.returncode == 2 and "[coverage]" in strict.stdout

    forced = subprocess.run(cmd + ["--force-coverage",
                                   "--calibration-json", str(tmp_path / "c2.json")],
                            capture_output=True, text=True, timeout=1800)
    assert forced.returncode == 0, forced.stderr[-2000:]
    payload = json.loads((tmp_path / "c2.json").read_text(encoding="utf-8"))
    assert any(str(w).startswith("coverage_gate_forced:")
               for w in payload.get("evidence_warnings") or [])
    assert min(payload["minute"]["coverage"]["universe_ratio"].values()) < 0.90
```

`_trim_month` 规则：

1. 源 `E:\Level 1 Data\2020-02-*.feather`（实测 20 个文件、共 233 MB）；
2. 逐文件 `pyarrow.feather.read_table` → `to_pandas()` → 唯一 `stock_code` 排序后按 `idx % 10 not in (0,1,2)` 保留（确定性，≈70%）；
3. `feather.write_feather` 写 `tmp_path/minutes/<原名>`；
4. 断言产物文件数 == 源文件数，且 `universe_ratio` 落在 [0.6, 0.8]。

## 5. 替代方案

### 5.1 方案 A（选择）：测试补强 + opt-in CLI + 真实数据 E2E

- 优点：断言可失败、退出码为真、默认路径零变更；不引入新依赖与标记；
- 缺点：E2E 需一次性写 ~163 MB 临时数据，单次运行约 1-3 分钟；
- 选择理由：U-1/U-2 均已裁 A；仓内已有 `needs_minutes` + `subprocess` 先例（test_minute_panels L28-33/L541-551）。

### 5.2 方案 B（否决）：不加 `--minute-root`，用环境变量注入

- 优点：CLI 表面不变；
- 否决理由：隐式全局状态，需改 `CalibrationConfig`/loader 解析优先级，影响面大于一个可选参数；且 monkeypatch 不能跨子进程（RESEARCH §8.2）。

### 5.3 方案 C（否决）：E2E 降级为函数级（builder + coverage_gate）

- 优点：不需要起子进程，快；
- 否决理由：拿不到 `return 2` / `exit 0` 的真实证据，正是 P-015③ 要补的缺口。

### 5.4 方案 D（否决）：修 `plateau` 使其对 NaN 返回 `[]`

- 优点：契约更完备；
- 否决理由：本批明令 `core/decay.py` 只加测试、不改实现（RESEARCH §3.3-1）；NaN 场景并无生产调用路径。

### 5.5 方案 E（否决）：从 `pyproject.toml` 解析版本

- 优点：不导入重包；
- 否决理由：Python 3.9 无 `tomllib`，需 `tomli`（违反零新增依赖）或手写解析（易漂移）。

### 5.6 方案 F（否决）：`importlib.metadata.version("factor-pipeline")`

- 优点：标准库；
- 否决理由：依赖包已安装且元数据可解析；测试环境与脚本直跑不保证，失败模式比导入更隐蔽。

## 6. 数据结构

### 6.1 `reversal_counts` 15 键字面量（D5）

```python
_REVERSAL_COUNT_KEYS = {
    "n_events", "n_months", "n_buy", "n_sell", "n_first_period",
    "n_suspended_t", "n_suspended_t1", "n_limit_up_t", "n_limit_down_t",
    "n_limit_t1", "n_st", "n_tiny", "n_extreme", "n_missing",
    "n_limit_down_unavailable",
}
```

- 来源：`verify_capacity_impact.py` L207-213（15 键，逐字对齐）；
- 断言 `set(out["counts"]) == _REVERSAL_COUNT_KEYS`（增/删键均失败）。

### 6.2 `plateau` 契约用例矩阵（D6）

| 用例 | net | sd | 期望 | 覆盖语义 |
|---|---|---|---|---|
| 空 | `{}` | 1.0 | `[]` | 空输入 |
| sd=0 并列 | `{5:1.0, 10:1.0, 20:0.5}` | 0.0 | `[5, 10]` | `>=` 含并列 |
| 恰在边界 | `{5:10.0, 10:8.0, 20:5.0}` | 2.0 | `[5, 10]` | `v >= max−sd` 取等 |
| 边界外 | 同上 | 2.0001 | `[5]` | 严格小于被排除 |
| 排序 | `{20:5.0, 5:10.0, 10:8.0}` | 2.0 | `[5, 10]` | 输出升序 |
| 单点 | `{10:3.0}` | 9.9 | `[10]` | `h*` 恒含 |

### 6.3 md 标题（D7）

```text
# v3.9.6 alpha 衰减曲线（FO-1）
```

- 断言：`md.splitlines()[0] == '# v%s alpha 衰减曲线（FO-1）' % __version__`。

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---|---|---|
| `E:\Level 1 Data` 缺失 / `pyarrow` 缺失 | `@needs_minutes` 跳过 | pytest skippy 原因（既有） |
| `E:\Ashare_data` 缺失 | `@needs_daily` 跳过 | pytest skip 原因（既有） |
| `--minute-root` 指向空目录 | `available_months()==[]` → 无面板 → 门禁失败 | `[coverage] …`；无 force 则 exit 2 |
| `--minute-root` 不存在 | 同上（`root.is_dir()` 为 False） | 同上 |
| 子进程超时 | `subprocess.TimeoutExpired` 直接失败 | 测试输出 tail |
| `factor_pipeline` 导入失败 | 不吞异常，显式抛 | traceback（曲线分支） |
| feather 裁剪后 schema 变化 | 用 pyarrow 读表→过滤行→原 schema 写回 | 若失败测试立即红 |

## 8. 不变式（Invariants）

1. **INV-1** 默认 `out/capacity_impact.json` SHA 逐位不变（`82728CE1…`）；
2. **INV-2** `panel_hash` 逐位不变（`dfcc4e1d…`）；
3. **INV-3** `core/decay.py`、`core/impact.py`、`shell/panels.py` 生产代码零改动（只新增测试）；
4. **INV-4** 不传 `--minute-root` 时 CLI 行为与 v3.9.5 逐字节一致（`overrides == {}`）；
5. **INV-5** 零新增依赖；Python 3.9 语法；
6. **INV-6** 版本 6 处一致 = `3.9.6`（`__init__.py` L58、`pyproject.toml` L7、`config_v2.py` L371、`reporting.py` L40、两处 `EXPECTED_VERSION`）；
7. **INV-7** 新增测试不联网；E2E 只写 `tmp_path`，不触碰 `out/`；
8. **INV-8** `reversal_counts` 键集恒为 6.1 的 15 键。

## 9. 幻觉抑制审查（Step 4 Review，2026-11-21，自查·单视角）

> RULE-4 声明：本文档作者与复审者为同一 agent，本节结论标 `自查（单视角）`；全部核查为仓内 T1 锚点 E1 读数（Step 3 起草读 + Step 4 复核读，双 pass）。外部引用 0 条，无 F4 义务（RESEARCH 的 9 条外部引用已在 RESEARCH §9.1 验证）。

### 9.1 设计声明核查表（15 项 E1）

| # | 设计声明 | 代码锚点 | 结果 |
|---|---|---|---|
| 1 | D1 spy 签名兼容调用处 | impact.py L313-314 `stationary_bootstrap_indices(n_months, n_bootstrap=…, block_size=1, seed=…)`；effect_size.py L128 定义 | ✅ |
| 2 | D1 idx 形状语义：`v[idx].sum(axis=1)`，v=(n_months,)、idx=(n_boot,n_months) | impact.py L317 | ✅ |
| 3 | **F-1（缺陷已修）**：原稿 n_months=2 触发退化分支 | impact.py L309 `n_months < 3 → _degraded_reversal` | ✅ 改 4 月（§4.3） |
| 4 | D1「全样本 point = 重采样月值」构造约束 | 全 buy 同 rt1 → point=200；仅 month1 有 sell → 300 | ✅ 随 F-1 落 §4.3 |
| 5 | monkeypatch 目标运行期可解析（函数内 import） | impact.py L269 | ✅ |
| 6 | D2 `out["rt"]` 返回键存在 | verify_capacity_impact.py L289 返回 dict | ✅ |
| 7 | **F-2（缺陷已修）**：`ret_t` 为 `_event_panel` 局部变量，测试作用域不可见 | tests L389-390（函数体内部） | ✅ 硬编码（§4.4） |
| 8 | D2 期望值推导：`pct_change(cumprod)` 精确等于 ret_map；首形成日 `ub` 全 True → mean=0.015 | script L189-192 + tests L393-401 | ✅ |
| 9 | counts 15 键与 §6.1 字面量逐字一致 | script L207-213 | ✅ |
| 10 | 版本 6 处落点（INV-6） | `__init__.py` L58 / `pyproject.toml` L7 / `config_v2.py` L371 / `reporting.py` L40 / `test_fix3_version_unification.py` L34 / `test_backtest/verify_fix3_manual.py` L21 | ✅ 全为 3.9.5（待改 3.9.6） |
| 11 | D7 `import factor_pipeline` 经 ROOT=f:\Coding 可解析 | script L29-32；`factor_pipeline/__init__.py` L58 | ✅ |
| 12 | **F-3（缺陷已修）**：T396-9 feather 读写依赖 pyarrow，守卫缺项 | test_minute_panels.py L23-29（has_pyarrow/needs_pyarrow 先例） | ✅ 补 `@needs_pyarrow` |
| 13 | D8 strict 分支 `[coverage]` 前缀与 exit 2 | script L751-754（print + return 2） | ✅ |
| 14 | D8 forced 分支 `evidence_warnings` 键存在 | run_calibration 输出（tests T380-47 `out["evidence_warnings"]`） | ✅ |
| 15 | `--calibration-json` / `--force-coverage` 参数已存在 | script L681 / L693 | ✅ |

### 9.2 门禁 a-d

- (a) FALSIFIED 断言 — 无外部断言证伪；3 项**构造级**缺陷（F-1/F-2/F-3）已当场修正并记入修订记录 ✅
- (b) CONFLICT / STEP_GAP_OPEN — **无** ✅
- (c) 阻断性断言双源 — 15 项均为 T1 文件本体 E1 且双 pass 复读 ✅；唯一估计「E2E 构建时长 1-3 分钟」非阻断，已标 [估计-Step 9 实测回填] ✅
- (d) 假设区 — 无未携带假设；「`--minute-root` 是否对外 API」已由 U-3 裁决闭环 ✅

### 9.3 契约取证字段（F1-F5）

| 字段 | 状态 | 说明 |
|---|---|---|
| F1 来源日期 | ✅ | 本节全部锚点读取日 2026-11-21 |
| F2 来源版本 | ✅ | 仓内来源 = 文件 + 行号（无外部版本化来源） |
| F3 降级链 | N/A | 本步无外部检索，全部 E1 直读 |
| F4 引用验证表 | N/A | 设计文档外部引用 0 条 <3；外部证据已在 RESEARCH §9.1 履约 |
| F5 先失败记录 | N/A | Step 9 出具（TDD 先红后绿） |

### 9.4 复审结论

**PASS（自查·单视角）**。3 项构造级修正（F-1 方向性——原用例必然走退化分支、断言永假预期落空；F-2/F-3 守卫级），无接口变更、无不变式变更、无方向性方案变更。§4.3/§4.4/§4.5 已按修正后构造更新，可直接作为 Step 5-6 实施输入。

## 10. 对实施的输入

### 10.1 关键工程约束

1. 先红后绿：五条 P-016 断言必须先能失败（TDD，Step 9 出具 F5 先失败记录）；
2. 测试写入位置：`test_execution_capacity.py`（D1-D5）、`test_execution_decay.py`（D6/D7）、`test_minute_panels.py`（D8）；
3. `--minute-root` 只在 `--calibrate`/`--diagnose-window` 分支生效，其余分支不读；
4. 版本 6 处同改，`git diff` 只允许版本行；
5. E2E 断言顺序：先跑无 force（快速失败）再跑 force，避免重复全量校准；
6. 产物路径一律 `tmp_path`，禁止写 `out/`。

### 10.2 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| E2E 临时写入约 163 MB、耗时 1-3 分钟 | 只裁 1 个月；确定性抽样（`idx % 10`）；`skipif` 保证非数据环境不红；Step 9 记录实测时长回填 RESEARCH §5 |
| 两次子进程重复加载日频面板 | 先跑 exit 2 分支（门禁前即退出）；force 全量只跑一次 |
| 裁剪破坏 `stock_code` 类型 → `_keep_mask` 过滤异常 | 用原表 schema 写回；断言 `universe_ratio ∈ [0.6, 0.8]` |
| `factor_pipeline` 导入有副作用 | 延迟到 `_decay_curve_md` 内；测试覆盖该分支 |
| 版本 6 处漏改 | `pytest tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py` 双锚点 |

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**：

（无）——U-1/U-2/U-3 已于 2026-11-21 裁决为 A（RESEARCH §6），本设计无新增未决项。

**11.2 决策矩阵**：不启用。本批改动均为 Type-2（可逆）且无多方案硬选择需求（U-3 的 SemVer 争议已由用户裁决闭环）。

---

**Review 签字**: _________ 日期: _________
