"""Prompt templates for Stage 6: Semantic Enrichment."""

GLOSSARY_EXTRACTION_PROMPT = """# 任务
你是一个业务术语管理专家。请根据以下业务文档和已有概念列表，提取标准业务术语。

# 已有概念
{concepts}

# 文档内容
{text}

# 输出格式（严格 JSON）
{{"terms": [{{"standard_term": "标准术语", "aliases": ["别名1", "别名2"], "definition": "术语定义", "category": "所属分类"}}]}}
"""

ANNOTATION_EXTRACTION_PROMPT = """# 任务
你是一个数据治理专家。请为以下本体元素提取业务语义注释（业务上下文说明、数据血缘提示、使用注意事项等）。

# 本体元素
{elements}

# 文档上下文
{text}

# 输出格式（严格 JSON）
{{"annotations": [{{"target_name": "元素名称", "target_type": "concept|property|relation", "key": "business_context|usage_note|data_lineage", "value": "注释内容"}}]}}
"""

TRIGGER_RULE_EXTRACTION_PROMPT = """# 任务
你是一个业务规则分析师。请从以下文本中抽取事件-条件-动作（ECA）触发规则。

# 已知概念
{concepts}

# 文本
{text}

# 重要规则
1. 每条触发规则必须包含：触发事件、触发条件、执行动作
2. 事件类型分为：data_change（数据变更）、time_based（定时/超时）、status_transition（状态迁移）、external_event（外部事件）
3. 只提取文本中明确描述的规则，不要推测

# 输出格式（严格 JSON）
{{"trigger_rules": [{{"name": "规则名称", "description": "规则描述", "event_type": "data_change|time_based|status_transition|external_event", "event_source": "触发源概念", "event_detail": "事件详情", "condition": "触发条件表达式", "action_type": "update_field|create_instance|notify|invoke_service", "action_detail": "动作详情"}}]}}
"""

EXTERNAL_MAPPING_PROMPT = """# 任务
你是一个系统集成专家。请从以下文本中识别跨系统术语映射关系。

# 内部术语
{terms}

# 文本
{text}

# 输出格式（严格 JSON）
{{"mappings": [{{"internal_term": "内部术语", "external_system": "外部系统名", "external_term": "外部术语", "external_code": "外部编码(如有)", "mapping_type": "equivalent|broader|narrower|related"}}]}}
"""
