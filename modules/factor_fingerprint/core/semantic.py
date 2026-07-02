# -*- coding: utf-8 -*-
"""
因子构造语义理解模块

从因子构造规则的自然语言描述中，提取结构化信息。
支持分层架构：分词 → 语义角色 → 知识图谱 → 语义匹配
"""

import re
import jieba
import jieba.posseg as pseg
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class Token:
    """分词结果"""
    text: str
    pos: str
    offset: int
    entity_type: str = None


@dataclass
class FactorMeta:
    """因子构造元数据（先验知识）"""
    name: str
    category: Optional[str] = None
    is_price_based: bool = False
    is_financial_report: bool = False
    is_analyst_data: bool = False
    lookback_window: Optional[float] = None
    rebalance_freq: str = 'monthly'
    known_issues: List[str] = field(default_factory=list)
    typical_stability: Optional[str] = None
    literature_support: bool = False


@dataclass
class ExtractedRule:
    """提取的规则"""
    category: Optional[str] = None
    category_confidence: float = 0.0
    is_price_based: bool = False
    is_financial_report: bool = False
    is_analyst_data: bool = False
    lookback_windows: List[Tuple[float, str]] = field(default_factory=list)
    rebalance_freq: str = 'monthly'
    operators: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    semantic_roles: Dict[str, List[str]] = field(default_factory=dict)
    knowledge_graph_matches: List[Dict] = field(default_factory=list)
    overall_confidence: float = 0.0
    inferred_factor_type: Optional[str] = None  # 'static' | 'dynamic' | 'mixed'


# =============================================================================
# Layer 1: 金融增强分词器
# =============================================================================

class FinancialTokenizer:
    """金融增强分词器"""

    def __init__(self):
        self._init_financial_dict()
        self.pos_mapping = {
            'nz': '金融术语', 'n': '名词', 'v': '动词',
            'm': '数量词', 'q': '量词', 't': '时间词',
            'f': '方位词', 'r': '代词', 'd': '副词',
            'p': '介词', 'c': '连词', 'u': '助词',
        }

    def _init_financial_dict(self):
        """初始化金融词典"""
        financial_terms = [
            '市盈率', '市净率', '市销率', 'ROE', 'ROA', 'ROIC',
            '毛利率', '净利率', '资产负债率', '换手率', '波动率',
            '动量因子', '反转因子', '价值因子', '质量因子', '成长因子',
            '一致预期', '分析师预期', 'TTM', '扣除非经常性损益',
            '过去N个月', '最近N个月', '累积收益率', '行业中性化',
            '市值因子', '规模因子', '流动性因子', '情绪因子',
            '短期反转', '长期动量', '账面市值比', '盈利收益率',
            '净资产收益率', '总资产收益率', '营业收入增长率',
            '净利润增长率', '营业利润率', '成本费用利润率',
            '每股收益', '每股净资产', '每股现金流',
            '股息率', '分红率', '派息率',
            '贝塔系数', '阿尔法', '夏普比率', '信息比率',
            '最大回撤', '波动率', '下行风险', '尾部风险',
        ]
        for term in financial_terms:
            jieba.add_word(term, freq=10000, tag='nz')

    def tokenize(self, text: str) -> List[Token]:
        """分词"""
        tokens = []
        offset = 0
        for word, pos in pseg.cut(text):
            token = Token(
                text=word, pos=pos, offset=offset,
                entity_type=self.pos_mapping.get(pos, '其他')
            )
            tokens.append(token)
            offset += len(word)
        return tokens

    def extract_numbers_with_unit(self, text: str) -> List[Tuple[float, str]]:
        """提取数字+单位"""
        pattern = r'(\d+(?:\.\d+)?)\s*([日周月年个]*)'
        matches = re.findall(pattern, text)
        return [(float(num), unit) for num, unit in matches if unit]


# =============================================================================
# Layer 2: 语义角色标注器
# =============================================================================

class SemanticRoleLabeler:
    """语义角色标注器"""

    RELATION_PATTERNS = {
        '时间范围': r'(过去|最近|历史上|当期|本期)',
        '操作类型': r'(除以?|比值?|乘以?|加|减|取|计算|构建|定义|使用)',
        '数据来源': r'(使用?|基于?|采用?|取|用)',
        '比较对象': r'(与|和|比|相对|相比)',
        '排序方式': r'(排名?|分位数|百分位|倒序|正序)',
        '修饰关系': r'(的|之|得|地)',
        '否定关系': r'(不|无|非|未|否)',
    }

    def extract_semantic_roles(self, text: str) -> Dict[str, List[str]]:
        """提取语义角色"""
        roles = {}
        for role_name, pattern in self.RELATION_PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                roles[role_name] = list(set(matches))
        return roles


# =============================================================================
# Layer 3: 金融知识图谱
# =============================================================================

@dataclass
class FinancialEntity:
    """金融实体"""
    name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    properties: Dict = field(default_factory=dict)
    category_hint: str = None


