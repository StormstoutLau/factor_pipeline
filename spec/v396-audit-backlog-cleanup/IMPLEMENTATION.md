# 实施文档：v3.9.6 清尾包（P-016 + P-015 + P-014）

---
id: v396-audit-backlog-cleanup-IMPLEMENTATION
type: design
version: 1.2
status: verified（Step 6 复审 PASS；v1.2 Step 8 勘误 §3.1-3 保留范围，见修订）
date: 2026-11-21
depends: [v396-audit-backlog-cleanup-DESIGN, v396-audit-backlog-cleanup-RESEARCH]
upstream: null
---

> **Feature**: 审计遗留清尾——P-016（2×P2 + 3×P3）、P-015（3×P3）、P-014（文献订正）
> **创建日期**: 2026-11-21
> **状态**: v1.2 verified（Step 6 复审 PASS；16 项锚点 E1 双 pass 核验；Step 8 勘误见修订）
> **修订记录**: v1.2（2026-11-21）Step 8 一致性审查：§3.1-3「保留 L308-322」范围勘误——L308-311 为第二条恒真断言（`shifted==base` 逐元素恒等 → `a`/`b` 同输入对照无判别力），应一并删除；仅保留 L313-322 非恒真对照；删死变量 `shifted`（与 RESEARCH v1.4 §3.2-③ 注记、DESIGN v1.3 D3 对齐）。v1.1 Step 6 复审——核验 16 项锚点全过；承重假设「feather 代码列名 = stock_code」经 loaders.py L110-115 实证升级为已验证事实（§9.1-13）；无 FALSIFIED、无接口变更。v1.0 Step 5 初稿（含落盘前自查修正：`_trim_month` 裁剪索引、D4 常数用例 rt≠0）。
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.3 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.4 verified**
> **包版本**: 3.9.6（patch）

---

## 1. 实施概述

本批共 **9 个测试用例 + 2 处生产改动 + 1 处文献订正 + 6 处版本落点**，全部落在测试层与脚本层，`backtest/execution/core/` 零改动。

- P-016 五项：新增 T396-1（bootstrap 共享索引）、T396-2（脚本层 demean）、T396-5（counts 15 键），改写 T3100_3（删恒真断言）、T3100_9（补常数分位）；
- P-015 三项：T396-6（`plateau` 6 例）、T396-7（md 标题随包版本）、T396-9（真实低覆盖 E2E）；
- P-014 两行：`RESEARCH_V3.8.0_EXECUTION_CAPACITY.md` L699/L860；
- 生产改动仅两处：`--minute-root` 可选参数、`_decay_curve_md` 标题参数化。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|------|------|------|---------|
| 语言 | Python | 3.9（项目约束） | ✅ 现有 CI/测试基线 |
| 测试框架 | pytest | 既有 | ✅ |
| 数值/数据 | numpy / pandas | 既有 | ✅ |
| 列式 IO | pyarrow（feather） | 既有，`has_pyarrow` 守卫 | ✅ test_minute_panels L23-29 |
| 新增依赖 | **无** | — | ✅ INV-5 |

### 2.2 依赖版本验证

不新增依赖，无需 PyPI 查询；E2E 仅用既有 `pyarrow.feather`。

### 2.3 文件结构（仅列变更）

```
factor_pipeline/
├── __init__.py                                  # L58 版本 3.9.5→3.9.6
├── pyproject.toml                               # L7  版本 3.9.5→3.9.6
├── backtest/
│   ├── config_v2.py                             # L371 版本
│   └── reporting.py                             # L40 版本
├── scripts/
│   └── verify_capacity_impact.py                # +--minute-root；标题参数化
├── tests/
│   ├── test_execution_capacity.py               # T396-1/2/5；改 T3100_3/9
│   ├── test_execution_decay.py                  # T396-6/7
│   ├── test_minute_panels.py                    # T396-8/9 + _trim_month
│   ├── test_fix3_version_unification.py         # L34 EXPECTED_VERSION
│   └── test_backtest/verify_fix3_manual.py      # L21 版本
└── docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md  # L699/L860
```

## 3. 模块实施

### 3.1 `tests/test_execution_capacity.py`（P-016）

#### 职责

在既有 fixture 上新增 3 个用例、改写 2 个用例；不新增 fixture，不改生产代码。

#### 实施要点

