"""Prompt templates for Stage 5: Axiom/Rule layer."""

# ============================================================
# Prompt 5.2-B: LLM-driven axiom generation
# ============================================================

AXIOM_GENERATION_PROMPT = """你是一个本体工程师。请根据以下业务描述，生成 OWL 公理。

业务背景：
{domain_description}

已确认的概念列表：
{concepts}

已确认的关系列表：
{relations}

任务：
1. 生成 subClassOf 公理
2. 生成 domain/range 公理
3. 生成 inverseOf 公理

输出格式（严格 JSON）：
每个公理是一个 JSON 对象，包含：
- "axiom_type": "subClassOf" | "domain" | "range" | "inverseOf"
- "subject": 主体名称
- "object": 客体名称
- "confidence": 0.0-1.0
- "rationale": "这条公理的业务理由"

输出示例：
{{
  "axioms": [
    {{"axiom_type": "subClassOf", "subject": "VIPCustomer", "object": "Customer", "confidence": 0.95, "rationale": "VIP客户是客户的子类"}},
    {{"axiom_type": "domain", "subject": "hasOrder", "object": "Customer", "confidence": 0.9, "rationale": "只有客户才能有订单"}}
  ]
}}

重要约束：
- 只使用"已确认的概念列表"和"已确认的关系列表"中的名称
- 不要生成 disjointWith 公理（需要人工确认）
- 不要生成 equivalentClass 公理（除非是同义标签）
- 置信度 < 0.7 的公理不要输出"""


# ============================================================
# NL2SWRL Step 1: Input preprocessing (decompose conditions/conclusion)
# ============================================================

SWRL_STEP1_PROMPT = """你是一个规则解析器。请把以下自然语言业务规则分解成"条件"和"结论"两部分。

规则：
{nl_rule}

输出格式（严格 JSON）：
{{
  "conditions": [
    {{"text": "条件原文", "type": "comparison|class_membership|relation"}}
  ],
  "conclusion": {{
    "text": "结论原文",
    "type": "class_assertion|property_assertion"
  }}
}}

示例：
规则："如果客户年消费额 > 10 万且合作年限 > 3 年，则是 VIP 客户"
输出：
{{
  "conditions": [
    {{"text": "客户年消费额 > 10 万", "type": "comparison"}},
    {{"text": "合作年限 > 3 年", "type": "comparison"}}
  ],
  "conclusion": {{"text": "是 VIP 客户", "type": "class_assertion"}}
}}"""


# ============================================================
# NL2SWRL Step 2: Ontology binding
# ============================================================

SWRL_STEP2_PROMPT = """你是一个本体绑定器。请把自然语言规则中的概念/属性名，映射到本体中已定义的概念/属性。

本体概念列表：
{concepts}

本体属性列表：
{properties}

待绑定词：
{terms}

输出格式（严格 JSON）：
{{
  "bindings": [
    {{"nl_term": "自然语言中的词", "ontology_term": "本体中的名称", "confidence": 0.0-1.0, "method": "exact_match|semantic|llm"}}
  ],
  "unbound": ["无法绑定的词"]
}}

重要：如果有无法绑定的词，不要猜测，列在"unbound"里，交给人工处理。"""


# ============================================================
# NL2SWRL Step 3: LLM generate SWRL (JSON atom format)
# ============================================================

SWRL_STEP3_PROMPT = """你是一个 SWRL 规则生成器。请根据以下输入，生成 SWRL 规则（JSON 格式）。

规则条件（已绑定）：
{conditions}

规则结论（已绑定）：
{conclusion}

可用本体元素：
- 概念: {concepts}
- 属性: {properties}

SWRL 内置函数列表（只使用以下函数）：
- greaterThan(?x, ?y)  # ?x > ?y
- lessThan(?x, ?y)     # ?x < ?y
- equal(?x, ?y)        # ?x = ?y
- notEqual(?x, ?y)     # ?x != ?y
- add(?z, ?x, ?y)      # ?z = ?x + ?y
- subtract(?z, ?x, ?y) # ?z = ?x - ?y

输出格式（严格 JSON）：
{{
  "rule_name": "规则名称",
  "description": "自然语言描述（验证用）",
  "body": [
    {{"atom_type": "class_atom", "predicate": "Customer", "variables": ["?x"]}},
    {{"atom_type": "property_atom", "predicate": "hasAnnualSpend", "variables": ["?x", "?y"]}},
    {{"atom_type": "builtin_atom", "predicate": "greaterThan", "variables": ["?y", "100000"]}}
  ],
  "head": [
    {{"atom_type": "class_atom", "predicate": "VIPCustomer", "variables": ["?x"]}}
  ],
  "issues": ["可能的问题（如果有）"]
}}"""


# ============================================================
# NL2SWRL Step 4: Error fix prompt
# ============================================================

SWRL_STEP4_PROMPT = """你生成的 SWRL 规则有以下错误，请修复：

原始规则（JSON）：
{rule_json}

错误信息：
{errors}

可用本体元素：
- 概念: {concepts}
- 属性: {properties}

请输出修复后的 JSON 格式规则（格式同原始规则）。"""
