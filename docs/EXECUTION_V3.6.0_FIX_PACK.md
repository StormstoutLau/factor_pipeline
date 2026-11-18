# EXECUTION v3.6.0 修复包 — 复审 R1-R4 (P2-5 / P3-5 ~ P3-7)

> **版本**: v1.0 (2026-11-18)
> **流程**: [WORKFLOW_METHODOLOGY §13.8](WORKFLOW_METHODOLOGY.md#L1201) 小任务裁剪（步骤 5-6-9-10；调研/设计内联）
> **上游证据**: [ADD 审计 P2-5 / P3-5~P3-7](audit/2026-11-18-v3.6.0-governance-base-audit.md#L162) /
> [EXECUTION §9.9 R1-R4](EXECUTION_V3.6.0_GOVERNANCE_BASE.md#L1268) /
> `out/review_v360_t46_e8_results.txt`（双验证器 2/2 确认）
> **目标版本**: **3.6.0 不 bump** —— v3.6.0 尚未提交，修复折入同批；6 处版本锚点与缓存代际均不动
> **档位**: T1（Layer-1：`backtest/` + `tests/`）；裁剪理由：四项修复均为单函数级 + 单测，
> 调研 = 独立复审 E2 证据，设计内联 §3（依 §13.8 小任务条款）
> **新增依赖**: 零

---

## §1 任务清单

| # | 来源 | 修复内容 | 测试 | 是否实施 |
|---|------|---------|------|---------|
| F1 | 复审 R1 / P2-5（**MAJOR**） | `build()` 补默认阶段统一注入「有模型默认值且参与 `record_id`」的字段，消除语义等价记录的 id 分裂 | T51 | 实施 |
| F2 | 复审 R2 / P3-5 | golden 场景判定由「G4 键存在」改为「G4 存在且 `passed=True`」 | T52 | 实施 |
| F3 | 复审 R3 / P3-6 | `known_gaps` 码名由字段名白名单改为集中映射表 | T53 | 实施 |
| F4 | 复审 R4 / P3-7 | `OLD_VERSIONS` 追加 3.5.3，覆盖上一版本残留扫描 | T54 | 实施 |
| — | P2-1 | 性能债 5 项（10k 写入 / BH / RW / White-SPA / golden 比较） | — | **不实施**（另开优化批） |
| — | P3-1 | 提交后回填 E3 行号 `@WORKTREE` → commit | — | 提交后动作 |
| — | P3-2 ~ P3-4 | 证据降级 / 默认值披露 / 词表示例 | — | 仅披露 |

---

## §2 工程事实（E1/E2 取证）

| # | 事实 | 证据 |
|---|------|------|
| F1 | `build()` 仅对 `tradable_convention` 补默认；`price_convention` 计算 id 前未注入（模型默认 `"hfq"` 不参与 `compute_record_id` 的 `fields.get`） | `backtest/governance.py` L388-419、L350、L207-210 |
| F2 | `gate_policy_version` 同模式：模型默认 `"1.0.0"`、在 `ID_FIELDS`，`build()` 未注入 | `backtest/governance.py` L338、L62 |
| F3 | golden 判定为 `"G4" in self.gate_status`，未读 `GateResultPayload.passed` | `backtest/governance.py` L437、L125-134 |
| F4 | `known_gaps` 码名按字段名白名单 `("barra", "industry")` 特判；`default_fields()` 中仅此二字段声明 `missing_semantics="known_gap"` | `backtest/data_contract.py` L812-818、L246-249 |
| F5 | `OLD_VERSIONS = ["2.0.0", "2.1.0"]`；扫描正则只匹配代码赋值/比较，不匹配描述性注释 | `tests/test_backtest/verify_fix3_manual.py` L22、L66-70 |
| F6 | 全仓无 `*.duckdb` → 无存量治理记录，改 `record_id` 零迁移 | 仓库根文件列表（2026-11-18 复核） |
| F7 | 无测试硬编码 `record_id` 字面值（grep 0） | `tests/` 全量搜索 |
| F8 | 测试已有 `_gate(name, passed)` 工厂，可直接构造 G4 失败 payload | `tests/test_backtest/test_governance.py` L35-42 |
| F9 | 全仓 `3.5.3` 代码级残留 0（7 处命中均为 docstring 版本史，正则不匹配） | 2026-11-18 复核 grep + 脚本试运行 |

---

## §3 设计决策（内联）

### DR-F1：ID 默认值注入范围

**决策**：`build()` 补默认阶段按映射统一注入：`price_convention="hfq"`、`gate_policy_version="1.0.0"`；
映射之外不注入。注入发生在 `compute_record_id` 之前。

**理由**：两字段都「有模型默认值 + 在 `ID_FIELDS`」，省略与显式传默认值必须得到同一 id。
当前无存量库（F6），改 id 零迁移成本。

**拒绝方案**：
- (a) 只修 `price_convention` → 同类缺陷在 `gate_policy_version` 残留，下一轮复审必再报；
- (b) 改 `compute_record_id` 读取模型默认 → 需实例化或重复默认表，引入循环与双源真相。

### DR-F2：golden 场景判定

**决策**：`golden = payload is not None and payload.passed`（`gate_status.get("G4")`）。
**理由**：G4 失败的记录是「留档失败结论」，不是 golden 基线；允许其携带 qfq 记录失败原因。
**拒绝方案**：(a) 键存在（现状）→ 误拒失败留档；(b) 一律拒绝 → 无法记录 qfq 的 G4 失败证据。

### DR-F3：known_gap 码名映射

**决策**：模块级 `GAP_CODE_BY_FIELD = {"barra": "barra_stale", "industry": "industry_stale"}`；
未命中回退 `"%s_missing" % name`（保持现状兜底语义）。
**理由**：词汇表约束集中在数据处，新增 known_gap 字段只需加一行映射；不改 `FieldSpec` 公共面。
**拒绝方案**：(a) `FieldSpec.gap_code` 字段 → 公共 dataclass 扩面，本批收益不足；
(b) 保留字段名白名单 → 语义约束藏在实现细节（复审 R3 原问题）。

### DR-F4：版本残留扫描范围

**决策**：`OLD_VERSIONS = ["3.5.3", "2.0.0", "2.1.0"]`；扫描正则不动。
**理由**：小版本升级同样需要残留扫描；3.5.3 代码级残留为 0（F9），追加后脚本应仍 exit 0。
**拒绝方案**：从 git tag 动态推导 → 手工校验脚本不应引入 git 依赖。

---

## §4 代码变更点

### 4.1 `backtest/governance.py`

```python
# 新增（ID_FIELDS 附近）：参与 record_id 且带模型默认值的字段
ID_DEFAULTS: Dict[str, Any] = {
    "price_convention": "hfq",
    "gate_policy_version": "1.0.0",
}

# build()：在 data["record_id"] = compute_record_id(data) 之前
for key, default in ID_DEFAULTS.items():
    data.setdefault(key, default)

# model_validator：golden 判定改为
payload = self.gate_status.get("G4")
golden = bool(payload is not None and payload.passed)
```

### 4.2 `backtest/data_contract.py`

```python
GAP_CODE_BY_FIELD: Dict[str, str] = {
    "barra": "barra_stale",
    "industry": "industry_stale",
}

# _collect()：缺失字段的 known_gap 分支
code = GAP_CODE_BY_FIELD.get(spec.name, "%s_missing" % spec.name)
```

### 4.3 `tests/test_backtest/verify_fix3_manual.py`

```python
OLD_VERSIONS = ["3.5.3", "2.0.0", "2.1.0"]
```

### 4.4 测试

| 测试 | 文件 | 断言要点 |
|------|------|---------|
| T51 | `tests/test_backtest/test_governance.py` | 省略与显式默认（`price_convention="hfq"`、`gate_policy_version="1.0.0"`）→ 同 `record_id`；字段值一致 |
| T52 | 同上 | research + G4(`passed=False`) + qfq → 允许且保留 qfq；G4(`passed=True`) + qfq → 拒绝；production + qfq → 仍拒绝 |
| T53 | `tests/test_backtest/test_data_contract.py` | `GAP_CODE_BY_FIELD` 存在且两码正确；映射外字段回退 `<name>_missing`；不 block |
| T54 | `tests/test_fix3_version_unification.py` | `"3.5.3"` 在 `OLD_VERSIONS`；`verify_fix3_manual.py` 子进程 exit 0 |

---

## §5 TDD 双读数（F5：已捕获，2026-11-18）

红命令：`python -m pytest tests/test_backtest/test_governance.py::test_t51_build_injects_id_defaults tests/test_backtest/test_governance.py::test_t52_golden_requires_g4_passed tests/test_backtest/test_data_contract.py::test_t53_gap_code_mapping_centralized "tests/test_fix3_version_unification.py::TestFix3VersionUnification::test_08_old_versions_include_previous_release" -q --tb=line`

```text
[红] 退出码: 1
     读数: 4 failed in 0.55s
     T51: AssertionError: assert '7d9045d81c3b...' == '6d0447d1fb02...'
          （record_id 分裂，R1 直接复现）
     T52: ValidationError: price_convention='qfq' 禁止用于 production/golden
          （G4 失败留档被误拒，R2 复现）
     T53: ImportError: cannot import name 'GAP_CODE_BY_FIELD'
     T54: AssertionError: '3.5.3' not found in ['2.0.0', '2.1.0']
     时间: 2026-11-18（实现前）
```

> 中间读数（如实登记）：T52 首版构造缺陷——覆盖 `gate_status` 时丢失 S1 必需的
> G0，且 G4=True 用例拒绝来自缺 G0 而非 qfq（假绿风险）；修正为补 G0 +
> `pytest.raises(match="qfq")` 后复跑 `1 failed, 33 passed in 4.45s` → 全绿。

绿命令：`python -m pytest tests/test_backtest/test_governance.py tests/test_backtest/test_data_contract.py tests/test_fix3_version_unification.py -q`

```text
[绿] 退出码: 0
     读数: 34 passed in 3.81s（governance 17 + data_contract 8 + version 9）
     实现: F1 ID_DEFAULTS 注入 / F2 golden=G4.passed / F3 GAP_CODE_BY_FIELD /
           F4 OLD_VERSIONS+3.5.3
     时间: 2026-11-18
```

配套校验（均 2026-11-18）：

```text
[绿] verify_fix3_manual.py → "Fix 3 手工校验通过: 5/5 (预期位置 6/6, 缓存独立,
     顶层可导入)"，exit 0（含 3.5.3 残留扫描，0 残留）
[绿] AST py39 扫描（governance.py + data_contract.py）→ py39_violations=[]
[绿] gate version-consistency → verdict=pass exit=0（session seq 29）
[绿] gate unit-tests → verdict=pass exit=0（session seq 30，2026-11-18T14:06:09+08:00）
     读数: 1925 passed, 7 skipped, 167 warnings, 13 subtests in 898.75s (0:14:58)
     零变更: 修复包前 1920 → 修复包后 1925（+5）；本批累计 1864 → 1925（+61）
     耗时比: 898.75s / 1516.82s = 0.59（≤1.2 预算）
     T31 golden max_abs_diff<=1e-10 零变更
```

> **+5 说明（RULE-1 如实登记）**：T54 按 §4.4 两个断言要点实现为 `test_08`
> （OLD_VERSIONS 含 3.5.3）+ `test_09`（脚本子进程 exit 0）两例；`test_09` 为
> 表征测试先绿、未入红命令（与 T46/T48b 先例一致）。开批预估 1924 按 4 例计，
> 实际 +5 = 1925。

---

## §6 兼容性、零变更与回退点

| 项 | 影响 | 处置 |
|----|------|------|
| `record_id` 取值 | 省略默认值的历史调用 id 会变化 | 无存量库（F6），零迁移；T1/T2/T3 断言为确定性/敏感性，不依赖字面值 |
| 显式 `gate_policy_version="1.0.0"` | 与省略现在同 id（行为修正） | 设计预期 |
| golden 语义 | 仅「G4 失败 + qfq」由拒绝改为允许留档 | T52 固化 |
| `known_gap` 码名 | 对外取值不变（`barra_stale` / `industry_stale`） | 仅实现方式变化 |
| 版本号 / 缓存代际 | 不变（3.6.0 / `v2.3.0-cache`） | `gate version-consistency` 应仍 pass |
| 回退点 | 逐任务独立 | F1/F2 各自回退 `governance.py` 对应 hunk；F3 回退 `data_contract.py`；F4 回退一行 |

---

## §7 验收命令

```text
1) python -m pytest tests/test_backtest/test_governance.py tests/test_backtest/test_data_contract.py tests/test_fix3_version_unification.py -q
2) python tests/test_backtest/verify_fix3_manual.py
3) python scripts/spec_runner_adapter.py gate version-consistency --session factorpipe-govbase-step9-20261117
4) python scripts/spec_runner_adapter.py gate unit-tests --session factorpipe-govbase-step9-20261117
5) AST py39 扫描（禁止 PEP 604 / 内置泛型下标）
```

预期全量：**1925 passed / 7 skipped**（1920 + 5 新例：T51/T52/T53/T54a/T54b；
开批预估 1924 按 4 例计，T54 实现为两例，见 §5 +5 说明）。

---

## §8 未决项与边界

| # | 项 | 状态 |
|---|---|------|
| U1 | P2-1 性能债 5 项 | 不在本批；另开优化批（White/SPA 需向量化） |
| U2 | P3-1 E3 行号绑定工作树 | 提交后统一回填（含本批新增行号） |
| U3 | P3-3 `price_convention` 是否改必填 | 保持默认 `hfq` + 记录落盘；改必填属契约破坏，另议 |
| U4 | 本批不新增 ADR | F1-F4 均为既有 ADR-050（确定性 id）与设计 §5.7 的实现对齐 |
