# 审查验收 Checklist：v3.9.4 审计遗留修复 + 覆盖度口径收口（批次 A）

---
id: v394-audit-coverage-fix-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-20
depends: [v394-audit-coverage-fix-IMPLEMENTATION, v394-audit-coverage-fix-DESIGN]
upstream: null
---

> **Feature**: 批次 A「口径收口包」——P-012（F-1~F-6）+ P-004（覆盖度交集口径）+ P-005（强制放行留痕）
> **创建日期**: 2026-11-20
> **状态**: **Step 10 完成 — 验收通过（accepted）**：70/70 通过；审计 PASS（0×P1 + 0×P2 + 3×P3 登记 P-015）；三项声明偏离裁决可接受
> **Spec 步骤**: Step 7-8, 10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.1 verified**
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.1 verified**
> **批次档位**: T1｜**包版本**: 3.9.4｜**代码基线**: `a0cf914`
> **硬约束**: Python 3.9 / 零新增依赖 / `core/decay.py` 零改动（`__all__` 恒 5 项）/ 默认 SHA `82728CE1…` 逐位不变 / `panel_hash` 逐位不变

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 11 条决策（D1-D11）均可追溯到 RESEARCH 锚点 | ✅ | 逐行实核：D1→§3.1、D2→§3.1（effect_size L138-139 实核）、D3/D4/D6/D7→§3.2、D5→§6.1、D8→§3.3、D9→§3.4、D10→§6.4 U-1、D11→§8.2 R-1，11/11 存在（Step 8） |
| RESEARCH 的 F-1~F-6 / P-004 / P-005 全部被 DESIGN 消费 | ✅ | F-1~F-6→D1-D7、P-004→D8/D11、P-005→D9、U-1→D10+U-6、U-5→§11、R-1→D11；U-3/U-4 已由 v393 DESIGN v1.2 落地；无静默丢弃（Step 8） |
| 无文档间矛盾 | ✅ | `_panel_hash` payload（panels.py L403-419）实核 10 键无 counts/ratio，与 D8 一致；INV-2 [单源-待二核] 与 RESEARCH §8.4 B-2 逐字一致（Step 8） |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN §10.1 白名单 9 文件在 IMPLEMENTATION §2 一一对应 | ✅ | 差异项：T394-7 落位 `test_minute_panels.py`（IMPLEMENTATION §10.4 F9 已声明）；另两处已声明差异——v393 DESIGN.md 行缺席（IMPL §3.4 文字声明）、T394-8 在 DESIGN §10.1 无独立落位行（随 T394-5 同表）（Step 8 F-F） |
| IMPLEMENTATION §3 的 12 个编辑块与 DESIGN §4.1/§4.2/§4.3/§4.4 逐块对应 | ✅ | 12 块锚点逐一实核全中（panels L10/L26-28/L50-71/L232-239/L382-401；runner L200/L316-321/L330后/L354-365/L352后；script L578-581/L610-616）；字段/键序一致（Step 8） |
| DESIGN §8 的 INV-1~INV-8 在 IMPLEMENTATION §6 有实施位置 | ✅ | 8/8 映射；INV-5 主路径限定（F8）、INV-7 单向（S6）均已声明（Step 8） |
| 无设计未覆盖的实施 | ✅ | 全部编辑可映射 D1/D5/D6/D7/D8/D9/D11；`__all__` 增项已声明（panels L26-28 实核）（Step 8） |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| IMPLEMENTATION §1 的三条主线（panels / runner / script）在本文件 §2 有验收项 | ✅ | 三主线 + §3.4 勘误 ↔ §2.1/§2.2/§2.3/§2.4（Step 8） |
| 本文件每个验收项可追溯到 IMPLEMENTATION 的 §/T 编号 | ✅ | §2→T394-1~8/§8.2/§3.4；§3→§3.1.x-§3.4；§4→§6；§5→§7 逐表抽查可追溯（Step 8） |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| `universe_ratio` | 交集口径 `\|M∩U\|/\|U\|` | 同（D8） | 同（§3.1.4） | ✅ |
| `ratio_raw` | 旧式分子披露（可 >1） | 同（D8） | 同（§3.1.2/§3.1.4） | ✅ |
| `counts` | 分钟 uniq 码数（冻结） | 同（D11） | 同（§3.1.4 不触碰 L469） | ✅ |
| `net` 区间 | m 形式 `aum·A(h_m)·(m ∓ t·m_se)` | 同（D1） | 同（§3.2.2） | ✅ |
| `plateau` | 校准工件顶层键（D5 落点） | 同（D6） | 同（§3.2.3） | ✅ |
| `coverage_gate_forced` | P-005 留痕 token | 同（D9） | 同（§3.1.5/§3.3.2） | ✅ |

