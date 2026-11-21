# 实施文档：v3.9.7 P-017 审计遗留清尾

---
id: v397-p017-cleanup-IMPLEMENTATION
type: implementation
version: 1.2
status: verified（v1.2 = Step 6 retro 复核 §9 补齐，见流程偏差 D-397-1；v1.1 = Step 8 勘误 §3.3/§4）
date: 2026-11-21
depends: [v397-p017-cleanup-DESIGN]
upstream: v397-p017-cleanup-DESIGN
---

> **输入**: [DESIGN.md](DESIGN.md) **v1.0 verified**（Step 4 PASS）。
> **包版本**: 3.9.7。**生产改动 1 处**（D5）；`core/` 与 `shell/panels.py` 零改动。
> **执行顺序**: D1 → D2 → D3 → D6 → D8 → D7 → D5 → D4/D9 → D10（测试先行，D5 为唯一红转绿）。

## 1. 变更清单

| 序 | 编号 | 文件 | 类型 | 行数估计 | 红形态 |
|---|---|---|---|---|---|
| 1 | D1 | tests/test_execution_capacity.py | 删除 + 改写 | −6/+2 | N/A（删除型） |
| 2 | D2 | tests/test_minute_panels.py | 删除 + 改写 | −16/+3 | N/A（结构型） |
| 3 | D3 | tests/test_minute_panels.py | 新增 | +12 | 先绿（守护栏） |
| 4 | D6 | tests/test_minute_panels.py | 新增 | +16 | 先绿（守护栏） |
| 5 | D8 | tests/test_minute_panels.py | 新增 | +20 | **红**（D5 前 `CalibrationUnavailable` 上抛） |
| 6 | D7 | tests/test_execution_decay.py | 新增 | +10 | 先绿（守护栏） |
| 7 | D5 | scripts/verify_capacity_impact.py | 生产改动 | +6/−0 | — |
| 8 | D4/D9 | spec/v396-…/DESIGN.md、CHECKLIST.md | 文档勘误 | 4 行 | — |
| 9 | D10 | 6 处版本锚点 | 3.9.6 → 3.9.7 | 6 行 | — |

## 2. 前置检查（执行前）

```powershell
git status --porcelain                 # 期望：仅本次将改的文件之外为空
git rev-parse --short HEAD             # 记录基线 commit
(Get-FileHash out/capacity_impact.json -Algorithm SHA256).Hash   # 82728CE1…
```

记录基线：全量 `pytest` = **2088 passed / 15 skipped / 0 failed**。

## 3. 逐项实施

### 3.1 D1：T3100_3 删除恒真断言（tests/test_execution_capacity.py L293-320）

**改前**（L293-309）：

```python
def test_T3100_3_shift_invariance_after_demean():
    """T3100-3: demean 幅度可断言（非恒真）；未 demean 的平移对照会改变读数。"""
    ...
    base = raw - raw.mean()
    # v3.9.6 P-016③：删除恒真 allclose(base, shifted) 与同输入 a/b 对照，
    # 改断言 demean 幅度（误用 median 等公式漂移会被捕获）。
    assert abs(float(base.mean())) < 1e-12
    assert float(np.max(np.abs(base - raw))) == pytest.approx(
        abs(float(raw.mean())))
```

**改后**：

```python
def test_T3100_3_shift_invariance_after_demean():
    """T3100-3: 未 demean 的平移对照非恒真（demean 本身由 T396_2 在脚本层覆盖）。"""
    from backtest.execution.core.impact import cross_section_reversal

    rng = np.random.default_rng(7)
    n = 60
    rt = rng.normal(0.0, 0.02, n)
    raw = rng.normal(0.001, 0.02, n)
    weight = np.full(n, 0.1)
    month = np.repeat(np.arange(4), n // 4)

    # v3.9.7 P-017①：demean 幅度类断言由定义恒真（base = raw - raw.mean()），
    # 无判别力，已删除；保留下列对实现的非恒真平移对照。
    n_unbal = n - 1
    c = cross_section_reversal(rt[:n_unbal], raw[:n_unbal],
                               np.ones(n_unbal), weight[:n_unbal],
                               month[:n_unbal])
    d = cross_section_reversal(rt[:n_unbal], raw[:n_unbal] + 0.5,
                               np.ones(n_unbal), weight[:n_unbal],
                               month[:n_unbal])
    assert abs(c["reversal_bps"]["point"]
               - d["reversal_bps"]["point"]) > 1.0
```

