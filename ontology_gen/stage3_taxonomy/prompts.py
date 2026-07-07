"""Prompt templates for Stage 3: Taxonomy construction."""

# ============================================================
# Prompt 3.1: LLM taxonomy induction (is-a relation)
# ============================================================

TAXONOMY_INDUCTION_PROMPT = """# 任务
给定一组候选概念，判断它们之间是否存在 "is-a" 关系（泛化-特化关系）。

# 重要约束
- 只判断"直接上下位"（如"智能手机"是"手机"的子类，但不是"电子产品"的直接子类）
- 如果不确定，输出 "UNSURE"，不要猜测
- 每个判断必须附带理由（1-2 句话）

# 输入
候选概念列表：
{concepts}

# 输出格式（严格 JSON）
{{
  "taxonomy": [
    {{"parent": "客户", "child": "VIP客户", "confidence": "high", "reason": "VIP客户是客户的子类，有特定义务属性"}},
    {{"parent": "客户", "child": "企业客户", "confidence": "high", "reason": "企业客户是法人的客户"}}
  ],
  "unsure": [
    {{"pair": "订单-产品", "note": "订单包含产品，但订单不是产品的子类（这是part-of关系，不是is-a关系）"}}
  ]
}}"""


# ============================================================
# Prompt 3.2: Relation type classification
# ============================================================

RELATION_TYPE_PROMPT = """# 任务：判断一对概念之间的关系类型
概念 A：{concept_a}  概念 B：{concept_b}

请选择最准确的关系类型：
1. "is-a"（A的实例也是B的实例）
2. "part-of"（A包含B，或B包含A）
3. "attribute-of"（A是B的属性值）
4. "related-to"（A和B相关，但不是以上三种）

# 输出格式（严格 JSON）
{{
  "relation_type": "is-a",
  "direction": "A_to_B",
  "reason": "A的实例也是B的实例，所以A是B的子类"
}}"""