## 2. 功能验收

### 2.1 覆盖度交集口径（P-004，`panels.py`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 交集比值 | `pytest tests/test_minute_panels.py -k T394_5`（`test_coverage_intersection`） | `universe_ratio==0.5` 且 `ratio_raw==1.5` | 通过 | T394-5 绿（57 passed 批次内） |
| `stock_median` 同源 | 同上 | `stock_median==6.0`（取自 `counts`，INV-4） | 通过 | T394-5 断言 6.0；39 月 stock_median 4454.0 与改前一致 |
| `as_dict` 披露 | 同上 | `as_dict()["ratio_raw"]["2023-01"]==1.5` | 通过 | T394-5 第三断言 |
| 向后兼容 | `pytest -k T394_8`（`test_panel_coverage_ratio_raw_default`） | 旧构造可用；`ratio_raw=={}` | 通过 | T394-8 绿 |

### 2.2 衰减模型遗留修复（P-012，`runner.py`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| F-1 回退区间 | `pytest -k T394_1`（`test_fallback_net_interval_m_form`） | `n_bootstrap=50` 触发回退；h∈{5,10,20} 的 lo/hi 与 m 形式独立复算一致（rel 1e-9）；`lo≤point≤hi` | 通过 | T394-1 绿（含 `decay_ci_analytic_fallback` 断言） |
| F-6 退化守卫 | `pytest -k T394_2` | `m_sensitivity=={}` 且 warning `decay_curve_unidentified` | 通过 | T394-2 绿（红阶段为 `{"1":{},"6":{}}`） |
| F-4 `DecayCurve` 接线 | `pytest -k T394_3`（monkeypatch spy） | 构造恰好 1 次；`phi_status=="fitted"` | 通过 | T394-3 绿（`len(calls)==1`） |
| F-5 `sd` | `pytest -k T394_4` | `net[h].sd` 三键有限且 ≥0 | 通过 | T394-4 绿；39 月 sd：h5=2.09e7 / h10=1.45e7 / h20=8.47e6 |
| F-5 `plateau` | 同上 | `plateau ⊆ {5,10,20}` 且含 `argmax(point)` 对应 h | 通过 | T394-4 绿；39 月 `plateau=[20]`（point 最大者） |
| 39 月实跑留痕 | `python scripts/verify_capacity_impact.py --calibrate --decay-curve-json out/v394_decay_curve.json` | 工件 `net[h].sd` / `plateau` 非缺省；退化/回退场景 `plateau==[]` | 通过 | `out/v394_decay_curve.json`：net(5/10/20) 均含 `sd`，顶层 `plateau=[20]`、`phi_status=fitted`、`evidence_warnings=[]`；退化/回退的 `[]` 由 T394-2 覆盖 |

### 2.3 强制放行留痕（P-005，`scripts/verify_capacity_impact.py`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| token 文案 | `pytest -k T394_6`（`test_force_coverage_warning_contract`） | `force_coverage_warning(["a","b"])=="coverage_gate_forced: a; b"` | 通过 | T394-6 绿（含 script 源码接线断言） |
| 端到端留痕 | 构造门禁失败输入 + `--force-coverage` 实跑 | 校准工件 §6「证据警告」节含 `coverage_gate_forced:` 行；未 force 时 `return 2` | 通过（接线级） | script L613-619 实读：未 force `return 2`；force 分支 `minute.setdefault(...).append(force_coverage_warning(messages))`；真实低覆盖数据的 E2E 未复跑（39 月门禁通过，`evidence_warnings=[]`），留 Step 10 复核 |