1. **T396-1** 复用 `_vci()`/`_csr_arrays` 风格，但需自定义 5 事件 × 4 月样本（见 §4.3）；`monkeypatch.setattr(backtest.effect_size, ...)` 在**函数内** import 之后仍生效（impact.py L269 函数内 import）。
2. **T396-2** 用 `_event_panel()` 返回的 `(vci, P, _w, _dates, form_dates)`，以全期恒定 `w=0.25` 覆盖，仅首期产生 4 个 Δw>0 事件。
3. **T3100_3 改写**（删恒真、补幅度）：L305-311 **两条**恒真断言（`allclose(base, shifted)` 与同输入 `a`/`b` 对照——`shifted` 与 `base` 逐元素恒等）一并删除，代之以幅度断言（可捕获 demean 公式漂移，如误用 median）：

```python
    base = raw - raw.mean()
    # v3.9.6 P-016③：删除 L305-307 恒真 allclose 与 L308-311 同输入 a/b 对照，改断言 demean 幅度
    assert abs(float(base.mean())) < 1e-12
    assert float(np.max(np.abs(base - raw))) == pytest.approx(abs(float(raw.mean())))
```

保留 L313-322 的非恒真对照（`c`/`d`，与 `base` 无关）；`shifted` 变量删除（不再使用）；测试名与 T3100_3 锚点不变。
4. **T3100_9 增常数用例**（见 §4.5）：`rt` 必须**非零**，否则 `Σa·x²=0` 走退化分支返回 NaN。
5. **T396-5** 15 键字面量见 DESIGN §6.1，用 `_event_panel()` 调 `build_reversal_events` 取 `out["counts"]`。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 每个用例重复构造 `_event_panel` | 复用既有函数，单次构造 4×4 小面板（微秒级） |
| bootstrap 用默认 1000 次 | T396-1 传 `n_bootstrap=50` |

### 3.2 `tests/test_execution_decay.py`（P-015①②）

#### 职责

补 `plateau` 直接契约 6 例；补 md 标题版本断言。

#### 实施要点

1. 顶部加与 `test_execution_capacity.py` L373-379 同款的 `_vci()`（插 root + scripts 到 `sys.path`）；
2. T396-6 表驱动 `@pytest.mark.parametrize`，6 组见 DESIGN §6.2；
3. T396-7 复用 T393-9 的合成 `panels` → `assemble_decay_curve` → `_decay_curve_md` → 断言首行。

### 3.3 `tests/test_minute_panels.py`（P-015③）

#### 职责

新增 `_trim_month` helper、T396-8（参数契约）、T396-9（真实低覆盖 E2E）。

#### 实施要点

1. `@needs_pyarrow @needs_minutes @needs_daily` 三层守卫；
2. 源目录固定 `E:\Level 1 Data`，月份固定 `"2020-02"`（实测 20 文件 / 233 MB）；
3. 逐文件 `feather.read_table` → `to_pandas` → 过滤 `stock_code`（`idx % 10 not in (0,1,2)`）→ `feather.write_feather`；
4. 两次子进程：严格版先跑（门禁即退出，便宜），force 版全量一次；
5. 全部产物写 `tmp_path`（INV-7）。

### 3.4 `scripts/verify_capacity_impact.py`（D7/D8）

#### 职责

新增 opt-in 分钟根目录；md 标题改为包版本。

#### 实施要点

- `--minute-root` 插在 L693-697 之后，`default=None`；
- cfg 构造（现 L726）改为 §4.1 的 `overrides` 写法；
- `_decay_curve_md` 首行改格式串，函数内延迟导入 `factor_pipeline.__version__`。

## 4. 接口实施

### 4.1 CLI 参数与 cfg 覆盖

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

**签名一致性**: 与 DESIGN §4.1 一致 ✅（`CalibrationConfig` 为 frozen dataclass，关键字构造合法）

### 4.2 `_decay_curve_md` 标题

```python
def _decay_curve_md(payload):
    """衰减曲线 md（口径 / m / net / verdict / bootstrap / warnings 六节）。"""
    from factor_pipeline import __version__ as _pkg_version
    ...
    lines = [
        '# v%s alpha 衰减曲线（FO-1）' % _pkg_version, '',
```

**签名一致性**: 与 DESIGN §4.2 一致 ✅（桩可解析：script L29-32 已把 `ROOT=f:\Coding` 插入 `sys.path`）

### 4.3 T396-1 构造（精确）

