"""Prompt templates for Stage 7: Process & Permission."""

OPERATION_EXTRACTION_PROMPT = """# 任务
你是一个业务流程分析师。请从以下文本中抽取原子业务操作。

# 已知概念
{concepts}

# 文本
{text}

# 重要规则
1. 原子操作是不可再分的最小业务动作
2. 每个操作需要明确：执行者、操作对象、输入、输出、前置条件、后置条件
3. 只提取文本中明确描述的操作

# 输出格式（严格 JSON）
{{"operations": [{{"name": "操作名称", "description": "操作描述", "actor": "执行者概念", "target": "操作对象概念", "inputs": [{{"name": "参数名", "type": "类型", "required": true}}], "outputs": [{{"name": "输出名", "type": "类型"}}], "preconditions": ["前置条件1"], "postconditions": ["后置条件1"]}}]}}
"""

SERVICE_COMPOSITION_PROMPT = """# 任务
你是一个服务编排专家。请将以下原子操作组合成业务流程（服务链）。

# 可用操作
{operations}

# 文本描述
{text}

# 输出格式（严格 JSON）
{{"compositions": [{{"name": "流程名称", "description": "流程描述", "type": "sequential|parallel|conditional|exception_handling", "steps": [{{"operation_name": "操作名", "order": 1, "condition": "条件(如有)"}}], "exception_handlers": [{{"trigger": "异常触发条件", "action": "处理操作名"}}]}}]}}
"""

PERMISSION_EXTRACTION_PROMPT = """# 任务
你是一个权限管理专家。请从以下文本中抽取权限控制规则。

# 已知概念
{concepts}

# 文本
{text}

# 重要规则
1. 识别角色/用户组（权限主体）
2. 识别被管控的数据对象
3. 识别允许/禁止的操作类型
4. 识别特殊条件和约束

# 输出格式（严格 JSON）
{{"subjects": [{{"name": "角色名", "type": "role|user_group|system", "parent": "父角色(如有)"}}], "rules": [{{"name": "规则名", "description": "规则描述", "subject": "角色名", "object": "管控对象概念", "scope": "all|own", "actions": ["read", "write"], "effect": "allow|deny", "condition": "附加条件(如有)"}}]}}
"""