### 2.4 文档勘误（P-012 F-2/F-3）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| F-2 通过线勘误 | 读 `spec/v393-alpha-decay-model/IMPLEMENTATION.md` §5 | 改为 `≥2057 passed / 15 skipped / 0 failed` + 恒等式注记 + I-3 注记保留 | 通过 | L460 已改：`2065 collected + 7 模块级 skip = 2072 = 2057 + 15`，I-3 注记保留 |
| F-3 `phi_status` 枚举 | 读 `spec/v393-alpha-decay-model/DESIGN.md` | v1.2：`"fitted \| unidentified \| prior"`（Step 3 已完成，本批仅复核） | 通过 | v393 DESIGN v1.2 §6 枚举三项；`unidentified` 为运行期退化产物（DR-5），39 月实跑 `fitted` |

## 3. 接口验收

### 3.1 `PanelCoverage`（panels.py L50-71）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 与 DESIGN §6.1 一致 | 非 frozen `@dataclass`；`ratio_raw` 为**末位字段**且带 `default_factory=dict` | 通过（panels.py L52-72 实读：`ratio_raw: dict = field(default_factory=dict)` 置于 `board_counts` 之后） |
| 序列化方法名 | 使用 `as_dict`（非 `to_dict`），含 `"ratio_raw"` 键 | 通过（`as_dict` 含 `"ratio_raw"` 键；T394-8 断言空 dict） |
| 既有消费方不受影响 | `coverage_gate`（L649-671）只读 `universe_ratio`；tests L463 经 `as_dict` 取值 | 通过（`coverage_gate` 未改；T381-17 绿） |
| 边界输入 | `ratio_raw={}` 时 `as_dict()` 输出空 dict 而非抛错 | 通过（T394-8） |

### 3.2 `_universe_codes` / `_coverage`（panels.py）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| `_universe_codes` 契约 | 返回 `set[int]`；`daily is None` / `row is None` → `set()`；bool 归一与 L238-239 同款 | 通过（`daily=None` 实跑 → `set()` / count 0；`np.asarray(..., dtype=bool)` 与旧实现同款） |
| `_universe_count` 单一真相源 | 返回 `len(_universe_codes(ym))`；无其他调用方被破坏 | 通过（薄封装 `len(...)`；全量回归无新增失败） |
| 分母为 0 | `ratio[ym]=raw[ym]=None`，不抛异常 | 通过（实跑 denom=0 → `{None}`/`{None}` + 门禁「覆盖度未产出（universe_ratio 为空）」） |
| 列键不可 int 归一 | 跳过该列（try/except），分母收窄在 §7 有披露 | 通过（混入 `A00001`：codes=[1, 600000]，denom=2，ratio=0.5 / raw=1.0） |

### 3.3 `assemble_decay_curve` payload（runner.py）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| `net[h]` 键序 | `point` / `lo` / `hi` / `sd`；既有三键 point/lo/hi 取值不变（sd 为新增）（Step 8 F-E 勘误） | 通过（T394-4 断言 `sd`；git diff 仅增键，`point` 赋值未变） |
| 顶层 `plateau` | `list[int]`；`sd` 非有限时 `[]`；默认路径不进入该函数 | 通过（T394-4 主路径含 argmax；T394-2 退化 → `plateau=[]`） |
| `m` 由 `DecayCurve` 字段组装 | 与旧 `m_out` 逐位相同（同 horizons 顺序、同 float 转换） | 通过（T394-3 构造恰好 1 次；三测试文件 57 passed） |
| `phi_status` | 三态 `fitted / unidentified / prior` 与 v3.9.3 DESIGN v1.2 一致 | 通过（T394-3 `fitted`；T393-8 `prior` / `unidentified`） |