```python
def test_T396_1_bootstrap_shared_index(monkeypatch):
    """T396-1: bootstrap 只抽 1 次，buy/sell 共用同一索引。"""
    import backtest.effect_size as es
    from backtest.execution.core.impact import cross_section_reversal

    n_boot, n_months = 50, 4
    calls = []
    plan = [np.ones((n_boot, n_months), dtype=np.int64),
            np.zeros((n_boot, n_months), dtype=np.int64)]

    def spy(n, n_bootstrap=1000, block_size=1, seed=None):
        calls.append(1)
        return plan[len(calls) - 1]

    monkeypatch.setattr(es, "stationary_bootstrap_indices", spy)

    rt = np.full(5, 0.02)
    rt1 = np.array([-0.02, -0.02, 0.03, -0.02, -0.02])
    side = np.array([1.0, 1.0, -1.0, 1.0, 1.0])
    weight = np.full(5, 0.5)
    month = np.array([0, 1, 1, 2, 3], dtype=np.int64)

    out = cross_section_reversal(rt, rt1, side, weight, month, n_bootstrap=50)
    assert len(calls) == 1
    assert out["buy"]["point"] == pytest.approx(200.0)
    assert out["buy"]["lo"] == pytest.approx(200.0)
    assert out["buy"]["hi"] == pytest.approx(200.0)
    assert out["sell"]["point"] == pytest.approx(300.0)
    assert out["sell"]["lo"] == pytest.approx(300.0)
    assert out["sell"]["hi"] == pytest.approx(300.0)
    assert out["degraded"] is False
```

### 4.4 T396-2 构造（精确）

```python
def test_T396_2_script_demean_zero_mean():
    """T396-2: 形成日截面 demean 后 Σrt≈0，且逐值等于 ret − mean(ret)。"""
    vci, P, _w, _dates, form_dates = _event_panel()
    w = pd.DataFrame(0.25, index=form_dates, columns=P["close"].columns)
    out = vci.build_reversal_events(P, w)
    raw = np.array([0.02, 0.01, 0.03, 0.00])
    expected = raw - raw.mean()
    assert out["counts"]["n_events"] == 4
    assert np.allclose(np.sort(out["rt"]), np.sort(expected))
    assert abs(float(np.sum(out["rt"]))) < 1e-12
```

### 4.5 T3100_9 常数用例（精确）

```python
    # v3.9.6 P-016④：常数输入 → 分位退化，lo == point == hi == 100.0
    const = cross_section_reversal(np.full(8, 0.02), np.full(8, -0.01),
                                   np.ones(8), np.full(8, 0.5),
                                   np.array([0, 0, 1, 1, 2, 2, 3, 3]))
    assert const["degraded"] is False
    assert const["reversal_bps"]["point"] == pytest.approx(100.0)
    assert const["reversal_bps"]["lo"] == pytest.approx(100.0)
    assert const["reversal_bps"]["hi"] == pytest.approx(100.0)
```

### 4.6 `_trim_month` helper（精确）

```python
def _trim_month(tmp_path, ym="2020-02", keep_mod=(0, 1, 2)):
    """复制一个月 feather 到 tmp，按 code 排序后裁掉约 30%。"""
    pyarrow_feather = pytest.importorskip("pyarrow.feather")
    src = Path(r"E:\Level 1 Data")
    dst = tmp_path / "minutes"
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("%s-*.feather" % ym))
    assert files, "无 %s 分钟文件" % ym
    for f in files:
        frame = pyarrow_feather.read_table(str(f)).to_pandas()
        codes = np.sort(frame["stock_code"].unique())
        drop = set(codes[(np.arange(codes.size) % 10) < 3].tolist())
        keep = [c for c in codes if c not in drop]
        pyarrow_feather.write_feather(frame[frame["stock_code"].isin(keep)],
                                     str(dst / f.name))
    assert len(list(dst.glob("*.feather"))) == len(files)
    return dst
```

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|------------|------|------|
| 3.9 | ✅ | 项目基线；无 3.10+ 语法 |
| 3.10+ | ✅ | 语法子集 |

### 5.2 依赖兼容

无新增依赖，组合不变。

### 5.3 向后兼容