**自检**：文件内 `grep -n "base" tests/test_execution_capacity.py` 该函数段应无命中。

### 3.2 D2：T396_9 精确键路径 + 删 `_find_key`（tests/test_minute_panels.py）

**Step 1** 删除 L721-735 整个 `_find_key` 函数（含其上方空行，保持两空行间距）。

**Step 2** L777-780 改前：

```python
    payload = json.loads(text)
    ratio = _find_key(payload, "universe_ratio")
    assert ratio, "校准工件缺 universe_ratio"
    assert min(ratio.values()) < 0.90
```

**改后**：

```python
    payload = json.loads(text)
    ratio = payload["panels"]["coverage"]["universe_ratio"]
    assert ratio, "校准工件缺 universe_ratio"
    assert min(ratio.values()) < 0.90
```

**自检**：全仓 `grep -rn "_find_key" tests/` 应无命中。

### 3.3 D3：T397_1 配置等价（tests/test_minute_panels.py，插在 T396_9 之后；v1.1 勘误：原写「T396_8 之后」与实际不符）

```python
def test_T397_1_empty_overrides_equivalence():
    """T397-1: 不传 --minute-root 时 cfg 与 **{} 完全等价（INV-4）。"""
    from backtest.execution.config import CalibrationConfig

    root = r"E:\Ashare_data"
    a = CalibrationConfig(data_root=root)
    b = CalibrationConfig(data_root=root, **{})
    assert a == b
    assert a.config_hash() == b.config_hash()
    assert a.minute_root == r"E:\Level 1 Data"
```

### 3.4 D6：T397_2 空分钟根（tests/test_minute_panels.py，紧随 T397_1）

```python
@needs_pyarrow
def test_T397_2_empty_minute_root_raises(tmp_path):
    """T397-2: 空分钟根 → build() 抛 CalibrationUnavailable（不静默返回空面板）。"""
    from backtest.execution.config import CalibrationConfig
    from backtest.execution.ports import CalibrationUnavailable
    from backtest.execution.shell.loaders import MinuteLoader
    from backtest.execution.shell.panels import DailyRef, MinutePanelBuilder

    cfg = CalibrationConfig(minute_root=str(tmp_path))
    builder = MinutePanelBuilder(
        cfg,
        loader=MinuteLoader(str(tmp_path), sigma_bars=cfg.bvc_sigma_bars),
        daily=DailyRef(days_by_month={}))
    with pytest.raises(CalibrationUnavailable, match="无可用月份"):
        builder.build()
```

### 3.5 D8：T397_4 进程内 CLI（tests/test_minute_panels.py，紧随 T397_2）

先在文件内（`_trim_month` 之前）新增脚本导入助手：

```python
def _vci():
    """导入 scripts/verify_capacity_impact.py（进程内 CLI 测试用）。"""
    for path in (str(ROOT), str(ROOT / "scripts")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import verify_capacity_impact as vci
    return vci
```

用例：

```python
@needs_pyarrow
def test_T397_4_minute_unavailable_exit2(tmp_path, monkeypatch, capsys):
    """T397-4: 空分钟根 → 一行 [minute] 提示 + 返回 2（无 traceback）。"""
    from backtest.execution.shell.panels import DailyRef

    vci = _vci()
    monkeypatch.setattr(sys, "argv", [
        "verify_capacity_impact.py", "--calibrate",
        "--minute-root", str(tmp_path)])
    monkeypatch.setattr(vci, "build_panels", lambda root: {})
    monkeypatch.setattr(vci, "daily_ref", lambda market, cfg: DailyRef())

    rc = vci.main()
    out = capsys.readouterr().out
    assert rc == 2, out[-2000:]
    assert "[minute]" in out and "无可用月份" in out
    assert "Traceback" not in out
```

**红形态确认**（D5 前执行）：`python -m pytest tests/test_minute_panels.py -k T397_4 -q`
期望 **1 failed**（`CalibrationUnavailable` 上抛，未被捕获）。

### 3.6 D7：T397_3 导入失败（tests/test_execution_decay.py，文件末尾）

```python
def test_T397_3_decay_md_import_failure(monkeypatch):
    """T397-3: 包不可导入时 _decay_curve_md 不吞异常（ImportError 上抛）。"""
    import sys

    vci = _vci_script()
    monkeypatch.setitem(sys.modules, "factor_pipeline", None)
    with pytest.raises(ImportError):
        vci._decay_curve_md({})
```

### 3.7 D5：script 捕获 `CalibrationUnavailable`（scripts/verify_capacity_impact.py）

