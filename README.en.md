[English](README.en.md) | [中文](README.md)

![Factor Pipeline](docs/badges/factor_pipeline_cli.svg)

# Factor Processing Pipeline

## Unified Factor Processing Pipeline

**Factor Processing Pipeline** is a unified factor processing orchestration system for quantitative investment. The system has evolved from v1.0's "fixed pipeline" to v3.1.0's "audit-driven code quality remediation (31 fixes + 22 non-trivial tests)", and is advancing v3.0.0's **fingerprint dimension expansion and migration detection enhancement** (ADR-024 fingerprint 21-dim + ADR-002a KS BH-FDR). Core capabilities include **factor fingerprint diagnostic layer (21-dim, v3.0.0 T1)**, **semantic-statistical fusion classification**, **three differentiated processing pipelines**, **optional GARCH whitening**, **continuous migration monitoring**, **backtest engine integration**, **L2 disk cache layer**, **multi-factor cross-sectional orthogonalization (5 algorithms)**, and **dual-track drift fusion judgment**.

> **GitHub**: https://github.com/StormstoutLau/factor_pipeline
> **Author**: Scott Peng Liu

---

## Why I Built This Pipeline

This pipeline is not "yet another factor library." It is a **factor lie detector**.

It stems from a simple observation: the quantitative industry is awash with "confident performances"—polished backtest curves, elaborate model jargon, seemingly rigorous statistical tests—yet few address the most fundamental question: **Is this factor real? Under what conditions will this model fail? To what extent should I trust it?**

Most factor processing frameworks assume "the factor is valid; let's process it." This pipeline inverts the premise: **diagnose first, then process, then monitor continuously**. The 21-dimensional factor fingerprint is not decoration; it's a health check for every factor. The BH-FDR correction in KS migration detection is not showing off; it's an honest treatment of multiple-comparison false-positive risk. The three differentiated pipelines are not feature bloat; they acknowledge that "static, dynamic, and mixed factors require different processing logic."

In other words, this is not just code—it is an **epistemological stance**: distrust factors, distrust models, distrust your own judgment, then use statistical tools to precisely measure "to what extent can you believe."