- `--minute-root` 不传 → `overrides == {}` → 与 v3.9.5 构造一致（INV-4）；
- `_decay_curve_md` 签名不变，仅标题内容由常量变包版本；
- 既有 9 个 T396 之外的全部测试不受影响（生产实现零改动）。

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 异常类型 | 处理代码 | 测试 |
|---|---|---|---|
| 分钟数据目录缺失 | `pytest.skip` | `@needs_minutes`（test_minute_panels L28-33） | T396-9 |
| pyarrow 缺失 | `pytest.skip` | `@needs_pyarrow` / `importorskip` | T396-9 |
| 日频数据缺失 | `pytest.skip` | `@needs_daily` | T396-9 |
| `--minute-root` 空/不存在 | 无异常，门禁失败 | script L751-754 `return 2` | T396-9 |
| 子进程超时 | `subprocess.TimeoutExpired` | `timeout=1800` | T396-9 |
| `factor_pipeline` 导入失败 | `ImportError` 上抛 | `_decay_curve_md` 内 import | T396-7 |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 |
|---|---|---|
| INV-1 默认 SHA 不变 | 无生产路径改动 | Step 9 复跑 + `sha256sum` |
| INV-2 `panel_hash` 不变 | 同上 | Step 9 JSON 对比 |
| INV-3 core 零改动 | `git diff -- backtest/execution/core` 为空 | Step 9 命令断言 |
| INV-4 不传参零变更 | script L726 `overrides` | T396-8 + 默认工件 SHA |
| INV-5 零新增依赖 | pyproject 不改依赖段 | `git diff pyproject.toml` 仅版本行 |
| INV-6 版本 6 处一致 | 6 文件 | `pytest tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py` |
| INV-7 只写 tmp_path | T396-9 | 断言 `out/` mtime 不变 |
| INV-8 counts 15 键 | T396-5 | 集合断言 |

## 8. 测试策略

### 8.1 单元测试

| 模块 | 测试文件 | 测试数 | 目标 |
|------|---------|--------|------|
| P-016① | test_execution_capacity.py | 1（T396-1） | 红→绿 |
| P-016② | 同上 | 1（T396-2） | 红→绿 |
| P-016③ | 同上 | 1（T3100_3 改写） | 改写后仍绿且新增幅度断言 |
| P-016④ | 同上 | 1（T3100_9 扩充） | 新增常数断言 |
| P-016⑤ | 同上 | 1（T396-5） | 红→绿 |
| P-015① | test_execution_decay.py | 6（T396-6 参数化） | 红→绿 |
| P-015② | 同上 | 1（T396-7） | 红（当前标题 v3.9.3）→绿 |

### 8.2 集成测试

| 用例 | 文件 | 守卫 | 断言 |
|---|---|---|---|
| T396-8 参数契约 | test_minute_panels.py | 无 | `--help` 含 `--minute-root`；默认 cfg 值不变 |
| T396-9 真实低覆盖 E2E | 同上 | ×3 | 严格 exit 2；force exit 0 + `coverage_gate_forced:` + `universe_ratio<0.90` |

### 8.3 属性测试

不适用（本批为契约/证据补强，非算法改造）。

### 8.4 先失败（F5）预期

| 用例 | 先红形态 |
|---|---|
| T396-1 | `AttributeError`/`AssertionError: len(calls)==2`（桩未生效或重复抽样） |
| T396-2 | `AssertionError`（`build_reversal_events` 无 demean 或 mean≠0） |
| T396-5 | `AssertionError`（键集不等） |
| T396-6 | `AttributeError: module 'decay' has no attribute 'plateau'` 或断言失败 |
| T396-7 | `AssertionError`（标题仍为 v3.9.3） |
| T396-8 | `AssertionError`（help 无该参数） |
| T396-9 | `returncode == 1`（argparse 不认识 `--minute-root`） |

## 9. 幻觉抑制审查（Step 6 Review，2026-11-21，自查·单视角）

> RULE-4 声明：本文档作者与复审者为同一 agent，结论标 `自查（单视角）`；全部核查为仓内 T1 锚点 E1 读数（Step 5 起草读 + Step 6 复核读，双 pass）。外部引用 0 条，F4 义务由 RESEARCH §9.1 履约。

### 9.1 接口与锚点核查表（16 项 E1）

