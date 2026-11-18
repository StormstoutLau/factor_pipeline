# -*- coding: utf-8 -*-
"""PreRegistration — 事前规格承诺 (V3.1.0 E2, §3 L1 事前设计).

在看到数据前, 书面承诺模型规格 (滞后阶数、中性化变量、样本期).
承诺一旦写入不可修改 (append-only, 与 SpecificationLogger 同机制).

学术依据:
- Nosek, B. A., Ebersole, C. R., DeHaven, A. C., & Mellor, D. T. (2018).
  "The preregistration revolution." PNAS 115(11):2600-2606.
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional


class PreRegistration:
    """事前规格承诺 (§3 L1).

    在看到数据前, 书面承诺模型规格 (滞后阶数、中性化变量、样本期).
    承诺一旦写入不可修改 (append-only, 与 SpecificationLogger 同机制).
    """

    def __init__(self, log_dir: str = "logs/specifications/"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.prereg_path = os.path.join(log_dir, "preregistration.jsonl")

    def commit(
        self,
        spec: Dict[str, Any],
        researcher: str = "anonymous",
        description: str = "",
    ) -> str:
        """提交事前承诺.

        返回 8 位 ``commit_hash``（旧契约）；同时写入 timestamp 不参与的
        64 位 ``content_hash``（SHA256）与 ``hash_algo="sha256"``。
        """
        record = {
            'timestamp': datetime.now().isoformat(),
            'researcher': researcher,
            'description': description,
            'spec': spec,
        }
        commit_hash = hashlib.sha1(
            json.dumps(record, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()[:8]
        content_hash = hashlib.sha256(
            json.dumps(
                {'researcher': researcher,
                 'description': description,
                 'spec': spec},
                sort_keys=True, separators=(",", ":"), default=str,
            ).encode('utf-8')
        ).hexdigest()
        record['commit_hash'] = commit_hash
        record['content_hash'] = content_hash
        record['hash_algo'] = 'sha256'

        with open(self.prereg_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + '\n')

        return commit_hash

    def verify_compliance(
        self,
        actual_config: Dict[str, Any],
        committed_hash: str,
        *,
        strict_extra: bool = False,
        run_at: Optional[str] = None,
        constraints: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """验证实际运行是否与事前承诺一致.

        Args:
            actual_config: 实际运行配置
            committed_hash: 64 位 ``content_hash`` 或 8 位 ``commit_hash``
            strict_extra: 实际配置出现承诺外的键 → 记为偏差
            run_at: 实际运行时间；早于事前提案时间 → 记为偏差
            constraints: ``{key: op}``，校验 actual 相对 committed 的方向，
                op ∈ {">", ">=", "<", "<=", "==", "!="}
        """
        committed, matched_by = self._match_record(committed_hash)
        if committed is None:
            return {
                'is_compliant': False,
                'deviations': ['commit_hash not found'],
                'committed_spec': {},
                'actual_config': actual_config,
                'matched_by': None,
                'committed_at': None,
            }

        committed_spec = committed.get('spec', {})
        deviations = []
        for key, committed_val in committed_spec.items():
            actual_val = actual_config.get(key)
            if actual_val != committed_val:
                deviations.append(
                    f"{key}: committed={committed_val}, actual={actual_val}")

        if strict_extra:
            for key in actual_config:
                if key not in committed_spec:
                    deviations.append(
                        f"{key}: extra key not in committed spec")

        if run_at is not None:
            committed_at = committed.get('timestamp')
            if committed_at and _parse_dt(run_at) < _parse_dt(committed_at):
                deviations.append("run_before_commit")

        if constraints:
            for key, op in constraints.items():
                if op not in _CONSTRAINT_OPS:
                    raise ValueError("不支持的约束运算符: %r" % (op,))
                actual_val = actual_config.get(key)
                committed_val = committed_spec.get(key)
                if not _check_constraint(actual_val, committed_val, op):
                    deviations.append(
                        f"{key}: constraint {op} failed "
                        f"(committed={committed_val}, actual={actual_val})")

        return {
            'is_compliant': len(deviations) == 0,
            'deviations': deviations,
            'committed_spec': committed_spec,
            'actual_config': actual_config,
            'matched_by': matched_by,
            'committed_at': committed.get('timestamp'),
        }

    def _match_record(self, committed_hash: str):
        """按 content_hash 精确匹配，再回退 commit_hash。"""
        if not os.path.exists(self.prereg_path):
            return None, None
        with open(self.prereg_path, 'r', encoding='utf-8') as f:
            records = []
            for line in f:
                try:
                    records.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        for rec in records:
            if rec.get('content_hash') == committed_hash:
                return rec, 'content_hash'
        for rec in records:
            if rec.get('commit_hash') == committed_hash:
                return rec, 'commit_hash'
        return None, None

    def _find_record(self, commit_hash: str) -> Optional[Dict]:
        record, _ = self._match_record(commit_hash)
        return record


_CONSTRAINT_OPS = (">", ">=", "<", "<=", "==", "!=")


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _check_constraint(actual: Any, committed: Any, op: str) -> bool:
    if actual is None or committed is None:
        return False
    try:
        if op == ">":
            return actual > committed
        if op == ">=":
            return actual >= committed
        if op == "<":
            return actual < committed
        if op == "<=":
            return actual <= committed
        if op == "==":
            return actual == committed
        return actual != committed
    except TypeError:
        return False