> **Further Reading** (author's blog):
> - English: [Potemkin Village Notes](https://github.com/StormstoutLau/StormstoutLau.github.io/blob/main/posts/10-potemkin-village-notes.md)
> - 中文: [草台班子观察笔记](https://github.com/StormstoutLau/StormstoutLau.github.io/blob/main/posts/10-%E8%8D%89%E5%8F%B0%E7%8F%AD%E5%AD%90%E8%A7%82%E5%AF%9F%E7%AC%94%E8%AE%B0.md)

---

> **Note**: This English version is auto-translated. The Chinese [README.md](README.md) is the authoritative source.

---

## Version Update Summary

### v3.2.0 Academic-Principled Pipeline Refactoring (2026.07, Implemented)

> **Status**: Implemented, 9-step TDD execution plan all complete (168/168 regression)
> **Docs**: [docs/analysis/academic_literature_decision_criteria.md](docs/analysis/academic_literature_decision_criteria.md) + [docs/analysis/principle_vs_hacking_audit_v2.md](docs/analysis/principle_vs_hacking_audit_v2.md)
> **Baseline**: 168/168 tests (v3.2.0), principle ratio 68%→88% (+20%)

Systematic audit of 5 core processing modules found ~32% reliance on hardcoded heuristic thresholds (data hacking). A strict statistical decision framework based on 15 academic papers (Box-Cox 1964 / Shapiro-Wilk 1965 / Bali-Engle-Murray 2016 / Lo-MacKinlay 1988 etc.) was defined and implemented via TDD:

**Core changes**:
- **Winsorizer**: `method='auto'` → `method='percentile'` (1%/99%) — Bali et al. 2016
- **Transformer**: Heuristic `is_normal` → Shapiro-Wilk formal normality test — Shapiro & Wilk 1965
- **Imputer**: `strategy='auto'` → `strategy='ffill_ts'` (per-stock ffill → cross-median) — Little & Rubin 2002
- **Routing**: SOFT routing (weighted blend) → Hard routing + StatisticalClassifier (VR + AR(1)) — Lo & MacKinlay 1988
- **Neutralization**: Anderson-Rubin posterior R² monitoring (optional, P2) — Anderson & Rubin 1949

### v3.1.0 Audit-Driven Code Quality Remediation (2026.07, Implemented)

> **Status**: Implemented, audit P0×8 + P1×8 + P2+×15 all fixed, subset regression 754 passed + 1 skipped (zero regression)
> **Docs**: [docs/audit/2026-07-08-research-notes-v3.1.0-code-quality-audit.md](docs/audit/2026-07-08-research-notes-v3.1.0-code-quality-audit.md)
> **Baseline**: 974 passed + 6 skipped (v3.0.0 T1) → audit subset 754 passed + 1 skipped (E1-E10 + V3.1.0 E1-E6 scope)

**audit-driven-development 4-phase workflow**: Spec Inventory → Multi-Dimensional Audit (P0/P1/P2 severity) → Fix Priority Matrix → Fix Baseline + Tracking.

**Fix scope** (31 items):
- P0 blocking × 8 + P1 high-priority × 8
- P2+ tautology rewrites × 5 (Romano-Wolf / critical_alert / IVX bias / SCAD-MCP)
- P2+ design constraint tests × 10 (Config fields / config effectiveness / method_formal_name / selector logic)
- P2+ cross-file end-to-end × 2 (orchestrator + pipeline)
- P2+ E5 test strengthening × 5 (known relation / β range / zero weight / BH monotonicity / significant interaction)
- P2+ spec alignment × 11 (E1/E2/E4/E5/E9, 16 alignment markers)

**Key design decisions**:
1. r_max is computed value `min(1, multiplier × R̃)`, not configured multiplier
2. check_endogeneity signature: returns is 5th positional argument, must use keyword args
3. SCAD threshold `|x|≤λ`, MCP threshold `|x|≤λ/γ` (γ=3), need sufficiently large λ for sparsity
4. Selector persistence: single-column AR(1) ρ=0.95 has cross-sectional mean ρ only 0.70, need n=200 + ρ=0.98
5. BH-FDR monotonicity: `p_adj = p × K / rank ≥ p` (K/rank ≥ 1)

**Test regression**: subset 754 passed + 1 skipped (zero regression, 653s)
**commit**: 6192edb (7 files, +820/-87)

### v3.0.0 T1 Fingerprint Dimension Expansion to 21-dim (2026.07, Implemented)

> **Status**: Implemented, 974 passed + 6 skipped + 11 subtests passed (zero regression, 40 new tests vs v3.0.0 T4's 934)
> **Docs**: [docs/EXECUTION_V3.0.0_T1.md](docs/EXECUTION_V3.0.0_T1.md) | [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md)
> **Baseline**: 934 passed + 6 skipped (v3.0.0 T4) → 974 passed + 6 skipped (v3.0.0 T1, with 11 subtests)
> **Scope**: T1 (P1) of v3.0.0 long-term 4 tasks (T1-T4) completed

**3-Stage Execution (E1-E3)**:

| Stage | Task | Tests | Key Changes |
|-------|------|-------|-------------|
| **E1** | Fingerprint core expansion (Red→Green→Review) | 32 | `FactorFingerprint` NamedTuple 13→21-dim (8 new fields default NaN), `FingerprintConfig` 8→14 fields, 8 new computation methods (tail_dependence/gpd_shape POT-MLE/hill_estimator/regime_*/tail_regime_score), ADR-014 tech debt cleanup (statsmodels top-level import) |
| **E2** | Routing layer integration + test updates | 8 | `PipelineV2Config` adds `enable_multi_dim_routing` (default False), `_get_multi_dim_pipeline_weights` integrates into transform + Step 4 T1 corrections (tail_severity/regime_instability), `_make_fp` refactored to **kwargs pattern |
| **E3** | Doc sync + full regression | 0 | ADR-024 written to DECISIONS.md, CHANGELOG/CODE_WIKI/README sync, verify_v3_0_0_t1_manual.py 8/8 manual verification, full regression 974 passed |

**1 New ADR**:
- **ADR-024**: Fingerprint dimension expansion to 21-dim (extends ADR-019 internalized module's fingerprint definition)

**8 Key Design Decisions**:
1. Tail dependence and regime switching default off (`enable_tail_dependence=False` / `enable_regime_switching=False`), explicit opt-in
2. POT-MLE replaces Pickands estimator (`scipy.stats.genpareto.fit`), more robust for light-tailed distributions
3. regime_ic_diff scheme C (first-order diff mean difference), preserves `extract_fingerprint` signature
4. Routing integration with `enable_multi_dim_routing` toggle (default False, backward compatible)
5. No extension to `AdaptiveFactorClassifier.classify` (still uses ar1 only), new dims only affect routing correction layer
6. `_derive_tail_regime_score` M2 two-component weighting (tail_severity + regime_instability)
7. statsmodels top-level import (ADR-014 tech debt cleanup)
8. `_make_fp` test helper refactored to `**kwargs` pattern (21-dim field coverage, existing 12 tests backward compatible)

**Academic Basis**:
- Nelsen, R. B. (2006). *An Introduction to Copulas* (2nd ed.). Springer.
- Pickands, J. (1975). Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119-131.
- Hill, B. M. (1975). A simple general approach to inference about the tail of a distribution. *The Annals of Statistics*, 3(5), 1163-1174.
- Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica*, 57(2), 357-384.

### v3.0.0 T4 KS Migration BH-FDR Replaces Bonferroni (2026.07, Implemented)

> **Status**: Implemented, 934 passed + 6 skipped + 11 subtests passed (zero regression, 16 new tests vs v2.6.0's 918)
> **Docs**: [docs/EXECUTION_V3.0.0_T4.md](docs/EXECUTION_V3.0.0_T4.md) | [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md)
> **Baseline**: 918 passed + 6 skipped (v2.6.0) → 934 passed + 6 skipped (v3.0.0 T4, with 11 subtests)
> **Scope**: T4 (P0) of v3.0.0 long-term 4 tasks (T1-T4) completed

**3-Stage Execution (E1-E3)**:

| Stage | Task | Tests | Key Changes |
|-------|------|-------|-------------|
| **E1** | BH core implementation (Red→Green→Review) | 13 | `_ks_migration_significance` adds `correction_method` parameter (default 'benjamini_hochberg'), three-path dispatch (BH/Bonferroni/none), field isolation, ADR-002a written to DECISIONS.md |
| **E2** | Test updates | 3 | verify_fix1_manual.py validation 3 changed to BH-FDR formula check, test_factor_significance_manual.py adds TestKSMigrationBHCorrection class |
| **E3** | Doc sync + full regression | 0 | CHANGELOG/CODE_WIKI/README sync, verify_v3_0_0_t4_manual.py 8/8 manual verification, full regression 934 passed |

**1 New ADR**:
- **ADR-002a**: Benjamini-Hochberg FDR replaces Bonferroni (supersedes ADR-002's correction method, ADR-002 history preserved)

**5 Key Design Decisions**:
1. Default switched to BH, Bonferroni retained for backward compat (`correction_method='bonferroni'` opts into legacy path)
2. Three-path field isolation (BH: min_p_value_adjusted/correction_method; Bonferroni: alpha_corrected/bonferroni_correction)
3. None path for research/debugging (`correction_method='none'` no correction, direct `min_p < alpha`)
4. Golden reference: p=[0.01, 0.04, 0.03, 0.20, 0.50], K=5 → p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50]
5. Behavior change: BH is more lenient than Bonferroni, previously non-significant migrations may now become significant (`is_sig` may go False→True)

**Academic Basis**:
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *JRSS-B*, 57(1), 289-300.
- Consistent with `factor_significance.py`'s BH default (E7 already uses BH)

### v2.5.0 Multi-Factor Orthogonalization Three-Layer Architecture (Planning, Execution Plan v1.1)

> **Status**: Execution plan v1.1 completed (40 deepened sub-sections), pending implementation
> **Docs**: [docs/EXECUTION_V2.5.0.md](docs/EXECUTION_V2.5.0.md) | [docs/ANALYSIS_V2.5.0.md](docs/ANALYSIS_V2.5.0.md)

**Three-Layer Architecture Separation** (ADR-020):

| Layer | Responsibility | Module Location | Supervision |
|-------|---------------|-----------------|-------------|
| **Layer 1** | per-factor processing (existing) | `pipelines_v2.py` | Unsupervised |
| **Layer 2** | cross-factor cross-sectional orthogonalization (new) | `modules/factor_orthogonalizer/` | Unsupervised |
| **Layer 3** | target-aware significance testing (new) | `backtest/factor_significance.py` | Supervised (requires Y) |

**Layer 2 Core Algorithms** (5 types):
- **Symmetric (Löwdin)**: Default main method, VRR=1, no order dependency
- **Ridge**: Ill-conditioned matrix fallback, λ adaptive (Ledoit-Wolf 2004)
- **PCA**: Dimensionality reduction scenario, center parameter compatible with Layer 1 standardization
- **Gram-Schmidt**: Order-dependent scenario, κ>100 enables Kahan (1966) re-projection
- **Cholesky**: Positive semi-definite guaranteed scenario

**Layer 3 Significance Testing**:
- **Double Lasso**: treatment rotation mode, each factor independently as treatment, rotation order does not affect results
- **Elastic Net**: α/λ grid search, handles multi-factor collinearity

**Execution Plan v1.1 Deepened Content** (40 sub-sections):
- O1.12 Algorithm Core (7): threshold_mode three modes / eigh-svd selection / fit_from_gram / dtype coercion
- O2.8 Adapter Layer (6): align_mode / NaN handling / post_transform_hooks zero overhead / W cache
- O3a.6 Geometric Diagnostics (5): VRR ddof / VIF multi-method / condition number grading (Belsley-Kuh-Welsch 1980)
- O4.9 Double Lasso (7): treatment rotation / robust standard errors / multiple testing correction
- O4.11 RollingOrthogonalizer (5): incremental Gram reset / is_orthogonalized marker / warm-start LOBPCG
- O5.6 Synergy Design (5): data flow protocol / Neutralizer order / Grouped missing factors / conflict resolution
- O6.7-O6.11 Documentation Validation (5): TDD staged regression (6 Stages) / manual verification matrix (21 items) / performance benchmarks

**Performance Expectations**: K=20 Symmetric fit < 0.5ms; incremental Gram + warm-start achieves 42x speedup (vs full recompute)

**Constraint**: Orthogonalization disabled by default (`enabled=False`), does not affect 632 baseline tests

### v2.4.0 External Module Internalization (2026.07)

> **Status**: Implemented, 632 tests zero regression

**5 Processing Modules Internalized** (ADR-019):

| Module | Original External Path | Internalized Path | Dependency Trimming |
|--------|----------------------|-------------------|---------------------|
| **factor_fingerprint** | Factor_Fingerprint/ | `modules/factor_fingerprint/` | — |
| **factor_decoupler** | Factor_Decoupler/ | `modules/factor_decoupler/` | — |
| **factor_adaptive_winsor** | Factor_AdaptiveWinsor/ | `modules/factor_adaptive_winsor/` | Only core/ migrated (minimal packaging) |
| **factor_imputer** | Factor_Imputer_v2.0/ | `modules/factor_imputer/` | — |
| **factor_neutralizer** | Factor_Neutralizer_v2.0/ | `modules/factor_neutralizer/` | Removed matplotlib/joblib/psutil/numba |

**Key Decisions**:
- **Naming Unification**: lowercase snake_case, removed v2.0/v3.0 version suffixes (version info retained in module `__version__`)
- **Internalization over Sub-packaging** (ADR-019): For single-repo scenario, independence is false benefit; internalization eliminates importlib hacks and sys.path pollution
- **External Data Boundary Retained**: Factor_DB and Factor_Trading remain as external modules (data sources)
- **CI Simplification**: monorepo simulation reduced from 7 external modules to 2

**5-Stage Full Regression**: I1 (Fingerprint+Decoupler) → I2 (AdaptiveWinsor) → I3 (Imputer) → I4 (Neutralizer) → I5 (CI/docs cleanup),全程 632 passed zero regression throughout

### v2.3.0 CI Matrix and Dual-Track CI (2026.07)

> **Status**: Implemented

**GitHub Actions Matrix** (ADR-017):
- Python 3.10 / 3.11 / 3.12 × ubuntu-latest
- `fail-fast: false`: One version failure does not block other versions
- Windows temporarily excluded due to spawn method process startup overhead (ADR-016)

**tox Dual-Track CI**:
- Remote (GitHub Actions): Ensures push quality
- Local (tox): Fast cross-version compatibility verification, each env independently installs external modules for isolation
- CI config file script validation: 37/37 passed

**CI monorepo Simulation**: External modules cloned to parent directory via `git clone` to simulate local structure, directory renaming matches pyproject.toml package-dir mapping

### v2.2.2 Drift Detection and Optimizer Improvements (2026.07)

| Improvement | Priority | Description | Tests | Manual Verification |
|-------------|----------|-------------|-------|---------------------|
| **P0-1: Rolling Window KS** | P0 | Replaces binary split, rolling window + p-value filtering reduces false positives | 15/15 ✅ | — |
| **P0-2: Pipeline-in-the-loop** | P0 | Optimizer truly calls Pipeline fit+transform, complete 8-parameter mapping | 5/5 ✅ | — |
| **P1: per-factor min_dates** | P1 | Barra 41-day vs daily 1212-day adaptive threshold + reindex alignment | 7/7 ✅ | 8/8 ✅ |
| **P2-1: Three-mode Signal Fusion** | P2 | and/or/max replaces single AND logic, solves under-reporting | 11/11 ✅ | 12/12 ✅ |
| **P2-2: Optimizer CV Improvement** | P2 | _cv_evaluate interface rewrite, each fold train fit/test transform eliminates look-ahead | 9/9 ✅ | 12/12 ✅ |
| **P3-2: Grouped Parallel A/B Experiment** | P3 | 20-factor comparison, retained Plan A (ADR-009) | — | Experimental validation |

**Core Improvements**:
- Drift detection: Rolling window KS + p-value filtering + three-mode fusion (and/or/max)
- Optimizer: Pipeline-in-the-loop + CV eliminates look-ahead bias
- Data adaptation: per-factor min_dates + reindex alignment handles mixed-frequency factors

**Key Decision (ADR-009)**: P3-2 grouped parallel A/B comparison experiment proved Plan B (unified date range) infeasible — fwd_returns semantics differ for different frequency factors; unifying to daily frequency changes IC meaning. Retained Plan A (grouped by date).

**Tests**: 612/612 all passed, 32/32 manual verification passed, regression tests no new failures.

### v2.2.1 L2 Disk Cache Layer (2026.07)

| Module | Priority | Description | Tests |
|--------|----------|-------------|-------|
| **`cache_manager.py`** | P0 | L2 disk cache infrastructure, supports DataFrame (.parquet) + ndarray (.npy) + .meta.json metadata | 34/34 ✅ |
| **`price_cache.py`** | P1 | Price matrix cache, wraps PriceQuery.get_price_matrix() | 12/12 ✅ |
| **`factor_cache.py`** | P1 | Factor matrix cache, wraps FactorPivotAdapter.get_pivoted(), supports partial hits | 12/12 ✅ |
| **`cached_data_loader.py`** | P2 | Unified entry, business code enables cache with one replacement | 13/13 ✅ |
| **`fwd_returns_cache.py`** | P2 | Forward returns ndarray cache, accepts compute_fn for on-demand calculation | 10/10 ✅ |
| **End-to-end Integration Test** | P3 | Real DB runs full Pipeline, verifies cache hits and result consistency | 4/4 ✅ |

**Core Design** (ADR-008):
- Three Principles: P0 Debuggability > P1 Correctness > P2 Performance
- Three-Layer Transparency: Logging (HIT/MISS) + .meta.json metadata + environment variable escape hatch (`FACTOR_PIPELINE_CACHE=disabled`)
- Data fingerprint verification + corruption self-healing + dual-axis freq fidelity
- Data loading stage 4.36x speedup (1.466s → 0.336s)

**Usage**:
```python
from factor_pipeline.backtest.cached_data_loader import CachedDataLoader

# One replacement to enable caching
loader = CachedDataLoader(
    db_path="factor_db.duckdb",
    cache_dir="./cache",
    enabled=True,
)
factor_data = loader.get_pivoted_factors(["PE", "PB"], start_date, end_date)
price_data = loader.get_price_matrix(field="close", start_date, end_date)

# One-click disable for debugging
# export FACTOR_PIPELINE_CACHE=disabled
```

**Tests**: 85/85 all passed, regression tests no new failures.

### v2.2.0 Backtest Integration (2026.07)

| Module | Priority | Description | Tests |
|--------|----------|-------------|-------|
| **`factor_metrics.py`** | P1 | Factor-level metrics single source of truth, IC/ICIR/Decay/Turnover/LS/Spread sole authority | 30/30 ✅ |
| **`data_bridge.py`** | P2 | Pipeline → DataLoaderV3 format adapter, transposes (n_stocks, n_dates) → (n_dates, n_stocks) | 10/10 ✅ |
| **`engine.py`** | P3 | Factor backtest engine, adapted from `engine_v3_vector.py`, uses single source of truth | 20/20 ✅ |
| **`health_bridge.py`** | P4 | Backtest → FactorHealthMonitor adapter, does not modify external modules | 13/13 ✅ |
| **`unified_drift.py`** | P5 | Dual-track fusion drift judgment: structural drift (Fingerprint) + performance drift (Backtest) + turnover drift | 13/13 ✅ |
| **`pipeline_integration.py`** | P6 | End-to-end Pipeline integration runner + BacktestConfig configuration extension | 9/9 ✅ |

**Core Design**:
- Single Source of Truth: `factor_metrics.py` sole authority, avoids duplicate computation
- Adapter Pattern: Two adapters isolate dependencies, do not modify external modules
- Dual-Track Fusion: Structural drift + performance drift, improves drift detection reliability
- importlib Bypasses Heavy Dependencies: Resolves `core` namespace conflict

**Tests**: 95/95 all passed, regression tests no new failures.

### v2.1.0 Architecture Fixes (2026.07)

| Fix | Priority | Description | Impact |
|-----|----------|-------------|--------|
| **Probabilistic Weighted Soft Routing** | P0 | Hard routing → multi-pipeline weighted mixing, eliminates cliff effect at factor type switching | Smooth transition, no jumps |
| **Data-Driven Threshold Calibration** | P0 | `ThresholdCalibrator` quantile method + market presets, replaces hardcoded thresholds | Adaptive to data distribution |
| **Unified `fit()` Intermediate Data** | P1 | Three pipelines unified `_intermediate_data` + `get_intermediate_data()` | Full traceability |
| **Adapter Fallback Warning** | P1 | `warnings.warn(UserWarning)` when external modules unavailable, replaces silent failure | Improved transparency |
| **Migration Weight Fusion** | P1 | `_merge_transition_weights()` fuses classification weights + exponentially decayed migration weights | Smooth transition period |
| **KS Migration Significance Test** | P2 | `scipy.stats.ks_2samp` + BH-FDR correction (T4 v3.0.0, default; Bonferroni backward-compat), filters noise migration | Controlled false positives, improved detection power |
| **`importlib` Context Manager** | P2 | `_temp_sys_path` replaces `sys.path.insert`, exception-safe recovery | Global state isolation |

**Tests**: 229 tests, 222 passed, 3 pre-existing failures, no new regressions.

### v2.0.0 Intelligent Adaptive Pipeline (2026.05)

| New Feature | Description | Impact |
|-------------|-------------|--------|
| **Factor Fingerprint Diagnostic Layer** | 13-dimensional statistical metrics auto-diagnose factor time-series/cross-sectional characteristics | Replaces manual judgment with objective classification |
| **Adaptive Factor Classification** | Static / Dynamic / Mixed three-class auto-routing | Different types follow different processing flows |
| **Semantic-Statistical Fusion** | Natural language construction rules + statistical fingerprint Bayesian fusion | Prior knowledge reduces data dependency |
| **Triple Neutralization** | Raw value neutralization → AR modeling → residual neutralization | Solves endogeneity deficiency of traditional single neutralization |
| **GARCH Whitening (Optional)** | Eliminates volatility clustering for high-autocorrelation static factors | Disabled by default, explicitly enabled |
| **Processing Order Adjustment** | Static/Mixed factors: neutralization before standardization | Conforms to Barra/MSCI best practices |
| **Continuous Migration Monitoring** | Factor style drift auto-alerting | Lifecycle management |
| **GarchWhiteningAdapter** | New adapter, reuses existing PipelineStep pattern | Minimal invasive extension |

### v1.0 → v2.0 → v2.1 → v2.2 → v2.4.0 → v2.5.0 Architecture Evolution

```
v1.0: Single Fixed Pipeline
Raw factors → Imputation → Outlier detection → Transformation → Standardization → Neutralization

v2.0: Intelligent Adaptive Flow
Raw factors → Fingerprint extraction → Classification (semantic+statistical) → Routing → Migration monitoring
                ↓
        ┌───────┼───────┐
        ↓       ↓       ↓
    Static    Dynamic   Mixed
   Pipeline  Pipeline  Pipeline
   (high AR1) (low AR1) (mid AR1)

v2.1: Probabilistic Weighted Soft Routing + KS Statistical Filtering
Raw factors → Fingerprint extraction → Probabilistic weighting → Multi-pipeline mixing → KS validation → Output
                ↓
        Weights: 0.70 static + 0.20 mixed + 0.10 dynamic → Weighted fusion

v2.2: Backtest Engine Integration + Full-Chain Closed Loop
Raw factors → Pipeline → Processed factors
                ↓
         DataBridge → Engine → HealthMonitor → UnifiedDrift
                ↓
         IC/ICIR/Decay/Turnover + 5-dim health score + Fusion drift judgment

v2.2.2: Drift Detection and Optimizer Improvements
Rolling KS + p-value filtering → Three-mode fusion (and/or/max)
Optimizer: Pipeline-in-the-loop + CV train-fit/test-transform (no look-ahead)
Data adaptation: per-factor min_dates + reindex alignment (Barra 41-day vs daily 1212-day)

v2.3.0: CI Matrix + Dual-Track CI
GitHub Actions (Python 3.10/3.11/3.12 × ubuntu) + tox local cross-version verification

v2.4.0: External Module Internalization (ADR-019)
5 processing modules internalized to modules/: Fingerprint / Decoupler / AdaptiveWinsor / Imputer / Neutralizer
External data boundary retained: Factor_DB / Factor_Trading
632 tests zero regression, CI monorepo simulation reduced from 7 to 2 external modules

v2.5.0: Multi-Factor Orthogonalization Three-Layer Architecture (Planning)
Layer 1 (per-factor) → Layer 2 (cross-factor orthogonalization) → Layer 3 (target-aware testing)
  Symmetric orthogonalization (Löwdin) / Ridge / PCA / GS / Cholesky
  Double Lasso (treatment rotation) + Elastic Net
  Default enabled=False, does not affect 632 baseline
```

---

## Architecture Design

```
┌─────────────────────────────────────────────────────────────────┐
│              FactorProcessingPipelineV2                          │
│                 (Intelligent Orchestrator Layer)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Intelligence Layer                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │   │
│  │  │  Fingerprint│  │  Classifier │  │Semantic-Statistical│ │   │
│  │  │  Extractor  │  │  (AR1-based)│  │    Fusion         │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────────┘ │   │
│  │         └─────────────────┘                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Type Router Layer                           │   │
│  │         STATIC    DYNAMIC    MIXED                       │   │
│  │            ↓         ↓         ↓                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Processing Layer                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │   │
│  │  │StaticPipeline│  │DynamicPipeline│  │MixedPipeline│    │   │
│  │  │Nonlinear     │  │Triple        │  │Conditional  │    │   │
│  │  │transform     │  │neutralization│  │transform    │    │   │
│  │  │[Optional]GARCH│  │AR decoupling │  │Mild winsor  │    │   │
│  │  │Neutral→Std   │  │Standardize   │  │Neutral→Std  │    │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Monitoring Layer                            │   │
│  │         FactorFingerprintMonitor                         │   │
│  │         - Type migration detection                       │   │
│  │         - Style drift alerting                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Four Core Components

| Component | Responsibility | Unique Value |
|-----------|---------------|--------------|
| **PipelineOrderValidator** | Validates processing step order | Complete blank in open-source community |
| **Adapter Layer** | Unified module interface | sklearn-style encapsulation |
| **FactorFingerprint** | 13-dimensional factor diagnosis | From empirical judgment to data-driven |
| **SemanticStatisticalFusion** | Semantic + statistical fusion classification | Prior-guided, posterior-calibrated |

---

## Module Composition

### Sub-module 1: Factor Imputer v2.0

| Attribute | Details |
|-----------|---------|
| **Theme** | OpenClaw (blue-purple) |
| **Core Class** | `HierarchicalImputer` |
| **Imputation Strategies** | 5 types: cross-sectional mean / time-series forward / panel hierarchical / ML advanced / factor-specific |
| **Missing Detection** | MCAR/MAR/MNAR type identification + missing pattern analysis |
| **Feature** | Lookahead-Free design, vectorized execution |

### Sub-module 2: Factor AdaptiveWinsor v2.0

| Attribute | Details |
|-----------|---------|
| **Theme** | CLI Arcade (green) |
| **Core Class** | `SmartOutlierDetector` / `AdaptiveTransformer` / `AdaptiveStandardizer` |
| **Outlier Methods** | 6 auto-selected: quantile / Z-score / MAD / IQR / adaptive / Sigmoid |
| **Transform Methods** | Box-Cox / Yeo-Johnson / quantile transform, adaptive selection |
| **Standardization** | Z-score / Rank / MinMax / Robust, statistic voting |

### Sub-module 3: Factor Neutralizer v2.0

| Attribute | Details |
|-----------|---------|
| **Theme** | Synthwave (pink-orange sunset) |
| **Core Class** | `FactorNeutralizer` |
| **Neutralization Types** | Industry neutralization / Market-cap neutralization / Index neutralization |
| **Regression Methods** | OLS / WLS / Ridge, cross-sectional regression residual extraction |

### Sub-module 4: Factor_Fingerprint

| Attribute | Details |
|-----------|---------|
| **Core Class** | `FactorFingerprinter` / `AdaptiveFactorClassifier` / `SemanticStatisticalFusion` |
| **Fingerprint Dimensions** | 13 dimensions: AR(1), rank autocorrelation, half-life, volatility clustering, skewness, kurtosis, etc. |
| **Classification Method** | AR(1) threshold method + Bayesian fusion (supports semantic prior) |
| **Monitoring Features** | Type migration detection, style drift alerting |

### Sub-module 5: Factor_Decoupler

| Attribute | Details |
|-----------|---------|
| **Core Class** | `CompositeDecoupler` / `AROrderSelector` / `DualNeutralizer` |
| **Decoupling Methods** | AR model / first-order differencing / HP filter / auto-selection |
| **Dual Neutralization** | Raw value neutralization → AR modeling → residual neutralization |
| **Academic Basis** | Hausman (1978) endogeneity theory |

---

## Three Differentiated Pipelines

### Pipeline 1: StaticFactorPipeline (Static Factors)

**Applicable Conditions**: `ar1_median > 0.80` and `rank_autocorr > 0.70`
**Typical Representatives**: Price-to-Book (PB), Price-to-Earnings (PE), Dividend Yield

```
Raw factors
    ↓
Missing value imputation
    ↓
Outlier detection
    ↓
Adaptive nonlinear transformation
    ↓
[Optional] GARCH whitening (GarchWhiteningAdapter)  ← disabled by default
    ↓
Neutralization                                     ← v2.0 adjustment: neutralize first
    ↓
Standardization                                    ← v2.0 adjustment: standardize after
    ↓
Processing complete
```

**Why this processing**:
- Static factors' value lies in cross-sectional ranking; nonlinear transformation effectively tames heavy tails and skewness
- High autocorrelation means GARCH pre-whitening may be necessary (eliminates volatility clustering)
- **v2.0 adjustment**: Neutralize before standardize, conforming to Barra/MSCI best practices

**GARCH Whitening Enablement**:
```python
pipeline = StaticFactorPipeline(
    neutralizer_params={'industry_data': industry_series},
    enable_garch=True,  # explicitly enable
    garch_params={'p': 1, 'q': 1, 'vol': 'Garch', 'min_obs': 50}
)
```

---

### Pipeline 2: DynamicFactorPipeline (Dynamic Factors)

**Applicable Conditions**: `ar1_median < 0.40`
**Typical Representatives**: Short-term reversal, turnover change, volatility change

```
Raw factors
    ↓
Missing value imputation
    ↓
Raw value dual neutralization (Dual Neutralization Stage 1)
    ↓
AR modeling → residual extraction (AR Decoupling)
    ↓
Residual neutralization (Dual Neutralization Stage 2)
    ↓
Standardization
    ↓
Processing complete
```

**Why this processing**:
- Dynamic factors' value lies in time-series changes; **nonlinear transformation prohibited** to protect time-series signal
- Neutralization must be performed at raw value stage to strip endogeneity exposure (first neutralization)
- After AR modeling, second neutralization strips industry/market-cap exposure in residuals
- **GARCH whitening absolutely prohibited**, as series near white-noise would introduce new noise through volatility standardization

---

### Pipeline 3: MixedFactorPipeline (Mixed Factors)

**Applicable Conditions**: `0.40 <= ar1_median <= 0.80`
**Typical Representatives**: 1-month momentum, 3-month momentum

```
Raw factors
    ↓
Missing value imputation
    ↓
Mild outlier detection (3σ winsorization)
    ↓
[Conditional] Nonlinear transformation (Conditional Transformation)
    ↓
Neutralization                                     ← v2.0 adjustment: neutralize first
    ↓
Standardization                                    ← v2.0 adjustment: standardize after
    ↓
Processing complete
```

**Why this processing**:
- These factors fall between the two extremes; the most conservative strategy is degraded processing
- Only mild winsorization and neutralization; conditional nonlinear transformation (based on skewness/kurtosis thresholds)
- Prefer to retain some raw noise rather than risk damaging signal structure

---

## Processing Order Validation

### Validation Rules (Academic-Level)

```python
DEPENDENCIES = {
    OUTLIER_DETECTION: [IMPUTATION],
    TRANSFORMATION:    [IMPUTATION, OUTLIER_DETECTION],
    STANDARDIZATION:   [IMPUTATION, OUTLIER_DETECTION],
    NEUTRALIZATION:    [IMPUTATION],
}
```

| Rule | Reason |
|------|--------|
| **IMPUTATION must be first** | Outlier detection statistics (MAD/quantiles) require complete data |
| **OUTLIER must precede TRANSFORM** | Outliers severely distort transformation parameter estimation |
| **OUTLIER must precede STANDARDIZE** | Outliers significantly affect post-standardization distribution |
| **NEUTRALIZATION order varies by type** | Static/Mixed: neutralize then standardize; Dynamic: neutralize before AR |

### v2.0 Order Adjustment Explanation

**v1.0 Order** (uniform for all factors):
```
Imputation → Outlier detection → Transformation → Standardization → Neutralization
```

**v2.0 Order** (varies by type):
```
Static/Mixed: Imputation → Outlier detection → Transformation → Neutralization → Standardization
Dynamic:      Imputation → Neutralization → AR modeling → Residual neutralization → Standardization
```

**Adjustment Reasons**:
- Static factors' standardization should be based on post-neutralization residuals, avoiding industry/market-cap exposure affecting standardization baseline
- Dynamic factors' neutralization must precede AR modeling to control endogeneity (Hausman, 1978)

---

## Comparison with Open-Source Community

### Mainstream Quant Framework Analysis

| Project | Stars | Data Processing Coverage | Factor Classification | Order Validation | Semantic Fusion | Activity |
|---------|-------|-------------------------|----------------------|-------------------|-----------------|----------|
| **Microsoft Qlib** | 29.2k | ⭐⭐⭐⭐⭐ | ❌ None | ❌ None | ❌ None | Very high |
| **Quantopian Alphalens** | 3.8k | ⭐⭐ | ❌ None | ❌ None | ❌ None | Stagnant |
| **Zipline** | 17k | ⭐⭐ | ❌ None | ❌ None | ❌ None | Stagnant |
| **This Pipeline v2.0** | - | ⭐⭐⭐⭐⭐ | ✅ **Unique** | ✅ **Unique** | ✅ **Unique** | Active |

### Feature Depth Comparison

| Feature | This Pipeline v2.0 | Qlib | Alphalens |
|---------|-------------------|------|-----------|
| Missing value imputation | ✅ 5-strategy hierarchical intelligent imputation | ⚠️ Simple fill/drop | ❌ None |
| Adaptive outlier detection | ✅ 6-method intelligent selection | ⚠️ Tanh compression only | ❌ None |
| Distribution transformation | ✅ Adaptive Box-Cox/YJ | ❌ None | ❌ None |
| Standardization | ✅ Statistic voting selection | ✅ Z-score/Rank | ❌ None |
| Neutralization | ✅ Industry/Market-cap/Index | ❌ None | ❌ None |
| **Factor fingerprint classification** | ✅ **13-dim diagnosis + adaptive classification** | ❌ None | ❌ None |
| **Semantic-statistical fusion** | ✅ **Prior-guided + posterior-calibrated** | ❌ None | ❌ None |
| **Triple neutralization** | ✅ **Raw value → residual dual** | ❌ None | ❌ None |
| **GARCH whitening** | ✅ **Optional pre-whitening** | ❌ None | ❌ None |
| **Order validation** | ✅ **Academic-level validator** | ❌ None | ❌ None |
| **Migration monitoring** | ✅ **Style drift detection** | ❌ None | ❌ None |

### Core Marginal Contributions

1. **Factor Fingerprint Diagnostic System** — Complete blank in open-source community; elevates factor classification from empirical judgment to data-driven
2. **Semantic-Statistical Fusion** — Introduces natural language construction rules as prior, reducing data dependency and overfitting risk
3. **Triple Neutralization** — Solves endogeneity deficiency of traditional single neutralization (Hausman, 1978)
4. **Adaptive Processing Order** — Different factor types follow different flows, not one-size-fits-all
5. **GARCH Whitening Option** — Provides volatility clustering elimination for high-autocorrelation static factors

---

## Quick Start

### Method 1: v2.0 Intelligent Pipeline (Recommended)

```python
from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config
from Factor_Fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

# Configuration
config = PipelineV2Config(
    fingerprint=FingerprintConfig(min_window=24),
    classification=ClassificationConfig(),
    monitor=MonitorConfig(),
    dynamic_decorrelation_strength=1.0,
    dynamic_max_ar_order=5,
    dynamic_ar_criterion='aic',
    static_enable_garch=False,  # disabled by default, enable when needed
)

# Create pipeline
pipeline = FactorProcessingPipelineV2(config)

# Fit (supports semantic descriptions)
descriptions = {
    'pb_factor': 'Price-to-book factor, based on latest report book value divided by total market cap',
    'reversal_factor': 'Opposite of past 1-month daily returns',
    'momentum_factor': 'Cumulative return over past 12 months excluding most recent 1 month',
}

pipeline.fit(
    factor_data={'pb_factor': pb_df, 'reversal_factor': rev_df, 'momentum_factor': mom_df},
    industry_data=industry_series,
    descriptions=descriptions,  # optional: enables semantic-statistical fusion
)

# Transform
results = pipeline.transform(factor_data)

# View classification results
print(pipeline.get_classification_summary())

# Check migrations
alerts = pipeline.check_migrations(factor_data)
```

### Method 2: Use Three Pipelines Individually

```python
from factor_pipeline.pipelines_v2 import (
    StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline
)

# Static factor pipeline (optionally enable GARCH)
static_pipe = StaticFactorPipeline(
    neutralizer_params={'industry_data': industry_series},
    enable_garch=True,  # explicitly enable GARCH whitening
    garch_params={'p': 1, 'q': 1, 'min_obs': 50}
)
result = static_pipe.fit_transform(pb_data)

# Dynamic factor pipeline (triple neutralization)
dynamic_pipe = DynamicFactorPipeline(
    decorrelation_strength=1.0,
    max_ar_order=5,
    ar_criterion='aic',
    neutralizer_params={'industry_data': industry_series}
)
result = dynamic_pipe.fit_transform(reversal_data)

# Mixed factor pipeline
mixed_pipe = MixedFactorPipeline(
    conditional_transform=True,
    skew_threshold=2.0,
    kurt_threshold=5.0,
    neutralizer_params={'industry_data': industry_series}
)
result = mixed_pipe.fit_transform(momentum_data)
```

### Method 3: v1.0 Compatibility Mode (Fixed Five-Step Method)

```python
from factor_pipeline import FactorProcessingPipeline

# Create default pipeline
pipeline = FactorProcessingPipeline.default_pipeline()
result = pipeline.fit_transform(factor_data)
```

### Method 4: Backtest Engine (v2.2.0 New)

```python
from factor_pipeline.backtest import (
    FactorBacktestEngine, DataBridge, HealthMonitorAdapter,
    UnifiedDriftReporter, PipelineBacktestRunner
)
from factor_pipeline.config_v2 import PipelineV2ConfigUnified, BacktestConfig

# Configuration
config = PipelineV2ConfigUnified(
    backtest=BacktestConfig(
        ic_method="rank",
        top_n=0.2,
        enable_drift_detection=True,
        enable_health_check=True,
    )
)

# End-to-end run
runner = PipelineBacktestRunner(config)
results = runner.run(factor_data, price_data, factor_names=["pb_factor", "reversal"])
print(runner.summary())

# Use backtest engine standalone
engine = FactorBacktestEngine(dataloader)
engine.run()
print(engine.summary())  # IC/ICIR/Decay/HitRate/Turnover/LS/Spread

# Health assessment
adapter = HealthMonitorAdapter()
report = adapter.build_report_from_engine(engine, "pb_factor")
print(report.health_score)  # 0-100 comprehensive health score

# Drift detection
drift = UnifiedDriftReporter()
result = drift.evaluate_from_engine(engine, "pb_factor", historical_data)
print(result.level)  # stable / warning / drift_detected / severe_drift
```

---

## Configuration

### PipelineV2Config Full Configuration

```python
@dataclass
class PipelineV2Config:
    fingerprint: FingerprintConfig = field(default_factory=FingerprintConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)

    # Dynamic factor decoupling parameters
    dynamic_decorrelation_strength: float = 1.0   # AR residual extraction strength [0, 1]
    dynamic_max_ar_order: int = 5                  # Maximum AR order
    dynamic_ar_criterion: str = 'aic'              # Order selection criterion: aic/bic/hqic

    # Mixed factor parameters
    mixed_conditional_transform: bool = True       # Whether conditional transformation
    mixed_skew_threshold: float = 2.0              # Skewness threshold
    mixed_kurt_threshold: float = 5.0              # Kurtosis threshold

    # Static factor GARCH parameters (disabled by default)
    static_enable_garch: bool = False              # Whether to enable GARCH whitening
    static_garch_p: int = 1                        # GARCH p order
    static_garch_q: int = 1                        # GARCH q order
    static_garch_vol: str = 'Garch'                # Volatility model
    static_garch_min_obs: int = 50                 # Minimum observations
```

---

## API Reference

### FactorProcessingPipelineV2

| Method | Description |
|--------|-------------|
| `fit(factor_data, industry_data, descriptions)` | Fit entire pipeline (including fingerprint extraction, classification, pipeline initialization) |
| `transform(factor_data)` | Apply pipeline transformation |
| `fit_transform(factor_data, industry_data)` | Fit and transform |
| `get_classification_summary()` | Get classification summary table |
| `get_fingerprint_summary()` | Get fingerprint summary table |
| `check_migrations(factor_data)` | Check factor type migrations |
| `get_execution_summary()` | Get execution summary |

### StaticFactorPipeline

| Method | Description |
|--------|-------------|
| `fit(X, **kwargs)` | Fit pipeline (imputation → outlier → transform → [GARCH] → neutralize → standardize) |
| `transform(X)` | Apply pipeline transformation |
| `fit_transform(X)` | Fit and transform |

### DynamicFactorPipeline

| Method | Description |
|--------|-------------|
| `fit(X, **kwargs)` | Fit pipeline (imputation → triple neutralization → standardization) |
| `transform(X)` | Apply pipeline transformation |
| `fit_transform(X)` | Fit and transform |
| `get_decoupling_summary()` | Get decoupling summary (including AR model info) |

### GarchWhiteningAdapter

| Parameter | Description | Default |
|-----------|-------------|---------|
| `p` | ARCH order | 1 |
| `q` | GARCH order | 1 |
| `vol` | Volatility model | 'Garch' |
| `min_obs` | Minimum observations | 50 |

---

## File Structure

```
factor_pipeline/
├── __init__.py                 # Package entry
├── config.py                   # v1.0 config management (StepType, PipelineConfig)
├── config_v2.py                # v2.0 Pydantic config management (PipelineV2ConfigUnified)
├── adapters.py                 # Unified adapter layer
│   ├── PipelineStep            # Abstract base class
│   ├── ImputerAdapter          # Imputation adapter (REQUIRED)
│   ├── ProcessingAdapter       # Processing adapter (outlier/transform/standardize, REQUIRED)
│   ├── NeutralizerAdapter      # Neutralization adapter (REQUIRED, ADR-018 fit/transform semantic consistency)
│   └── GarchWhiteningAdapter   # GARCH whitening adapter (OPTIONAL, arch dependency)
├── pipeline.py                 # v1.0 core pipeline + order validator
├── pipelines_v2.py             # v2.0 intelligent pipeline (fingerprint+classification+3 pipelines+soft routing)
├── optimizer.py                # v2.2.1 optimizer (Pipeline-in-the-loop + CV)
├── dag.py                      # Directed Acyclic Graph dependency management
├── cache.py                    # Intermediate result cache
├── reporting.py                # Execution report generation
├── performance.py              # Performance optimization tools
├── exceptions.py               # Custom exception hierarchy
├── types.py                    # Core type system
├── pyproject.toml              # Project config (flat-layout, where=[".."])
├── tox.ini                     # Dual-track CI local config (ADR-017)
├── .github/workflows/ci.yml    # GitHub Actions CI matrix
├── docs/                       # Documentation directory
│   ├── EXECUTION_V2.5.0.md     # v2.5.0 execution plan v1.1 (40 deepened sub-sections)
│   ├── ANALYSIS_V2.5.0.md      # v2.5.0 analysis report
│   ├── EXECUTION_V2.4.0.md     # v2.4.0 execution record
│   ├── KABC_paper_draft.md     # KABC paper draft
│   └── ...                     # Other analysis documents
├── backtest/                   # Backtest engine module (v2.2.0, ADR-007)
│   ├── factor_metrics.py       # Factor-level metrics single source of truth (IC/ICIR/Decay/Turnover)
│   ├── data_bridge.py          # Pipeline → DataLoaderV3 adapter
│   ├── engine.py               # Factor backtest engine
│   ├── health_bridge.py        # Backtest → FactorHealthMonitor adapter
│   ├── unified_drift.py        # Dual-track fusion drift judgment (rolling KS + EWMA)
│   ├── pipeline_integration.py # End-to-end Pipeline integration
│   ├── cache_manager.py        # L2 disk cache infrastructure (ADR-008)
│   ├── cached_data_loader.py   # Cache unified entry
│   ├── factor_cache.py         # Factor matrix cache (partial hit)
│   ├── price_cache.py          # Price matrix cache
│   ├── fwd_returns_cache.py    # Forward returns cache
│   ├── factor_pivot.py         # DuckDB PIVOT factor wide-table transform
│   ├── parallel_runner.py      # Multi-factor process parallel (grouped by date)
│   └── __init__.py             # 26 public API exports
├── modules/                    # Internalized processing modules (v2.4.0, ADR-019)
│   ├── factor_fingerprint/     # Factor fingerprint (13-dim statistical metrics)
│   ├── factor_decoupler/       # Time-series decoupling (AR modeling + residual neutralization)
│   ├── factor_adaptive_winsor/ # Adaptive winsorization (core/ only, minimal packaging)
│   ├── factor_imputer/         # Factor imputation (lookahead-free)
│   └── factor_neutralizer/     # Factor neutralization (38 methods, class imported not instantiated)
├── scripts/                    # Auxiliary scripts
│   ├── check_trading_v3.py
│   ├── verify_p3_manual.py
│   └── verify_td1_manual.py
├── tests/                      # Test directory (632+ tests)
│   ├── unit/                   # Unit tests
│   ├── test_backtest/          # Backtest module tests
│   ├── test_fix1-7_*.py        # v2.2.2 code quality fix tests
│   ├── test_p0-p3_*.py         # v2.1/v2.2 improvement tests
│   └── verify_*_manual.py      # Manual numerical verification scripts
└── README.md                   # This document
```

---

## Technical Features

- **sklearn-style interface**: Unified `fit/transform/fit_transform` pattern
- **Configurable flow**: Supports JSON/YAML/dict configuration
- **Strict order validation**: Academic-rule-based automated validation
- **Intermediate state tracking**: Input/output shapes, missing rates, statistics per step
- **Error interception**: Invalid orders intercepted at initialization stage
- **Fallback mechanism**: Auto-degrades to simple implementation when sub-modules missing
- **Semantic fusion**: Supports natural language descriptions as classification prior
- **Migration monitoring**: Factor style drift auto-detection and alerting
- **GARCH whitening**: Optional volatility clustering elimination (disabled by default)

---

## Version Information

- **Pipeline Version**: v3.2.0 (academic-principled refactoring, implemented)
- **Internalized Modules**: factor_fingerprint / factor_decoupler / factor_adaptive_winsor / factor_imputer / factor_neutralizer / factor_orthogonalizer (v2.4.0 ADR-019 + v2.5.0 ADR-020) + **statistical_classifier** (NEW v3.2.0 ADR-027)
- **External Data Boundary**: Factor_DB / Factor_Trading (DataLoaderV3)
- **Test Baseline**: 168/168 (v3.2.0 full regression)
- **CI Matrix**: Python 3.10/3.11/3.12 × ubuntu-latest (ADR-017)
- **Build Date**: 2026.07.10
- **Status**: STABLE (v3.2.0 academic principles-driven)

### Version History

| Version | Date | Key Updates |
|---------|------|-------------|
| v1.0.0 | 2026.05.12 | Initial version: unified orchestration layer + order validation |
| v2.0.0 | 2026.05.17 | Intelligent version: fingerprint diagnosis + adaptive classification + semantic fusion + triple neutralization + GARCH whitening |
| v2.1.0 | 2026.07.01 | Architecture fixes: soft routing + threshold calibration + unified fit() + adapter warnings + KS significance + importlib refactor |
| v2.2.0 | 2026.07.01 | Backtest integration: backtest engine (95/95) + dual-track drift fusion + HealthMonitor adapter + BacktestConfig |
| v2.2.1 | 2026.07.01 | Drift detection improvements + L2 cache layer (ADR-008, 4.36x speedup) + optimizer Pipeline-in-the-loop + CV eliminates look-ahead |
| v2.2.2 | 2026.07.02 | 7 code quality fixes (self.factors bug / config unification / version unification / backtest exports / core namespace isolation / hardcoded path config) |
| v2.3.0 | 2026.07.02 | CI matrix (Python 3.10/3.11/3.12 × ubuntu, ADR-017) + tox dual-track CI + CI config script validation (37/37) |
| v2.4.0 | 2026.07.03 | External module internalization (5 modules → modules/, ADR-019) + naming unification lowercase snake_case + dependency trimming + 632 tests zero regression |
| v2.5.0 | 2026.07.03 | Multi-factor orthogonalization three-layer architecture (ADR-020, O1-O6 all completed): Layer 2 cross-sectional orthogonalization (5 algorithms) + Layer 3 double Lasso testing + rolling/grouping/triple-set, 860 passed + 5 skipped |
| v2.6.0 | 2026.07.04 | Optimizer and drift detection enhancement (ADR-021/022/023, E1-E9 all completed): objective function aligned with ADR-004 (6 items IC-vol-cov-ks-health-redundancy) + orthogonalization param search space + Layer 3 significance test (Belloni 2014 PDS) + ThresholdDriftMonitor (EWMA decay detection), 918 passed + 6 skipped + 11 subtests |
| v3.0.0 T4 | 2026.07.04 | KS migration detection BH-FDR replaces Bonferroni (ADR-002a, E1-E3 all completed): `_ks_migration_significance` three-path dispatch (BH/Bonferroni/none, default BH) + field isolation + backward compat + golden reference verification, Benjamini-Hochberg (1995) FDR control, 934 passed + 6 skipped + 11 subtests |
| v3.0.0 T1 | 2026.07.04 | Fingerprint dimension expansion to 21-dim (ADR-024, E1-E3 all completed), 974 passed + 6 skipped + 11 subtests |
| v3.1.0 | 2026.07.09 | Audit-Driven Code Quality Remediation (ADR-026): P0+P1×16 + P2+×15 + spec alignment×11, subset regression 754 passed+1 skipped |
| v3.2.0 | 2026.07.10 | Academic-Principled Pipeline Refactoring (ADR-027): all `auto` modes→fixed methods, SOFT→hard routing, Shapiro-Wilk/Variance Ratio/Anderson-Rubin formal tests, 9-step TDD (168/168 regression), principles ratio 68%→88% |

---

## Academic References

The processing order and classification logic of this pipeline is based on the following academic and industry standards:

- Barra multi-factor model data processing specifications
- MSCI factor standardization best practices
- Quantopian factor research framework
- Hausman (1978) endogeneity test and instrumental variable theory
- Engle (1982) ARCH/GARCH volatility modeling
- Box & Cox (1964) transformation theory
- "Quantitative Equity Portfolio Management" (Qian et al.)
- "Active Portfolio Management" (Grinold & Kahn)
- Löwdin (1950) symmetric orthogonalization (v2.5.0 Layer 2 main method)
- Ledoit & Wolf (2004) covariance matrix shrinkage estimation (v2.5.0 Ridge λ adaptive)
- Kahan (1966) Gram-Schmidt re-projection numerical stability (v2.5.0 GS re-orth)
- Belsley, Kuh & Welsch (1980) condition number diagnostics and collinearity analysis (v2.5.0 geometric diagnostics)
- Belloni & Chernozhukov (2013) double Lasso selection inference (v2.5.0 Layer 3 significance testing)