### 3.4 `force_coverage_warning`（panels.py）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 签名与 DESIGN §4.3 一致 | `(messages) -> str`；纯函数、无 I/O | 通过（panels.py L671-673 实读） |
| 文案格式 | 前缀 `coverage_gate_forced: `，多条以 `; ` 连接 | 通过（T394-6 断言 `"coverage_gate_forced: a; b"`） |
| 接线 | script force 分支经 `minute.setdefault("evidence_warnings", []).append(...)` 调用 | 通过（script L618-619 实读 + T394-6 源码文本断言） |
| 导出 | `panels.__all__` 含 `force_coverage_warning`；`test_core_all_bounded` 仍绿（仅扫 core/） | 通过（`__all__` 11 项含该符号；`test_execution_architecture.py` 3 passed） |

## 4. 不变式验收（DESIGN §8）

| 不变式 | 验证方法 | 状态 |
|--------|---------|------|
| INV-1 默认 `out/capacity_impact.json` SHA 逐位不变 | 跑前备份 → 默认实跑 → 复跑，三方 SHA == `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` | 通过（before / run1 / run2 / backup 四值全等，逐位 == 预注册串） |
| INV-2 `panel_hash` 输入键域不变 | 改码前备份 39 月 hash → 改码后逐月对比相同（第二源）；T394-7 源码文本断言 payload 无 `coverage` 键 | 通过（第二源成立：改前 `out/v393_calibration.json` 与改后 `out/v394_calibration.json` 的 `panels.panel_hash` 均为 `dfcc4e1dea9e4b4f82b73137b75ce8d59620a0d655d265780f8e52a935f85e3f` 逐位一致；T394-7 + `inspect.getsource` 断言绿） |
| INV-3 `universe_ratio ≤ 1` 且 `≤ ratio_raw` | T394-5 + 39 月读数表逐行核（同分母、交集 ≤ 分子） | 通过（39 月 `universe_ratio` ∈ [0.981548, 0.999739]，均值 0.993133，39/39 ≤1；`ratio_raw` ∈ [1.049629, 1.139838]，与改前旧口径区间逐位吻合；39/39 `ratio ≤ raw`） |
| INV-4 `stock_median` 基于原始 `counts` | T394-5 断言 6.0 | 通过（T394-5） |
| INV-5 `net.point ∈ [lo, hi]` | T394-1（回退分支）；主路径为分位 CI，依托 v3.9.3 实测读数（IMPLEMENTATION §6 F8 声明） | 通过（T394-1 断言三方不等式） |
| INV-6 退化态 `m_sensitivity=={}` / `net.*` 全 NaN / `verdict=unidentified` | T394-2 + 工件读数 | 通过（T394-2：`{}` + `decay_curve_unidentified`） |
| INV-7 `net[h].sd` 有限 ⟹ bootstrap 主路径可用（单向） | T394-4；退化/回退用例断言 `sd=NaN`、`plateau=[]` | 通过（T394-4 三 horizon `sd` 有限且 ≥0；T394-2 退化 → `[]`） |
| INV-8 `core/decay.py` 零改动、`__all__` 5 项、零新增依赖、Python 3.9 | `git diff --stat` 无该文件；`test_core_all_bounded` 绿；AST 扫描无 3.10+ 语法 | 通过（`git diff` 空；`decay.__all__` 5 项实读；三文件 `ast.parse(feature_version=(3,9))` OK；pyproject 依赖段未改） |

## 5. 错误处理验收（DESIGN §7）

