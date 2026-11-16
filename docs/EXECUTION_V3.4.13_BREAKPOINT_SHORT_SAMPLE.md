# EXECUTION — DEFECT-1 修复: BreakpointDetector 短样本退化 (v3.4.13)

> **版本**: v1.1 (2026-11-16; v1.0 = 修复实施, v1.1 = +§8 异构复审)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 — **小任务裁剪** (步骤 5-6-9-10;
> 调研/设计内联于本文 §1-§2, 不单出 RESEARCH/DESIGN/CHECKLIST)
> **来源**: [多因子审计 DEFECT-1](audit/2026-11-16-multifactor-multiyear-audit.md)
> **目标**: 修复 `BreakpointDetector.detect` 在有效点 T<30 时调用未定义方法导致的 `AttributeError`。

## §1 内联调研

### 1.1 缺陷事实

| # | 事实 | 证据 |
|---|------|------|
| F1 | [L293-L294](../modules/factor_health/__init__.py#L293-L294) `if T < 30: return self._no_breakpoint_result(T)` | 代码 |
| F2 | `_no_breakpoint_result` 在全模块**无定义** (grep 仅 1 处引用) | grep |
| F3 | 复现: `BreakpointDetector().detect(np.linspace(0.1,0.2,12))` → `AttributeError` | 2026-11-16 实测 |
| F4 | 唯一生产调用路径: `FactorHealthDiagnoser.diagnose` → `self.detector.detect(beta_raw)` ([L519](../modules/factor_health/__init__.py#L519)) | grep |
| F5 | `pipelines_v2.StructuralBreakMonitor` 为独立实现, 不调用 `BreakpointDetector` | grep |
| F6 | 现有测试 `TestBreakpointDetector` 两个面板 T=200, 分支未覆盖 | [test L110-L150](../tests/unit/test_layer3_factor_health.py#L110-L150) |
| F7 | 同文件 `_detect_decay` 对 T<30 已有退化先例 (返回 `has_decay=False` 默认 dict) | [L591-L607](../modules/factor_health/__init__.py#L591-L607) |

### 1.2 为什么 T<30 不应做 sup-F

- `min_segment=0.15` 下可搜索切分区间为 `[min_seg, T-min_seg]`, `min_seg = max(5, int(0.15T))`;
  T=29 时仅 19 个候选切分, 两侧样本各 5-24 点, F 统计量的渐近正态假设不成立;
- Andrews (1993) sup-F 临界值表以 `ε = min_seg/T` 参数化, 极小样本下无定义良好的渐近对应;
- 因此「无法检验 → 判无断点 + 显式 NaN 标记」是正确语义, 与 `_detect_decay` 的 T<30 处理一致。

### 1.3 影响面

| 场景 | 影响 |
|------|------|
| `diagnose` 输入 β 有效期 <30 (短样本因子 / 短回测窗 / 消融退化臂) | 修复前 `AttributeError`; 修复后正常返回标签, `has_breakpoint=False` |
| T ≥ 30 | 零影响 (代码路径不变) |
| `StructuralBreakMonitor` | 不受影响 |
| 数值/标签 | T≥30 全路径逐位不变 |

## §2 内联设计

### 2.1 退化契约 (6 键, 与正常路径同构)

| 键 | 值 | 理由 |
|----|----|------|
| `has_breakpoint` | `False` | 无法检验 → 不宣称断点 |
| `chow_max_stat` | `0.0` | 未计算; 0 表示无证据 (与 `diagnose` 默认 `get(..., 0.0)` 一致) |
| `critical` | `nan` | 未计算, 用 NaN 而非 0 以免被误读为「阈值 0」 |
| `cusum_path` | `np.full(T, nan)` | 保持长度契约 (T = 有效点数), 值标记未计算 |
| `pre_mean` / `post_mean` | `nan` | 无断点 → 无分段均值 |
| `breakpoint_idx` | **不出现** | 与正常路径「无断点」分支一致 (`diagnose` 用 `.get` → `None`) |

### 2.2 阈值

沿用既有 `T < 30` 常量, 不新增参数 — 避免扩大 API 面; 学术依据见 §1.2。

## §3 代码变更 (`modules/factor_health/__init__.py`)

在 `detect` 之后、`_sup_f_critical_value` 之前新增:

```python
    def _no_breakpoint_result(self, T: int) -> Dict:
        """有效点 <30 的退化结果: 不做 sup-F 网格搜索, 直接判无断点。

        T<30 时 `min_segment` 允许的候选切分过少, Andrews (1993) sup-F 渐近
        临界值不适用, 检验无意义; 返回与正常路径同构的 6 键结果 (cusum 全 NaN,
        不含 `breakpoint_idx`), 供 `diagnose` 与下游安全消费。

        注: v3.4.12 及之前该分支调用未定义的方法 → AttributeError (DEFECT-1),
        v3.4.13 补齐。
        """
        n = max(int(T), 0)
        return {
            'has_breakpoint': False,
            'chow_max_stat': 0.0,
            'critical': float('nan'),
            'cusum_path': np.full(n, np.nan),
            'pre_mean': float('nan'),
            'post_mean': float('nan'),
        }
```

`detect` 本体、正常路径、`diagnose` 均**零改动**。

## §4 测试计划 (E1-E5, `tests/unit/test_layer3_factor_health.py`)

| # | 测试 | 断言 |
|---|------|------|
| E1 | `test_e1_short_sample_returns_no_breakpoint` | T=10: 6 键退化 + cusum 全 NaN 长度 10 + 无 `breakpoint_idx` |
| E2 | `test_e2_boundary_just_below_threshold` | 输入 40 含 11 NaN (有效 29): 走退化路径, cusum 长 29 |
| E3 | `test_e3_threshold_30_still_normal_path` | 有效 30: 正常路径, `critical` 有限正, cusum 长 30 |
| E4 | `test_e4_diagnose_short_panel_no_raise` | `diagnose` T=20 面板: 不抛异常, `breakpoint_idx is None`, premium 有限 |
| E5 | `test_e5_all_nan_empty` | 全 NaN → T=0, cusum 空数组, 不抛异常 |

**Red → Green**: 实现前 E1/E2/E4/E5 4 failed (`AttributeError`), E3 passed (正常路径);
实现后 5/5 passed, 文件 23 passed。

## §5 版本与兼容

| 维度 | 结论 |
|------|------|
| 版本 | **3.4.13** (6 处锚点: `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py`) |
| 缓存代际 | 不变 `v2.3.0-cache` (不触及管线中间产物) |
| 公开 API | 签名/返回键不变; 仅消除异常路径 |
| `diagnose` | 短样本输入由「崩溃」变为「正常诊断 + 无断点」 |
| 依赖 | 无新增 |

## §6 步骤 6 review 记录 (幻觉消除 #2)

| # | 检查项 | 结论 |
|---|--------|------|
| A1 | F1-F7 与代码/实测一致 (逐行核对行号) | ✅ |
| A2 | 退化键集与正常路径键集同构 (除 `breakpoint_idx`) | ✅ L318-L325 vs §2.1 |
| A3 | `diagnose` 对缺失键使用 `.get(..., 默认)` | ✅ L538-L542 |
| A4 | `cusum_path` 无下游消费方 (grep 仅赋值/打印) | ✅ |
| A5 | T 计数为**有效点**而非输入长度 (与 `detect` 的 `valid` 掩码一致) | ✅ E2 覆盖 |
| A6 | 阈值 30 与 `_detect_decay` 一致, 未引入新参数 | ✅ L606 |
| A7 | 正常路径 T≥30 无任何改动 (diff 仅新增方法) | ✅ |
| A8 | 版本 6 锚点 + 手工校验 6/6 | ✅ |

**review 结论**: PASS。

## §7 回归结果

| 项 | 结果 |
|----|------|
| 定向 (layer3 23 + 版本统一 7) | 30 passed |
| 版本手工校验 | 5/5 (预期位置 6/6, 缓存独立, 顶层可导入) |
| 全量 | **1760 passed / 15 skipped / 0 failed** (1204.58s; = 基线 1755 + 5, 符合预期) |

## §8 异构复审记录 (5 视角 × 8 探针, 2026-11-16)

> 方法: 异构复审 — 计量推断 / 数据质量 / 稳健性 / 结论效度 / 可复现性 5 视角攻击式探针;
> 探针脚本为临时文件, 用后删除, 证据并入本节与 [审计 Phase 8](audit/2026-11-16-v3.4.13-breakpoint-short-sample-audit.md)。

### 8.1 探针结果 (PR1-PR8)

| # | 探针 (攻击面) | 结果 | 视角 |
|---|--------------|------|------|
| PR1 | 退化路径 vs 正常路径「无断点」分支键集同构 | 6 键程序化确认完全相同 | 可复现性 |
| PR2 | bootstrap 方法在 T<30 | 安全 | 稳健性 |
| PR3 | `cusum_path` 长度契约 (含 NaN 混合输入) | 长度 = 有效点数, 一致 | 数据质量 |
| PR4 | `diagnose` T=20 短面板 | 12 键齐全, 不抛异常; `premium_health=stable → diagnosis=pricing` (见 H3) | 结论效度 |
| PR5 | `has_breakpoint=False` 双义性 | 检验过 (critical=8.85) vs 未检验 (critical=nan) 仅凭 `has_breakpoint` 不可区分, `critical` 可区分 | 计量推断 |
| PR6 | T=30 边界候选切分数 | `min_seg=5` → 20 个; 渐近临界值适用性存疑 (见 H4) | 计量推断 |
| PR7 | `np.int64` / `float32` 输入类型 | 兼容 (`int(T)` 显式转换) | 稳健性 |
| PR8 | `inf` 输入 | 静默判无断点 + RuntimeWarning (既有语义, 审计 D4) | 数据质量 |

### 8.2 发现与处置 (H1-H6)

| # | 发现 | 严重度 | 处置 |
|---|------|--------|------|
| H1 | 退化键集与正常「无断点」路径同构 | 确认 | 无需处置 |
| H2 | bootstrap 分支 T<30 安全 | 确认 | 无需处置 |
| H3 | 短样本 `diagnose` 标签置信度高估: T<30 时断点与衰减检验均未执行, 却可给出 `pricing` 标签 | 语义风险 (中) | **文档披露, 不改代码**: 短样本 `pricing` 应读作「样本不足以检验断点/衰减, 非确认健康」; 阈值比较未执行不会虚报断点 (`has_breakpoint=False`), 与同文件 `_detect_decay` T<30 退化先例语义一致, 避免扩大修复面 |
| H4 | T=30-50 时 sup-F 渐近临界值仍偏激进 | 既有设计局限 | 记录, 不扩范围 |
| H5 | `inf` 输入静默吞 | 既有 (审计 D4 已记录) | 记录, 未改 |
| H6 | 契约 / 版本锚点 / 输入类型兼容 | 确认 | 无需处置 |

**复审结论**: PASS 维持 — 0 个新缺陷; H3 为唯一语义风险, 以文档披露处置 (不改代码)。