**Step 1** 在 L719-728 的局部 import 块中追加（按字母序放在 `backtest.execution.shell.*` 之前）：

```python
        from backtest.execution.ports import CalibrationUnavailable
```

**Step 2** L748-757 改前：

```python
        else:
            market = build_panels(args.data_root)
            loader = MinuteLoader(cfg.minute_root,
                                  sigma_bars=cfg.bvc_sigma_bars)
            cache_dir = (str(SCRIPTS.parent / 'out' / 'panel_cache')
                         if args.panel_cache else None)
            builder = MinutePanelBuilder(cfg, loader=loader,
                                         daily=daily_ref(market, cfg),
                                         cache_dir=cache_dir)
            minute = builder.build()
```

**改后**：

```python
        else:
            try:
                market = build_panels(args.data_root)
                loader = MinuteLoader(cfg.minute_root,
                                      sigma_bars=cfg.bvc_sigma_bars)
                cache_dir = (str(SCRIPTS.parent / 'out' / 'panel_cache')
                             if args.panel_cache else None)
                builder = MinutePanelBuilder(cfg, loader=loader,
                                             daily=daily_ref(market, cfg),
                                             cache_dir=cache_dir)
                minute = builder.build()
            except CalibrationUnavailable as exc:
                print('[minute] %s' % exc)
                return 2
```

**边界**：try 块**不含** L758 起的 `coverage_gate` 与后续装配；不捕获其它异常。

**绿确认**：`python -m pytest tests/test_minute_panels.py -k T397_4 -q` → **1 passed**。

### 3.8 D4/D9：文档勘误

#### (a) spec/v396-audit-backlog-cleanup/DESIGN.md L298-299（v1.3 → v1.4）

**改后两行**：

```markdown
| `--minute-root` 指向空目录 | `builder.build()` 抛 `CalibrationUnavailable` → script 捕获 | `[minute] 分钟窗口内无可用月份`；exit 2 |
| `--minute-root` 不存在 | 同上（`available_months()==[]` → 同一异常） | 同上 |
```

并在文件头 version 注记 `（v1.4：v3.9.7 勘误 §7 空根机制，见 [v397 RESEARCH](../v397-p017-cleanup/RESEARCH.md) §2.4(b)）`。

#### (b) spec/v396-audit-backlog-cleanup/DESIGN.md §6.2（L273-282）

按 [v397 DESIGN §6.2](DESIGN.md) 六行表格逐行替换（以 T396_6 L293-298 为真值）。

#### (c) spec/v396-audit-backlog-cleanup/CHECKLIST.md L159

**改后**：

```markdown
| `--minute-root` 空/不存在 | 传空目录 | `CalibrationUnavailable` → 提示 → `return 2` | ☑ v3.9.7 勘误：空根在 `build()` 抛异常、**不进入门禁**（原「走同一分支」失真）；捕获见 script L748-759，测试 T397_2/T397_4 |
```

CHECKLIST version 1.3 → 1.4，注明「v3.9.7 勘误 §5 空根行」。

### 3.9 D10：版本 3.9.7（6 处）

| 文件 | 行 | 改法 |
|---|---|---|
| pyproject.toml | 7 | `version = "3.9.7"` |
| `__init__.py` | 58 | `__version__ = "3.9.7"` |
| config_v2.py | 371 | `Field(default="3.9.7", …)` |
| reporting.py | 40 | `pipeline_version: str = "3.9.7"` |
| tests/test_fix3_version_unification.py | 34 | `EXPECTED_VERSION = "3.9.7"` |
| tests/test_backtest/verify_fix3_manual.py | 21 | `EXPECTED_VERSION = "3.9.7"` |

**自检**：`grep -rn "3\.9\.6" --include=*.py --include=*.toml` 仅剩注释（script L696、tests L280/L305/L370/L533/L699），无版本常量。

## 4. 测试计划（红 → 绿）

| 阶段 | 命令 | 期望 |
|---|---|---|
| 红（D8 后、D5 前） | `pytest tests/test_minute_panels.py -k T397_4 -q` | 1 failed（CalibrationUnavailable 上抛） |
| 绿（D5 后） | 同上 | 1 passed |
| 定向（全改完） | `pytest tests/test_minute_panels.py -k "T396_8 or T397" -q` | 4 passed（T397_3 在 decay 文件，由下一行覆盖） |
| 定向 | `pytest tests/test_execution_capacity.py -k T3100_3 -q` | 1 passed |
| 定向 | `pytest tests/test_execution_decay.py -k "T396_6 or T397_3" -q` | 7 passed |
| 定向（慢，可选） | `pytest tests/test_minute_panels.py -k T396_9 -q` | 1 passed（≈85-90 s） |
| 全量 | `pytest tests/ -q` | **2092 passed / 15 skipped / 0 failed** |