| # | 实施声明 | 代码锚点 | 结果 |
|---|---|---|---|
| 1 | `_event_panel()` 返回序 `(vci, P, w, dates, form_dates)` | tests L417 | ✅ |
| 2 | T396-2 硬编码 `ret_t=[0.02,0.01,0.03,0.00]` 与 fixture 一致 | tests L389-390 | ✅ |
| 3 | demean 链：mask ffill → 首形成日前 ub=False；首形成日 mean=0.015 | script L190-192 + tests L402 | ✅ |
| 4 | 恒定 w=0.25 → `dwf=wf−wf.shift(1).fillna(0)` 仅首期 4 事件 | script L198 | ✅ |
| 5 | `build_reversal_events(P, w, price_basis='adj_close_to_close_cs')` | script L174 | ✅ |
| 6 | 返回 dict 含 `rt`/`counts` 键 | script 返回结构（Step 5 实读） | ✅ |
| 7 | T396-1 数学：buy point=200 / sell=300 / lo=hi=point / n_months=4≥3 / sax2>0 | impact L261-336（Step 5 复算） | ✅ |
| 8 | monkeypatch 拦截函数内 import | impact L269 + effect_size L128 | ✅ |
| 9 | T3100_9 常数用例：rt=+2% → sax2>0 不退化；bps=100；reps 恒定 | impact L309/L317-320/L258 | ✅ |
| 10 | plateau 6 例与 L92-98 契约逐条对应 | decay L92-98 | ✅ |
| 11 | `_decay_curve_md(payload)` 签名；标题 L570 硬编码 v3.9.3（T396-7 先红） | script L565-570 | ✅ |
| 12 | `CalibrationConfig` frozen；`minute_root` 为字段；`**overrides` 构造合法 | config L18/L23 | ✅ |
| 13 | **承重假设实证**：原始 feather 代码列名 = `stock_code`（int64） | loaders L110-115（`df["stock_code"]` 直取） | ✅ 升级为已验证事实 |
| 14 | 三层守卫先例（needs_pyarrow/minutes/daily） | test_minute_panels L23-33 | ✅ |
| 15 | 版本 6 处落点均为 3.9.5 | Step 5 grep：5×py + pyproject L7 | ✅ |
| 16 | `[coverage]` 前缀 + return 2 + force 留痕分支 | script L751-759 | ✅ |

### 9.2 门禁 a-d

- (a) FALSIFIED — 本 pass 无；Step 5 落盘前自查的 2 项修正（裁剪索引、D4 rt≠0）已记入 DESIGN v1.2 修订记录 ✅
- (b) CONFLICT / STEP_GAP_OPEN — **无** ✅
- (c) 阻断性断言双源 — 16 项均为 T1 文件本体 E1 且双 pass；唯一估计（E2E 时长）非阻断已标注 ✅
- (d) 假设区 — 唯一承重假设（feather 列名）已实证（§9.1-13）；无残留 ✅

### 9.3 契约取证字段（F1-F5）

| 字段 | 状态 | 说明 |
|---|---|---|
| F1 来源日期 | ✅ | 全部锚点读取日 2026-11-21 |
| F2 来源版本 | ✅ | 仓内来源 = 文件 + 行号 |
| F3 降级链 | N/A | 本步无外部检索，全部 E1 直读 |
| F4 引用验证表 | N/A | 实施文档外部引用 0 条 <3 |
| F5 先失败记录 | N/A → Step 9 出具 | 红形态预期表已备（§8.4，7 条） |

### 9.4 复审结论

**PASS（自查·单视角）**。16 项锚点全过，无新构造缺陷、无接口变更、无不变式变更；§4 精确代码段可直接作为 Step 7-9 实施输入。先红预期（§8.4）与红后绿路径已就绪。

## 10. 实施步骤

### Step 1: 版本 6 处

- 文件：`__init__.py` L58、`pyproject.toml` L7、`config_v2.py` L371、`reporting.py` L40、两个 `EXPECTED_VERSION`
- 内容：3.9.5 → 3.9.6
- 测试：`pytest tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py`

### Step 2: 脚本两处生产改动

- 文件：`scripts/verify_capacity_impact.py`
- 内容：§4.1 + §4.2
- 测试：T396-7、T396-8

### Step 3: P-016 测试

- 文件：`tests/test_execution_capacity.py`
- 内容：T396-1/2/5 + 改 T3100_3/9
- 测试：`pytest tests/test_execution_capacity.py -k "T396 or T3100_3 or T3100_9"`

### Step 4: P-015 plateau 与标题

- 文件：`tests/test_execution_decay.py`
- 内容：T396-6/7
- 测试：`pytest tests/test_execution_decay.py -k T396`

### Step 5: P-015 E2E

- 文件：`tests/test_minute_panels.py`
- 内容：`_trim_month` + T396-8/9
- 测试：`pytest tests/test_minute_panels.py -k "T396_8 or T396_9" -x`

### Step 6: P-014 文献

- 文件：`docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md` L699/L860
- 内容：JFQA 58(3):968-1004 + DOI

### Step 7: 全量回归

- `pytest tests/ -q` → 0 failed
- 默认工件 SHA / `panel_hash` 复核

---

**Review 签字**: _________ 日期: _________