| 错误场景 | 触发方式 | 预期行为 | 状态 |
|---------|---------|---------|------|
| 日频域为空 / 全部列键不可归一 | 构造 `universe=None` 或全非数字列名 | `ratio=raw=None`、`_universe_count=0`；门禁「覆盖度未产出」 | 通过（实跑：`set()` / 0 / None / 门禁 False + 该文案） |
| 个别列键不可 int 归一 | 混入 `"A00001"` 列 | 跳过该列，不抛；分母收窄在 §7 披露 | 通过（实跑：codes=[1,600000]） |
| `n_bootstrap<100` | T394-1（50） | 回退分支 + `decay_ci_analytic_fallback`，不崩 | 通过（T394-1 断言该 warning） |
| 回退分支 `m_se` 非有限 | 构造 `A(h_m)` 极小/NaN | `lo/hi=NaN`（不产出伪区间） | 通过（`m_se` 非有限 → NaN 传播，同 `m_out` lo/hi 处理；T394-2 退化全 NaN） |
| 退化态 | T394-2（负累计） | `net.*`/`sd`/`plateau`/`m_sensitivity` 全空或 NaN + `decay_curve_unidentified` | 通过（T394-2） |
| gate 失败且未 force | 门禁失败输入 | `return 2` + messages 打印，不写留痕 | 通过（script L613-615 实读：`if not args.force_coverage: return 2`） |
| gate 失败且 force | 同上 + `--force-coverage` | 追加 `coverage_gate_forced: …` 至工件证据警告节 | 通过（script L616-619 实读 + T394-6 接线断言；E2E 需真实低覆盖数据，Step 10 复核） |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| `_universe_codes` 开销 | 39 次/跑，单次为布尔掩码 + 列名遍历，与旧 `_universe_count` 同量级 | 通过（合成 5000 列 × 31 行：39 次调用 0.0316 s，均值 0.8 ms；39 月实跑覆盖度装配未成为瓶颈） | 通过 |
| 无额外 bootstrap | `net_sd` 复用 `a_boot`/`m_boot`，不新增重采样轮次 | 通过（diff 复核：无新增 `_boot` 调用；39 月 `boot.reps=1000`、`sensitivity=[1,6]` 与 v3.9.3 一致） | 通过 |

## 7. 兼容性验收

| 环境 | 目标 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.9 语法 | 通过 | AST 扫描 3 文件（`panels.py` / `runner.py` / `verify_capacity_impact.py`）：无 `match` / PEP 604 / `slots=` |
| 依赖 | 零新增 | 通过 | `pyproject.toml` 依赖段未改；仅 numpy / pandas / 标准库 |
| 版本 | 3.9.4 | 通过 | `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` 四处 + 两处版本一致性测试断言；版本测试绿 |
| OS | Windows / PowerShell 5 | 通过 | §7.2 门禁命令实测通过 |

### 7.2 门禁命令与证据登记

```powershell
python -m pytest tests/test_execution_decay.py tests/test_minute_panels.py tests/test_execution_capacity.py -q
python -m pytest tests/test_execution_architecture.py -q
python -m pytest -q
python scripts/verify_capacity_impact.py
(Get-FileHash out/capacity_impact.json -Algorithm SHA256).Hash
python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v393_calibration.json --decay-curve-json out/v393_decay_curve.json
```

| 门禁 | 通过线 | 实测 | 状态 |
|------|--------|------|------|
| 新增用例 | T394-1~T394-8 先红后绿 | 先红 **7 failed + 1 passed**（T394-7 为回归护栏、非红）；后绿 **8 passed** | 通过 |
| 架构测试 | `test_core_all_bounded` 绿（`__all__` 5 项） | `tests/test_execution_architecture.py` 3 passed | 通过 |
| 全量 | ≥ **2065** passed / 15 skipped / **0 failed**（2057 + 8） | **2065 passed / 15 skipped / 0 failed**（850.84s，172 warnings） | 通过 |
| 默认 SHA | 三方一致 `82728CE1…` | before / run1 / run2 全等 | 通过 |
| `panel_hash` | 39 月逐月逐位一致 | 改前/改后均 `dfcc4e1d…`（单值聚合哈希） | 通过 |
| 39 月校准 | `universe_ratio` 全部 ≤1；门禁通过或 force 留痕 | 39/39 ∈ [0.9815, 0.9997]；门禁通过、`evidence_warnings=[]` | 通过 |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

| 维度 | 得分 | 说明 |
|------|------|------|
| 可测试约束 | N/A | 本批按 SPEC_PROCESS 10 步执行，以 REVIEW/AUDIT 五视角矩阵替代 ADD 五维量表（同 v3.9.2/v3.9.3，`docs/SPEC_COMPLIANCE.md` D-004） |
| 模块映射 | N/A | 同上 |
| 接口契约 | N/A | 同上 |
| 修正项 | N/A | 同上 |
| 跨模块契约 | N/A | 同上 |

