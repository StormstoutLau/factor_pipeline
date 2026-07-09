# -*- coding: utf-8 -*-
"""内生性诊断编排器 — 四阶段检验 (§1.6.9, v1.3 修正).

S1: 缺失机制诊断 (插补前) — 识别 MNAR/选择偏差
    输出: 分类标签 + mnar_risk_prior ∈ [0,1]
S2: 原始因子内生性基线 (插补后/中性化前) — 建立 baseline
    输出: 连续 τ ∈ [0,1]
S3: 截面内生性残留 (中性化后/解耦前, 可选) — 验证中性化有效性
    输出: 连续 τ ∈ [0,1]
S4: 增量+时序内生性残留 (解耦后) — 验证解耦有效性, 输出最终 τ_i
    输出: 连续 τ ∈ [0,1]

重要 (v1.3 修正):
- S1 → S2 是上下文衔接 (非数值差分): S1 的 mnar_risk_prior 作为 S2 基线的解读上下文
- S3 - S2, S4 - S3, S4 - S2 是数值差分 (连续 τ 之间)
"""
from typing import Dict, Any, Optional, List
import pandas as pd
from .missingness_checker import MissingnessMechanismChecker
from .oster_delta import OsterDeltaChecker
from .aet_checker import AltonjiElderTaberChecker
from .ife_checker import InteractiveFEChecker
from .lewbel_iv import LewbelInternalIVChecker
from .threat_assessor import EndogeneityThreatAssessor


