"""Prompt templates for Stage 4: Relation/Property construction."""

# ============================================================
# Prompt 4.1: Relation triple extraction (with property vs relation rules)
# ============================================================

RELATION_EXTRACTION_PROMPT = """# 任务
从以下文本中抽取关系三元组（主语-关系-宾语）和属性。

# 重要规则
1. 宾语是字面量（数字/日期/短字符串，长度<50字符）-> 用属性表示
2. 宾语是另一个实体 -> 用关系表示
3. 关系的domain和range必须从已确认的概念列表中选择
4. 不要凭空捏造关系类型——只抽取文本中明确表达的

# 已确认的概念列表
{concepts}

# 输入文本
{text}

# 输出格式（严格 JSON）
{{
  "relations": [
    {{"subject": "张三", "predicate": "hasDisease", "object": "高血压", "domain": "患者", "range": "疾病"}},
    {{"subject": "张三", "predicate": "hasDoctor", "object": "李四", "domain": "患者", "range": "医生"}}
  ],
  "properties": [
    {{"subject": "张三", "property": "age", "value": 45, "value_type": "int"}}
  ]
}}

# 附加约束
- 请按 [主体类型]-[关系]->[客体类型] 格式输出，并明确标注domain和range
- 关系方向必须以"主体"为中心：如"患者的医生"->hasDoctor（主体=患者）
- 生成后做self-check：domain和range类型是否合理？不合理则重新生成"""