class FinancialKnowledgeGraph:
    """金融知识图谱"""

    def __init__(self):
        self.entities = {}
        self._build_core_graph()

    def _build_core_graph(self):
        """构建核心知识图谱"""
        factor_entities = [
            FinancialEntity('动量因子', 'factor', ['momentum', '动量', '收益率动量'],
                          category_hint='momentum', properties={'typical_stability': 'mixed'}),
            FinancialEntity('反转因子', 'factor', ['reversal', '反转', '短期反转', '均值回归'],
                          category_hint='reversal', properties={'typical_stability': 'dynamic'}),
            FinancialEntity('价值因子', 'factor', ['value', '价值', '估值', '低估'],
                          category_hint='value', properties={'typical_stability': 'static'}),
            FinancialEntity('质量因子', 'factor', ['quality', '质量', '盈利质量', '财务质量'],
                          category_hint='quality', properties={'typical_stability': 'static'}),
            FinancialEntity('成长因子', 'factor', ['growth', '成长', '增长', '成长性'],
                          category_hint='growth', properties={'typical_stability': 'mixed'}),
            FinancialEntity('市值因子', 'factor', ['size', '市值', '规模', '小市值'],
                          category_hint='size', properties={'typical_stability': 'static'}),
            FinancialEntity('流动性因子', 'factor', ['liquidity', '流动性', '换手率', '成交量'],
                          category_hint='liquidity', properties={'typical_stability': 'dynamic'}),
            FinancialEntity('情绪因子', 'factor', ['sentiment', '情绪', '投资者情绪', '市场情绪'],
                          category_hint='sentiment', properties={'typical_stability': 'dynamic'}),
        ]

        metric_entities = [
            FinancialEntity('PE', 'metric', ['市盈率', 'price_to_earning', 'P/E'],
                          category_hint='value'),
            FinancialEntity('PB', 'metric', ['市净率', 'price_to_book', 'P/B'],
                          category_hint='value'),
            FinancialEntity('PS', 'metric', ['市销率', 'price_to_sales', 'P/S'],
                          category_hint='value'),
            FinancialEntity('ROE', 'metric', ['净资产收益率', 'return_on_equity'],
                          category_hint='quality'),
            FinancialEntity('ROA', 'metric', ['资产收益率', 'return_on_assets'],
                          category_hint='quality'),
            FinancialEntity('毛利率', 'metric', ['gross_margin', '销售毛利率'],
                          category_hint='quality'),
            FinancialEntity('净利率', 'metric', ['net_margin', '净利润率', '销售净利率'],
                          category_hint='quality'),
            FinancialEntity('换手率', 'metric', ['turnover', 'turnover_rate'],
                          category_hint='liquidity'),
            FinancialEntity('市值', 'metric', ['market_cap', 'market_value', '总市值'],
                          category_hint='size'),
        ]

        operator_entities = [
            FinancialEntity('除以', 'operator', ['比值', '比率', '/', 'divide', '除']),
            FinancialEntity('对数', 'operator', ['log', 'ln', '取对数', 'log变换']),
            FinancialEntity('累积', 'operator', ['累计', 'cumsum', 'cum', '求和']),
            FinancialEntity('排名', 'operator', ['排序', 'rank', 'percentile', '分位数']),
            FinancialEntity('相反数', 'operator', ['负号', '取反', 'negative']),
            FinancialEntity('差分', 'operator', ['diff', '变化', '变动', 'delta']),
            FinancialEntity('均值', 'operator', ['平均', 'mean', 'avg', 'average']),
            FinancialEntity('标准差', 'operator', ['std', '波动', 'volatility']),
        ]

        for entity in factor_entities + metric_entities + operator_entities:
            self.entities[entity.name] = entity

    def disambiguate(self, text: str, candidates: List[str]) -> Optional[str]:
        """语义消歧"""
        text_lower = text.lower()
        best_match = None
        best_score = 0

        for candidate in candidates:
            if candidate not in self.entities:
                continue

            entity = self.entities[candidate]
            score = 0

            if entity.name in text:
                score += 10
            for alias in entity.aliases:
                if alias.lower() in text_lower:
                    score += 5

            if score > best_score:
                best_score = score
                best_match = candidate

        return best_match

    def get_category_hint(self, entity_name: str) -> Optional[str]:
        """获取类别提示"""
        if entity_name in self.entities:
            return self.entities[entity_name].category_hint
        return None


# =============================================================================
# Layer 4: 语义相似度匹配器
# =============================================================================

