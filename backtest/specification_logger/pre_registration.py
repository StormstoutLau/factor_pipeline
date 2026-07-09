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
        """提交事前承诺."""
        record = {
            'timestamp': datetime.now().isoformat(),
            'researcher': researcher,
            'description': description,
            'spec': spec,
        }
        commit_hash = hashlib.sha1(
            json.dumps(record, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()[:8]
        record['commit_hash'] = commit_hash

        with open(self.prereg_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + '\n')

        return commit_hash

    def verify_compliance(
        self,
        actual_config: Dict[str, Any],
        committed_hash: str,
    ) -> Dict[str, Any]:
        """验证实际运行是否与事前承诺一致."""
        committed = self._find_record(committed_hash)
        if committed is None:
            return {'is_compliant': False, 'deviations': ['commit_hash not found'],
                    'committed_spec': {}, 'actual_config': actual_config}

        committed_spec = committed.get('spec', {})
        deviations = []
        for key, committed_val in committed_spec.items():
            actual_val = actual_config.get(key)
            if actual_val != committed_val:
                deviations.append(f"{key}: committed={committed_val}, actual={actual_val}")

        return {
            'is_compliant': len(deviations) == 0,
            'deviations': deviations,
            'committed_spec': committed_spec,
            'actual_config': actual_config,
        }

    def _find_record(self, commit_hash: str) -> Optional[Dict]:
        if not os.path.exists(self.prereg_path):
            return None
        with open(self.prereg_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                    if rec.get('commit_hash') == commit_hash:
                        return rec
                except json.JSONDecodeError:
                    continue
        return None
