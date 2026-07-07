"""Prompt templates for Stage 2: Concept Extraction."""

# ============================================================
# Prompt 2.1: RDB path concept extraction
# ============================================================

RDB_CONCEPT_EXTRACTION_PROMPT = """# 任务
你是一位知识图谱本体工程师。给定一张数据库表的 DDL（已补全注释），
请抽取出候选的实体类型和属性。

# 重要规则
- 表名 -> 候选实体类型（如果表代表一个业务对象）
- 外键字段 -> 候选关系（同时产生一个新实体类型）
- 枚举类型字段（如 status 取值为 ["active","inactive"]） -> 候选枚举类型
- 普通字段 -> 候选属性（归属到最相关的实体类型）

# 输入
表名：{table_name}
注释：{table_comment}
字段：
{columns}

# 输出格式（严格 JSON）
{{
  "entity_types": [
    {{"name": "Patient", "source": "table:patient_record", "evidence": "表名patient_record + 外键patient_id"}},
    {{"name": "Doctor", "source": "field:doctor_id", "evidence": "外键doctor_id指向doctor表"}}
  ],
  "properties": [
    {{"name": "age", "domain": "Patient", "range": "int", "evidence": "字段age，注释：年龄"}},
    {{"name": "diagnosis_code", "domain": "Patient", "range": "string"}}
  ]
}}"""


# ============================================================
# Prompt 2.2: Text path concept extraction (with anti-hallucination rules)
# ============================================================

TEXT_CONCEPT_EXTRACTION_PROMPT = """# 任务
从以下文本中抽取领域概念（名词性短语，表示实体类型、类别或属性）。

# anti-hallucination 约束（必须严格遵守）
1. 只抽取文本中直接出现的短语（字符级匹配）
2. 不要根据上下文推理出文本中没有出现的概念
3. 不要抽取过于通用的词（如"系统"、"方法"、"数据"、"信息"）
4. 不要把属性值当成概念（如"高血压"是疾病名，不是属性值）
5. 每个概念必须附带原文 span（起止字符位置）

# 输入文本
{text}

# 输出格式（严格 JSON）
{{
  "concepts": [
    {{"text": "高血压", "type": "疾病", "span": [0, 3], "count": 1}},
    {{"text": "糖尿病", "type": "疾病", "span": [7, 10], "count": 1}},
    {{"text": "ACE抑制剂", "type": "药物类别", "span": [30, 36], "count": 1}}
  ]
}}

# 注意
- 如果文本中没有出现某个预期概念，不要捏造
- 输出前做 self-check：这个概念是不是根据上下文推理出来的？如果是，删除它"""


# ============================================================
# LLM judge prompt for concept merge Step 4
# ============================================================

CONCEPT_MERGE_LLM_PROMPT = """# 任务：判断两个词在指定业务领域中是否指同一概念
领域：{domain}
词 A：{concept_a}
词 B：{concept_b}

请只回答"是"或"否"，然后附带一句解释。

# 输出格式（严格 JSON）
{{
  "same_concept": true,
  "explanation": "两者都指..."
}}"""