> **Step 10 审计执行（D-004 替代口径）**：五维量表以审计五视角矩阵替代——门禁复验 G1-G7 + 覆盖度探针 B1-B3 + 四阶段映射（完整性/忠实性/必要性/语义）+ Iron Law 四类；执行者为独立子代理（Agent 6192319f，只读纪律，不修改代码），完整读数见 §8.2-§8.4。

### 8.2 ADD 审计发现（Step 10 回填）

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P1 | 无 | — | — |
| P2 | 无 | — | — |
| P3-1 | `decay.plateau()` 无直接契约单测（T394-4 间接且半同义反复） | grep tests/ 仅 4 处均属 T394-4 | 后续批补 core 单测（max−sd 边界）→ 登记 P-015 |
| P3-2 | script md 标题硬编码「v3.9.3」，v3.9.4 生成工件标题滞留旧版本号 | `out/v394_decay_curve.md` L1；基线 `a0cf914` 已存在，非本批引入 | 后续参数化版本号 → 登记 P-015 |
| P3-3 | `--force-coverage` 真实低覆盖 E2E 未跑（审计补齐三端静态闭环：script append → `attach_panel_meta` 合并 → report 渲染） | CHECKLIST §2.3「接线级」 | 登记后续观测项，不阻断 → 合并 P-015 |

### 8.3 Iron Law 检查（Step 10 回填）

| 检查项 | 状态 |
|--------|------|
| 断言恒真式（T394-* 均依赖独立复算/闭式真值） | 通过（T394-1 独立闭式 t_crit + 原始 rows 复算 m_se；T394-2/3/8 闭式真值；T394-4 的 h_star∈plateau 半同义反复已记 P3-1） |
| 单文件检查盲区（panels ↔ runner ↔ script 三端字段一致性） | 通过（留痕通道静态闭环：script L617-618 → `attach_panel_meta` L301-306 → report.py L137-140；`ratio_raw` 经 `as_dict`→工件实证） |
| 设计文档独有约束无测试（D1-D11 + INV-1~8 均有对应项） | 通过（D10 阈值不放宽以零改动 diff 佐证；plateau 契约缺直接单测记 P3-1） |
| 修正阻断性项无测试（F-1 由 T394-1 守护；F-6 由 T394-2） | 通过（另 F-4↔T394-3、F-5↔T394-4） |

### 8.4 审计结论（Step 10 回填）

| 项 | 内容 | 状态 |
|----|------|------|
| 结论与整改去向（PASS / PASS_WITH_FIXES / FAIL + P 级计数 + 登记去向） | **PASS**（2026-11-21，独立子代理 6192319f，异构上下文）：C1-C8 八项主张全部独立复核成立；门禁 G1-G7 全过（G2 定向 69 passed；G4 `net(20)` 复算 diff=0.0；B1 39 月 `ratio_raw` ↔ 旧值逐位吻合）；0×P1 + 0×P2 + 3×P3 → 登记 [P-015](../../docs/PROGRESS.md)；三项声明偏离（T394-7 落位 / T381-17 不更新断言 / force-coverage 接线级）均裁决可接受 | 通过 |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | ✅（v1.1 verified） | 通过（Step 8 复核 15/15；§3.3 根因链与 39 月读数一致：改前 1.0496–1.1398 全部 >1） |
| DESIGN.md | ✅（v1.1 verified） | 通过（D1-D11 与 12 编辑块逐项对应；F-B 勘误已落 §9.2 + §5.5） |
| IMPLEMENTATION.md | ✅（v1.1 verified） | 通过（本次按 §3 代码块实施；F-C/F-D 声明已落盘） |
| CHECKLIST.md（本文件） | ✅ | 通过（§1-§9 已回填；§10-§11 待 Step 10） |
| ADR（如有） | N/A（无新架构决策，沿用 ADR-0001/0002） | — |
| 开发日志 | ✅（`docs/dev-log/DEV-LOG-2026-11-20.md` 追加「v3.9.4 批次 A — Step 9 实施」节） | 通过 |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 15 | 15 | 0 | 0 |
| 功能 | 14 | 14 | 0 | 0 |
| 接口 | 16 | 16 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 7 | 7 | 0 | 0 |
| 性能 | 2 | 2 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 70 | 70 | 0 | 0 |