class EndogeneityDiagnosticOrchestrator:
    """内生性诊断编排器 — 四阶段检验 (§1.6.9, v1.3 修正).

    S1: 缺失机制诊断 (插补前) — 识别 MNAR/选择偏差
        输出: 分类标签 + mnar_risk_prior ∈ [0,1]
    S2: 原始因子内生性基线 (插补后/中性化前) — 建立 baseline
        输出: 连续 τ ∈ [0,1]
    S3: 截面内生性残留 (中性化后/解耦前, 可选) — 验证中性化有效性
        输出: 连续 τ ∈ [0,1]
    S4: 增量+时序内生性残留 (解耦后) — 验证解耦有效性, 输出最终 τ_i
        输出: 连续 τ ∈ [0,1]

    重要 (v1.3 修正):
    - S1 → S2 是上下文衔接 (非数值差分): S1 的 mnar_risk_prior 作为 S2 基线的解读上下文
    - S3 - S2, S4 - S3, S4 - S2 是数值差分 (连续 τ 之间)
    """

    def __init__(
        self,
        methods: List[str] = None,
        threat_threshold: float = 0.1,
        enable_s3: bool = False,
        enable_ife: bool = False,
        enable_lewbel: bool = False,
        r_max_multiplier: float = 1.3,
        ife_max_dim: int = 5,
    ):
        self.methods = methods or ['oster_delta', 'aet']
        self._missingness_checker = MissingnessMechanismChecker()
        self._oster = OsterDeltaChecker(
            threat_threshold=threat_threshold,
            r_max_multiplier=r_max_multiplier,
        )
        self._aet = AltonjiElderTaberChecker()
        self._ife = InteractiveFEChecker(max_dim=ife_max_dim) if enable_ife else None
        self._lewbel = LewbelInternalIVChecker() if enable_lewbel else None
        self._assessor = EndogeneityThreatAssessor()
        self._enable_s3 = enable_s3
        self._alert_threshold = threat_threshold

        self._s1_report: Optional[Dict] = None
        self._s2_report: Optional[Dict] = None
        self._s3_report: Optional[Dict] = None
        self._s4_report: Optional[Dict] = None
        self._final_assessment: Optional[Dict] = None

    def diagnose_s1_pre_imputation(
        self,
        raw_factor_with_missing: pd.DataFrame,
        returns: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """S1: 插补前 — 缺失机制诊断."""
        self._s1_report = self._missingness_checker.diagnose(
            raw_factor_with_missing, returns
        )
        return self._s1_report

    def diagnose_s2_post_imputation(
        self,
        imputed_factor: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """S2: 插补后/中性化前 — 原始因子内生性基线."""
        results = {}
        if 'oster_delta' in self.methods:
            self._oster.fit(imputed_factor, returns, controls)
            results['oster_delta'] = self._oster.get_diagnostics()
        if 'aet' in self.methods:
            self._aet.fit(imputed_factor, returns, controls)
            results['aet'] = self._aet.get_diagnostics()
        if self._ife is not None and 'ife' in self.methods:
            self._ife.fit(imputed_factor, returns, controls)
            results['ife'] = self._ife.get_diagnostics()
        if self._lewbel is not None and 'lewbel' in self.methods:
            self._lewbel.fit(imputed_factor, returns, controls)
            results['lewbel'] = self._lewbel.get_diagnostics()

        # S1 → S2 上下文衔接 (逻辑衔接, 非数值乘法): 传入完整 S1 报告,
        # assess() 用 S1 的 missingness_mechanism 标签逻辑指导推荐策略
        self._s2_report = self._assessor.assess(results, s1_context=self._s1_report)
        self._s2_report['checker_results'] = results
        return self._s2_report

    def diagnose_s3_post_neutralization(
        self,
        neutralized_factor: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """S3: 中性化后/解耦前 — 截面内生性残留 (可选)."""
        if not self._enable_s3:
            return None
        results = {}
        if 'oster_delta' in self.methods:
            self._oster.fit(neutralized_factor, returns, controls)
            results['oster_delta'] = self._oster.get_diagnostics()
        if self._ife is not None:
            self._ife.fit(neutralized_factor, returns, controls)
            results['ife'] = self._ife.get_diagnostics()

        self._s3_report = self._assessor.assess(results)
        self._s3_report['checker_results'] = results
        return self._s3_report

    def diagnose_s4_post_decoupling(
        self,
        decoupled_factor: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """S4: 解耦后 — 增量+时序内生性残留, 输出最终 τ_i."""
        results = {}
        if 'oster_delta' in self.methods:
            self._oster.fit(decoupled_factor, returns, controls)
            results['oster_delta'] = self._oster.get_diagnostics()
        if 'aet' in self.methods:
            self._aet.fit(decoupled_factor, returns, controls)
            results['aet'] = self._aet.get_diagnostics()
        if self._ife is not None:
            self._ife.fit(decoupled_factor, returns, controls)
            results['ife'] = self._ife.get_diagnostics()

        self._s4_report = self._assessor.assess(results)

        # 威胁轨迹分析 (S4 - S2 数值差分, v1.3: S1→S2 是上下文衔接非差分)
        s2_tau = self._s2_report.get('final_threat_tau', 0.0) if self._s2_report else 0.0
        s4_tau = self._s4_report['final_threat_tau']
        s3_tau = self._s3_report.get('final_threat_tau', 0.0) if self._s3_report else None

        trajectory = {
            's2_baseline_tau': float(s2_tau),
            's4_final_tau': float(s4_tau),
            's4_minus_s2': float(s4_tau - s2_tau),  # 整体预处理净效果 (数值差分)
            'interpretation': '',
            'critical_alert': False,
        }
        if s3_tau is not None:
            trajectory['s3_tau'] = float(s3_tau)
            trajectory['s3_minus_s2'] = float(s3_tau - s2_tau)
            trajectory['s4_minus_s3'] = float(s4_tau - s3_tau)
            # S4 - S3 > 0: 解耦引入增量内生性 (§2 隐藏效应 CRITICAL)
            if s4_tau > s3_tau:
                trajectory['critical_alert'] = True
                trajectory['interpretation'] = 'CRITICAL: 解耦引入增量内生性 (§2 隐藏效应)'

        # S4 - S2 > 0: 预处理整体无效
        if s4_tau > s2_tau:
            trajectory['critical_alert'] = True
            trajectory['interpretation'] = 'CRITICAL: 预处理整体无效, 内生性不降反升'

        self._s4_report['threat_trajectory'] = trajectory
        self._s4_report['checker_results'] = results
        self._final_assessment = self._s4_report
        return self._s4_report

    def get_final_threat_assessment(self) -> Optional[Dict[str, Any]]:
        """输出最终内生性威胁等级 tau_i (供 E5 正则化使用)."""
        return self._final_assessment