## 5. 通过线

1. 全量 **2092 passed / 15 skipped / 0 failed**（基线 2088 + 4 新增）。
2. 定向用例全绿；T397_4 红转绿有日志。
3. `git diff --stat` 中 `backtest/execution/core/`、`backtest/execution/shell/panels.py` **无条目**。
4. `out/capacity_impact.json` SHA256 仍为 `82728CE1…`（跑前后各一次）。
5. `grep` 版本一致性：6 处 3.9.7，无残留常量 3.9.6。
6. `pyproject.toml` diff 仅 version 一行（零新增依赖）。

## 6. 回滚方案

| 场景 | 回滚 |
|---|---|
| D5 引入非预期行为 | `git checkout -- scripts/verify_capacity_impact.py`；T397_4 置 skip 并登记 |
| 新用例与既有用例冲突 | 保留守护栏，回退 T397_2/T397_4 |
| 文档勘误争议 | 回退 v396 DESIGN/CHECKLIST 两文件至 v1.3 |

## 7. 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| D5 缩进破坏正常路径 | 低 | 绿后跑全量 + SHA 比对 |
| T397_4 stub 不足仍读盘 | 中 | stub `build_panels`+`daily_ref`；断言 <5 s |
| `MinuteLoader` 对空目录抛非预期异常 | 低 | 先单跑 T397_2；失败则改传不存在路径 |
| `sys.modules=None` 污染 | 低 | monkeypatch 自动回滚 |
| 文档勘误后仍与实现漂移 | 低 | 勘误表逐例抄自 T396_6 |

## 8. 验收证据清单

- [x] 红阶段：T397_4 failed（`CalibrationUnavailable`，panels.py:474），T397_1/T397_2 passed
- [x] 绿阶段：定向 4 例 4 passed / 0.14 s
- [x] 全量：2092 passed / 15 skipped / 0 failed（910.12 s）
- [x] `git diff --stat`（13 文件；core/panels 零条目）
- [x] SHA256：`82728CE103D49AF2…`（与基线一致）
- [x] 版本：6 处 3.9.7，无 3.9.6 常量残留

## 9. Step 6 retro 复核记录（流程偏差 D-397-1 补救）

> **性质声明**：本批 Step 6（实施文档 Review）与 Step 9（TDD 实现）被合并执行，编码先于独立 Review。
> 本节是**事后（retro）复核**，不能替代前置 Review 的时序证据，仅补齐内容面；时序缺陷登记于 [CHECKLIST §12 D-397-1](CHECKLIST.md)。

### 9.1 复核维度（SPEC_PROCESS Step 6 三项）

| 维度 | 复核方式 | 结论 |
|---|---|---|
| 实施细节 ↔ 设计对齐 | D1-D10 逐项对照 DESIGN §3.1 变更面与本文档 §3 实际改动 | 一致 10/10 |
| 依赖版本真实性 | 本批零新增依赖；仅 stdlib + 既有 pytest / numpy / pandas / pyarrow | 成立（pyproject 仅 version 行） |
| 接口签名可实现 | D5 依赖 `ports.CalibrationUnavailable`（[L16](file:///f:/Coding/factor_pipeline/backtest/execution/ports.py#L16) 实测）、`main()` 内裸名调用 `build_panels`/`daily_ref`（[L751/L757](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L751-L757) 实测） | 可实现，T397_4 已实证 |

### 9.2 retro 复核发现

| 编号 | 发现 | 处置 |
|---|---|---|
| R-1 | §3.3 称 T397_1「插在 T396_8 之后」，实际在 T396_9 之后（L775 起） | 已 v1.1 勘误 |
| R-2 | §4 定向命令期望「5 passed」，实测 4 passed（T397_3 不在该收集范围） | 已 v1.1 勘误 |
| R-3 | §3.4/§3.5「紧随 T397_1」与实际一致 | 无需改动 |
| R-4 | §8 原为未勾选清单，且「绿日志：定向 14 例」与实际定向集合不符 | 已改为实测值 |

### 9.3 结论

**内容面 PASS**，无新增实施缺陷；**时序面缺陷**（Review 后置）单列登记，不影响代码、测试与工件。