> **统计口径（RULE-2）**：上表来自本文件逐项标记（§1-§8），非事后汇总推算；逐行 `总数 = 通过 + 失败 + 待办`，总计 = 8 类行按列求和。Step 8 复核后文档一致性 15 项全部通过（10 PASS + 5 PASS_WITH_NOTE，无 FAIL）；Step 9 实施后 §2-§7 共 51 项全部回填为通过（功能 14 / 接口 16 / 不变式 8 / 错误处理 7 / 性能 2 / 兼容性 4），仅 ADD 审计 4 槽留 Step 10；Step 10 审计 PASS（0×P1 + 0×P2 + 3×P3 登记 P-015）后 4 槽全部通过，总计 70/70/0/0。
> **分项构成**：文档一致性 15 = §1.1（3）+ §1.2（4）+ §1.3（2）+ §1.4（6）；功能 14 = §2.1（4）+ §2.2（6）+ §2.3（2）+ §2.4（2）；接口 16 = §3.1（4）+ §3.2（4）+ §3.3（4）+ §3.4（4）（Step 8 F-A 勘误：原误记 §3.4 为 3 行，实为 4 行）；ADD 审计 4 = 槽计数（§8.1/§8.2/§8.3/§8.4 各按整表计 1，与 v3.9.3 口径一致；表内行数不计）。
> **§7.2 门禁表 6 行不计入统计**：其为跨类别的汇总结论（新增用例 / 架构 / 全量 / SHA / `panel_hash` / 39 月校准），对应项已分别落在 §2.2、§4 INV-1/INV-2、§7 兼容性中，按 v3.9.3 同口径不重复计数。

### 10.2 验收决定

- [x] **验收通过**：70/70 通过（P1×0 / P2×0；审计 3×P3 非阻断，登记 P-015）
- [ ] **有条件通过**：<条件>
- [ ] **验收失败**：<原因>

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | Trae（Step 9 TDD 实施 + 证据回填） | 2026-11-21 |
| 审查者 | 独立子代理 6192319f（Step 10 ADD 审计，PASS） | 2026-11-21 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 跨文档一致性复核（§1 十五项） | — | 本批 | done（独立子代理 10 PASS + 5 PASS_WITH_NOTE + 0 FAIL；F-A/F-E 落本文件、F-B 落 DESIGN、F-C/F-D 落 IMPLEMENTATION） |
| Step 9 TDD 实施 + 证据回填（§2-§7 全部 ☐ → 证据） | — | 本批 | done（12 编辑块 + 8 例先红后绿；§2-§7 共 51 项回填；全量 2065 passed / 15 skipped / 0 failed） |
| Step 9 遗留观测：U-5 日频域列键抽样（≥3 月）、U-6 阈值定标（若门禁失败）、INV-2 `panel_hash` 二核 | — | Step 9 | done（U-5：39/39 月均产出有效 `universe_ratio` 且 `ratio_raw` 与改前逐位吻合，键归一无失效月；混入 `A00001` 实测被跳过；U-6：39 月门禁通过，无需定标；INV-2：`dfcc4e1d…` 改前/改后逐位一致） |
| Step 10 独立子代理 AUDIT + §8/§10 回填 | — | 本批 | done（PASS：0×P1 + 0×P2 + 3×P3；G1-G7 + B1-B3 + 四阶段映射 + Iron Law 四类；三项声明偏离裁决可接受） |
| 登记审计遗留 3×P3 → P-015（plateau 契约单测 / md 版本参数化 / force-coverage E2E） | — | 后续批 | pending（[PROGRESS.md](../../docs/PROGRESS.md) P-015） |
| 更新 PROGRESS.md（P-012 / P-004 / P-005 → done）/ 记录开发日志 | — | Step 9-10 | done（三行 done；dev-log 已追加 Step 9/10 节） |

> **E-TODO 映射**：本批无新增外部待办；U-5/U-6 已随 Step 9 关闭；P-012 / P-004 / P-005 已 done（Step 10）；审计遗留 3×P3 登记 P-015（pending P3）。