class SemanticMatcher:
    """语义相似度匹配器"""

    FACTOR_TEMPLATES = {
        '动量因子': {
            'patterns': ['过去N个月收益率', '累计收益率', '动量效应', '价格动量', '收益动量'],
            'category': 'momentum', 'typical_stability': 'mixed'
        },
        '反转因子': {
            'patterns': ['短期反转', '收益率相反数', 'reversal', '均值回归', '价格反转'],
            'category': 'reversal', 'typical_stability': 'dynamic'
        },
        '价值因子': {
            'patterns': ['市盈率', '市净率', '估值', '低估值', '账面市值比'],
            'category': 'value', 'typical_stability': 'static'
        },
        '质量因子': {
            'patterns': ['ROE', 'ROA', '盈利质量', '财务质量', '盈利能力'],
            'category': 'quality', 'typical_stability': 'static'
        },
        '成长因子': {
            'patterns': ['增长率', '营收增长', '利润增长', '成长性', '增长潜力'],
            'category': 'growth', 'typical_stability': 'mixed'
        },
        '流动性因子': {
            'patterns': ['换手率', '成交量', '流动性', '交易活跃度', 'Amihud'],
            'category': 'liquidity', 'typical_stability': 'dynamic'
        },
    }

    def match(self, text: str, top_k: int = 3) -> List[Dict]:
        """关键词匹配"""
        results = []

        for template_name, template in self.FACTOR_TEMPLATES.items():
            max_similarity = 0
            matched_pattern = None

            for pattern in template['patterns']:
                if pattern in text:
                    max_similarity = 1.0
                    matched_pattern = pattern
                    break
                for word in pattern:
                    if word in text and len(word) > 1:
                        max_similarity = max(max_similarity, 0.5)
                        if not matched_pattern:
                            matched_pattern = pattern

            if max_similarity > 0:
                results.append({
                    'template': template_name,
                    'matched_pattern': matched_pattern,
                    'similarity': max_similarity,
                    'category': template['category'],
                    'typical_stability': template['typical_stability']
                })

        return sorted(results, key=lambda x: x['similarity'], reverse=True)[:top_k]


# =============================================================================
# 完整语义理解系统
# =============================================================================

class FactorSemanticUnderstanding:
    """因子构造语义理解系统"""

    def __init__(self):
        self.tokenizer = FinancialTokenizer()
        self.srl = SemanticRoleLabeler()
        self.kg = FinancialKnowledgeGraph()
        self.matcher = SemanticMatcher()

    def understand(self, text: str) -> ExtractedRule:
        """完整语义理解"""
        rule = ExtractedRule()

        # Layer 1: 分词和基础规则
        tokens = self.tokenizer.tokenize(text)
        numbers = self.tokenizer.extract_numbers_with_unit(text)
        rule.lookback_windows = numbers

        # Layer 2: 语义角色
        rule.semantic_roles = self.srl.extract_semantic_roles(text)

        # Layer 3: 知识图谱消歧
        candidates = self._extract_candidates(tokens)
        for candidate in candidates:
            match = self.kg.disambiguate(text, [candidate])
            if match:
                entity = self.kg.entities[match]
                if entity.entity_type == 'factor':
                    rule.category = entity.category_hint
                elif entity.entity_type == 'metric':
                    rule.data_sources.append(entity.name)
                    if not rule.category:
                        rule.category = entity.category_hint

        # Layer 4: 语义相似度匹配
        rule.knowledge_graph_matches = self.matcher.match(text)

        # 综合决策
        rule = self._make_decision(rule)

        return rule

    def _extract_candidates(self, tokens: List[Token]) -> List[str]:
        """提取候选实体"""
        return [t.text for t in tokens if t.entity_type in ['金融术语', '名词']]

    def _make_decision(self, rule: ExtractedRule) -> ExtractedRule:
        """综合决策"""
        # 优先级: 知识图谱 > 语义匹配 > 基础规则
        if rule.category:
            rule.category_confidence = 0.8
        elif rule.knowledge_graph_matches:
            best_match = rule.knowledge_graph_matches[0]
            rule.category = best_match['category']
            rule.category_confidence = best_match['similarity'] * 0.7

        # 推断数据来源
        if any(k in rule.data_sources for k in ['PE', 'PB', 'PS', 'ROE', 'ROA']):
            rule.is_financial_report = True
        if any(k in rule.data_sources for k in ['市值', '价格', '收益率']):
            rule.is_price_based = True

        # 推断因子类型（基于 typical_stability）
        if rule.knowledge_graph_matches:
            best_match = rule.knowledge_graph_matches[0]
            rule.inferred_factor_type = best_match.get('typical_stability')
        
        # 计算总体置信度
        score = rule.category_confidence * 0.4
        score += (0.2 if rule.lookback_windows else 0)
        score += (0.2 if rule.data_sources else 0)
        score += (0.2 if rule.semantic_roles else 0)
        rule.overall_confidence = min(score, 1.0)

        return rule


# =============================================================================
# 便捷函数
# =============================================================================

def extract_from_text(text: str) -> ExtractedRule:
    """从文本提取规则（便捷函数）"""
    system = FactorSemanticUnderstanding()
    return system.understand(text)


def extract_to_meta(text: str, name: str = "Unknown") -> FactorMeta:
    """提取并转换为FactorMeta"""
    rule = extract_from_text(text)
    return FactorMeta(
        name=name,
        category=rule.category,
        is_price_based=rule.is_price_based,
        is_financial_report=rule.is_financial_report,
        is_analyst_data=rule.is_analyst_data,
        lookback_window=rule.lookback_windows[0][0] if rule.lookback_windows else None,
        rebalance_freq=rule.rebalance_freq,
    )
