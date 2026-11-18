# -*- coding: utf-8 -*-
"""SpecificationLogger — 规格日志 (V3.1.0 E2, §3 L2 事中记录).

自动记录所有运行过的规格, 不可删除 (append-only JSONL).
防止选择性报告 (selective reporting). 类似 git log, 每次运行有 commit_hash.

学术依据:
- Simmons, J. P., Nelson, L. D., & Simonsohn, U. (2011). "False-Positive
  Psychology." Psychological Science 22(11):1359-1366.
- Simonsohn, U., Simmons, J. P., & Nelson, L. D. (2020). "Specification
  Curve Analysis." Nature Human Behaviour 4:1208-1214.
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

import numpy as np

logger = logging.getLogger(__name__)


class SpecificationLogger:
    """规格日志 — 自动记录所有运行过的规格, 不可删除 (§3 L2).

    防止选择性报告 (selective reporting). 类似 git log, 每次运行有 commit_hash, 可追溯.
    日志格式: append-only JSONL, 每行一条记录.
    """

    def __init__(self, log_dir: str = "logs/specifications/"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, "specifications.jsonl")
        if not os.path.exists(self.log_path):
            with open(self.log_path, 'w', encoding='utf-8') as f:
                pass

    def log_run(
        self,
        config: Dict[str, Any],
        result: Dict[str, Any],
        run_type: str = 'exploratory',
        factor_name: Optional[str] = None,
        *,
        spec_id: Optional[str] = None,
        values: Optional[Any] = None,
        value_type: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录一次运行 (append-only, 不可删除).

        Args:
            config: 运行配置 (滞后阶数、中性化变量、样本期等)
            result: 运行结果 (IC、p_value、显著数等)
            run_type: 'exploratory' / 'validation' / 'final'
            factor_name: 因子名 (可选, 用于按因子查询)
            spec_id: v3.7.0 v2 规格标识 (缺省时按 config 的 SHA256 生成)
            values: v2 逐期序列 (收益或 IC), 转 float 并拒绝 NaN/inf
            value_type: v2 必填, ``"returns"`` 或 ``"ic"``
            parent_run_id: v2 派生运行的上游 ``commit_hash``
            spec: v2 完整规格字典

        Returns:
            commit_hash: 8 字符 SHA1 前缀, 运行的唯一标识 (旧契约不变)

        Notes:
            任一 v2 参数非 None 时写入 ``schema_version="2"``; 纯旧调用
            的字段集合与旧版逐字段一致。
        """
        is_v2 = any(item is not None for item in (
            spec_id, values, value_type, parent_run_id, spec))
        if not is_v2:
            record = {
                'timestamp': datetime.now().isoformat(),
                'run_type': run_type,
                'factor_name': factor_name,
                'config': _make_json_serializable(config),
                'result': _make_json_serializable(result),
            }
            content_for_hash = {
                k: v for k, v in record.items() if k != 'timestamp'}
            commit_hash = hashlib.sha1(
                json.dumps(content_for_hash, sort_keys=True, default=str)
                .encode('utf-8')
            ).hexdigest()[:8]
            record['commit_hash'] = commit_hash

            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, default=str,
                                   ensure_ascii=False) + '\n')

            return commit_hash

        if value_type is None:
            raise ValueError("v2 记录必须提供 value_type")
        if value_type not in ('returns', 'ic'):
            raise ValueError(
                "value_type 必须是 'returns' 或 'ic'，收到 %r" % (value_type,))

        values_list = None
        if values is not None:
            arr = np.asarray(values, dtype=float)
            if arr.ndim != 1:
                raise ValueError("values 必须是一维序列")
            if not np.all(np.isfinite(arr)):
                raise ValueError("values 含 NaN 或 Inf")
            values_list = [float(v) for v in arr]

        config_s = _make_json_serializable(config)
        result_s = _make_json_serializable(result)
        spec_s = _make_json_serializable(spec)
        if spec_id is None:
            spec_id = hashlib.sha256(
                _canonical_json(config_s).encode('utf-8')).hexdigest()

        content = {
            'run_type': run_type,
            'factor_name': factor_name,
            'config': config_s,
            'result': result_s,
            'spec_id': spec_id,
            'values': values_list,
            'value_type': value_type,
            'parent_run_id': parent_run_id,
            'spec': spec_s,
        }
        content_hash = hashlib.sha256(
            _canonical_json(content).encode('utf-8')).hexdigest()

        record = {
            'timestamp': datetime.now().isoformat(),
            'run_type': run_type,
            'factor_name': factor_name,
            'config': config_s,
            'result': result_s,
            'schema_version': '2',
            'spec_id': spec_id,
            'value_type': value_type,
            'content_hash': content_hash,
            'parent_run_id': parent_run_id,
            'spec': spec_s,
        }
        if values_list is not None:
            record['values'] = values_list

        hash_payload = {k: v for k, v in record.items()
                        if k not in ('timestamp', 'content_hash')}
        commit_hash = hashlib.sha1(
            json.dumps(hash_payload, sort_keys=True, default=str)
            .encode('utf-8')
        ).hexdigest()[:8]
        record['commit_hash'] = commit_hash

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str,
                               ensure_ascii=False) + '\n')

        return commit_hash

    def get_specification_matrix(
        self,
        factor_name: Optional[str] = None,
        value_type: str = "returns",
        strict: bool = True,
    ) -> Dict[str, Any]:
        """提取 v2 逐期序列矩阵 (T x M).

        Args:
            factor_name: 按因子过滤
            value_type: ``"returns"`` 或 ``"ic"``
            strict: True 时长度不一致或缺少 ``values`` 立即报错；
                False 时取最短长度（截断尾部）并置 ``truncated=True``。

        Returns:
            spec_ids / values / records / n_periods / n_specs /
            value_type / truncated
        """
        if value_type not in ('returns', 'ic'):
            raise ValueError(
                "value_type 必须是 'returns' 或 'ic'，收到 %r" % (value_type,))

        entries = []  # (lineno, record)
        if os.path.exists(self.log_path):
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get('schema_version') != '2':
                        continue
                    if rec.get('value_type') != value_type:
                        continue
                    if (factor_name is not None
                            and rec.get('factor_name') != factor_name):
                        continue
                    entries.append((lineno, rec))

        empty = {
            'spec_ids': [],
            'values': np.empty((0, 0)),
            'records': [],
            'n_periods': 0,
            'n_specs': 0,
            'value_type': value_type,
            'truncated': False,
        }
        if not entries:
            return empty

        series = []
        kept = []
        kept_lines = []
        for lineno, rec in entries:
            raw = rec.get('values')
            if raw is None:
                if strict:
                    raise ValueError(
                        "第 %d 行 spec_id=%r 缺少 values"
                        % (lineno, rec.get('spec_id')))
                continue
            series.append(np.asarray(raw, dtype=float))
            kept.append(rec)
            kept_lines.append(lineno)

        if not series:
            return empty

        lengths = {int(s.size) for s in series}
        truncated = False
        if len(lengths) > 1:
            if strict:
                detail = ", ".join(
                    "第 %d 行 spec_id=%r T=%d"
                    % (line, rec.get('spec_id'), int(s.size))
                    for line, rec, s in zip(kept_lines, kept, series))
                raise ValueError("v2 序列长度不一致: %s" % detail)
            t_min = min(lengths)
            series = [s[-t_min:] for s in series]
            truncated = True

        n_periods = int(series[0].size)
        matrix = np.column_stack(series) if series else np.empty((0, 0))
        return {
            'spec_ids': [rec.get('spec_id') for rec in kept],
            'values': matrix,
            'records': kept,
            'n_periods': n_periods,
            'n_specs': len(kept),
            'value_type': value_type,
            'truncated': truncated,
        }

    def get_specification_curve(
        self,
        factor_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成 specification curve (Simonsohn et al. 2020)."""
        records = self._load_records(factor_name)
        if not records:
            return {'specifications': [], 'results': [], 'p_values': [],
                    'median_effect': float('nan'), 'consistency': 'undefined'}

        results = [r['result'].get('ic', float('nan')) for r in records]
        p_values = [r['result'].get('p_value', float('nan')) for r in records]

        valid_results = [r for r in results if not (isinstance(r, float) and np.isnan(r))]
        if not valid_results:
            consistency = 'undefined'
        else:
            pos_ratio = sum(1 for r in valid_results if r > 0) / len(valid_results)
            consistency = 'high' if pos_ratio > 0.8 or pos_ratio < 0.2 else (
                'medium' if pos_ratio > 0.6 or pos_ratio < 0.4 else 'low'
            )

        return {
            'specifications': records,
            'results': results,
            'p_values': p_values,
            'median_effect': float(np.nanmedian(results)) if results else float('nan'),
            'consistency': consistency,
        }

    def enforce_test_set_once(
        self,
        test_set_id: str,
        factor_name: str,
    ) -> Dict[str, Any]:
        """强制 test set 一次性原则 (§3 L1).

        检查该 test_set_id 是否已被该因子评估过.
        若已评估, 返回警告; 若首次评估, 记录.
        """
        records = self._load_records(factor_name)
        previous = [r for r in records
                    if r.get('config', {}).get('test_set_id') == test_set_id
                    and r.get('run_type') == 'final']

        if previous:
            return {
                'is_first_evaluation': False,
                'warning': f'test_set {test_set_id} 已被因子 {factor_name} 评估过 '
                           f'{len(previous)} 次 (P-hacking 风险)',
                'previous_runs': [r.get('commit_hash', '') for r in previous],
            }
        return {
            'is_first_evaluation': True,
            'warning': '',
            'previous_runs': [],
        }

    def _load_records(self, factor_name: Optional[str] = None) -> List[Dict]:
        """加载所有记录 (可选按因子过滤)."""
        records = []
        if not os.path.exists(self.log_path):
            return records
        with open(self.log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if factor_name is None or rec.get('factor_name') == factor_name:
                        records.append(rec)
                except json.JSONDecodeError:
                    continue
        return records


def _canonical_json(obj: Any) -> str:
    """稳定 JSON 表示（键排序、紧凑分隔符），用于内容哈希。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _make_json_serializable(obj: Any) -> Any:
    """将对象转换为 JSON 可序列化格式."""
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (datetime,)):
        return obj.isoformat()
    else:
        return obj
