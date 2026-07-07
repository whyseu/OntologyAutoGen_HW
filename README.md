# Ontology Auto-Generation Pipeline

从异构数据源（RDB DDL、文本文档、对话日志）自动构建领域本体的 Python 项目。

原版作者：https://liuhuanyong.github.io
修改版作者：whyseu

## 架构概览

```
数据源 (DDL/Text/Query)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: 数据准备                                            │
│  质量评分 → DDL解析 → 文档解析 → 查询日志加载 → 空值过滤         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: 概念抽取                                            │
│  RDB路径抽取 + 文本路径抽取 → 四步概念合并 → 粒度决策            │
│  → 层次分类(data/logic/application) → 身份标识抽取              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: 概念层次构建                                        │
│  Hearst Pattern + LLM归纳 → 关系类型区分 → 环检测消环          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: 关系/属性构建                                       │
│  三元组抽取 → 属性vs关系决策 → 外键过滤 → M:N再化 → 归一化      │
│  → 派生属性抽取 → 验证规则抽取                                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 5: 公理/规则层                                         │
│  domain/range推断 → LLM公理生成 → NL2SWRL → 风险分级            │
│  → 一致性检查                                                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 6: 语义丰富化（可选）                                    │
│  术语表构建 → 外部映射 → 语义注解 → 触发器规则 → 治理规则        │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 7: 流程与权限（可选）                                    │
│  原子操作抽取 → 服务编排 → 权限主体/规则抽取 → 查询模式分析      │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
                   Ontology JSON 输出
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Reasoning: 本体推理引擎                                       │
│  符号推理（子类闭包/关系继承/路径/约束/派生/ECA/分类）           │
│  本体→LLM 上下文序列化  →  有本体 vs 无本体 推理效果对比         │
└─────────────────────────────────────────────────────────────┘
```
## 测试效果
bare_llm      : accuracy=0.283  completeness=0.285  hallucination=0.899  avg_latency=3158ms\n
ontology_llm  : accuracy=0.431  completeness=0.417  hallucination=0.458  avg_latency=2150ms\n
symbolic      : accuracy=0.267  completeness=0.262  hallucination=0.785  avg_latency=0ms\n

## 快速开始

### 1. 安装依赖

```bash
cd OntologyAutoGen
pip install -r requirements.txt
```

### 2. 配置 LLM（可选）

```bash
cp .env.example .env
# 编辑 .env，填入你的 API key
```

> **降级模式**：如果不配置 LLM API key，管线仍可运行，但所有 LLM 驱动的步骤（概念增强抽取、LLM公理生成、NL2SWRL）将返回空结果或使用规则 fallback。Embedding 也会降级到 hash 向量。

### 3. 运行完整管线

```bash
# 使用示例电商数据运行
python scripts/run_full_pipeline.py

# 指定数据和输出目录
python scripts/run_full_pipeline.py --data-dir examples --output-dir output

# 带业务规则（NL2SWRL）
python scripts/run_full_pipeline.py \
    --rules "如果客户的累计消费金额超过10000元，则该客户为VIP客户"

# 禁用 Stage 6/7（仅运行核心5阶段）
python scripts/run_full_pipeline.py --no-stage6 --no-stage7
```

### 4. 运行单个阶段

```bash
# 只运行 Stage 1（数据准备）
python scripts/run_stage.py stage1

# 只运行 Stage 2（概念抽取）
python scripts/run_stage.py stage2 -v

# 运行全部阶段
python scripts/run_stage.py all
```

### 5. 推理效果对比实验（有本体 vs 无本体）

这是验证「本体对模型推理效果影响」的核心实验，对比三种条件：

| 条件 | 说明 |
|------|------|
| `bare_llm` | 裸 LLM，仅凭参数化知识回答（无本体） |
| `ontology_llm` | LLM + 本体上下文注入（有本体） |
| `symbolic` | 纯符号推理，不调用 LLM，结论附带证明链 |

```bash
# 完整对比实验（需要配置 LLM API）
python scripts/run_reasoning_eval.py

# 仅运行符号推理（不需要 LLM，用于快速验证本体推理能力）
python scripts/run_reasoning_eval.py --no-llm

# 限制题目数量（快速测试）
python scripts/run_reasoning_eval.py --limit 5

# 指定超时与重试（远程 API 慢时）
LLM_TIMEOUT=30 LLM_MAX_RETRIES=1 python scripts/run_reasoning_eval.py --delay 0.3
```

输出报告位于 `output/reasoning_eval/`：
- `report.json` — 逐题结果 + 聚合指标（准确率/完整性/幻觉率/延迟）
- `report.md` — 人类可读的对比报告（总体指标表 + 本体增强效果量 + 逐题明细 + 结论）

## 项目结构

```
OntologyAutoGen/
├── ontology_gen/                        # 核心 Python 包
│   ├── __init__.py
│   ├── config.py                        # 全局配置（阈值、API、特性开关）
│   ├── models.py                        # 核心数据类型（Concept/Property/Relation/...）
│   ├── llm_client.py                    # OpenAI 兼容客户端 + Embedding 降级链
│   ├── utils.py                         # JSON I/O、文本分块、DDL 解析
│   ├── pipeline.py                      # 端到端管线编排器（7阶段）
│   │
│   ├── stage1_data_prep/                # Stage 1: 数据准备
│   │   ├── quality_scorer.py            #   Algorithm 1.1: 质量评分（0-10分）
│   │   ├── ddl_completer.py             #   DDL 补全（LLM 推断注释）
│   │   ├── id_mapper.py                 #   ID Mapping（桥接字段匹配）
│   │   ├── doc_parser.py                #   文档解析（PDF/MD/HTML/TXT）
│   │   ├── null_filter.py               #   空值过滤（>50%忽略，30-50%低置信）
│   │   └── query_pattern_analyzer.py    #   查询模式分析（CRUD/聚合/JOIN/数据缺口）
│   │
│   ├── stage2_concept/                  # Stage 2: 概念抽取
│   │   ├── prompts.py                   #   Prompt 2.1/2.2/合并判断
│   │   ├── rdb_concept_extractor.py     #   RDB 路径概念抽取
│   │   ├── text_concept_extractor.py    #   文本路径概念抽取（5条反幻觉规则）
│   │   ├── concept_merger.py            #   Algorithm 2.3: 四步概念合并（Union-Find）
│   │   ├── granularity_decider.py       #   Algorithm 2.4: 粒度决策树
│   │   ├── layer_classifier.py          #   概念层次分类（data/logic/application）
│   │   └── identity_spec_extractor.py   #   身份标识规则抽取（PK/UK约束）
│   │
│   ├── stage3_taxonomy/                 # Stage 3: 概念层次构建
│   │   ├── prompts.py                   #   Prompt 3.1/3.2
│   │   ├── hearst_pattern.py            #   Hearst Pattern 匹配（中英文）
│   │   ├── taxonomy_inducer.py          #   LLM 归纳 + 实例统计 fallback
│   │   ├── relation_type_classifier.py  #   关系类型分类（is-a/part-of/...）
│   │   └── cycle_detector.py            #   Algorithm 3.3: DFS 环检测 + 删边消环
│   │
│   ├── stage4_relation/                 # Stage 4: 关系/属性构建
│   │   ├── prompts.py                   #   Prompt 4.1
│   │   ├── relation_extractor.py        #   三元组抽取（文本+DDL）
│   │   ├── property_relation_decider.py #   Algorithm 4.2: 属性vs关系决策树
│   │   ├── fk_filter.py                 #   Algorithm 4.3: 外键业务语义过滤（3层规则）
│   │   ├── m2m_reifier.py               #   Algorithm 4.4: M:N 再化（引入中间节点）
│   │   ├── relation_normalizer.py       #   关系同义词归一化
│   │   ├── derivation_extractor.py      #   派生属性计算规则抽取（公式/聚合/查找/条件）
│   │   └── validation_rule_extractor.py #   数据验证规则抽取（正则/范围/长度）
│   │
│   ├── stage5_axiom/                    # Stage 5: 公理/规则层
│   │   ├── prompts.py                   #   Prompt 5.2-B + NL2SWRL 四步
│   │   ├── domain_range_inferrer.py     #   Algorithm 5.2-A: 统计多数投票
│   │   ├── axiom_generator.py           #   LLM 公理生成 + Taxonomy→subClassOf
│   │   ├── nl2swrl.py                   #   NL2SWRL 四步管线（纯Python校验）
│   │   ├── axiom_risk_classifier.py     #   公理风险分级（低/中/高）
│   │   └── consistency_checker.py       #   6项一致性检查
│   │
│   ├── stage6_semantic/                 # Stage 6: 语义丰富化
│   │   ├── prompts.py                   #   各步骤 Prompt 模板
│   │   ├── glossary_builder.py          #   统一业务术语表构建
│   │   ├── external_mapping_extractor.py#   跨系统术语映射抽取
│   │   ├── annotation_extractor.py      #   语义注解抽取（DDL注释+文档）
│   │   ├── trigger_rule_extractor.py    #   触发器规则抽取（ECA模式）
│   │   └── governance_rule_generator.py #   治理规则自动生成（命名/完整性/一致性）
│   │
│   │   ├── stage7_process/                  # Stage 7: 流程与权限
│   │   │   ├── prompts.py                   #   各步骤 Prompt 模板
│   │   │   ├── operation_extractor.py       #   原子业务操作抽取
│   │   │   ├── service_composer.py          #   服务编排（顺序/并行/条件/循环）
│   │   │   └── permission_extractor.py      #   权限主体与规则抽取
│   │   │
│   ├── reasoning/                       # ⭐ 本体推理引擎（Stage 8）
│   │   ├── __init__.py                  #   模块入口，导出核心 API
│   │   ├── ontology_loader.py           #   本体加载器 + 索引器（OntologyIndex）
│   │   ├── symbolic_reasoner.py         #   符号推理引擎（8种推理 + 证明链）
│   │   └── context_builder.py           #   本体→LLM 上下文序列化器
│   │
│   └── output/                          # 输出模块
│       ├── json_schema.py               #   JSON Schema 定义与校验
│       └── ontology_builder.py          #   最终 Ontology 组装
│
├── examples/                            # 示例数据
│   ├── ddl/ecommerce.sql                #   电商 DDL（7张表）
│   ├── docs/product_intro.md            #   电商领域文档
│   ├── queries/query_log.jsonl          #   20条业务查询SQL
│   ├── config/ecommerce.yaml            #   领域配置（业务术语、同义词）
│   └── eval/                            # ⭐ 推理评测
│       └── qa_dataset.json              #   18道电商领域问答+标准答案
│
├── scripts/                             # CLI 脚本
│   ├── run_full_pipeline.py             #   运行完整管线（7阶段）
│   ├── run_stage.py                     #   运行单个阶段
│   └── run_reasoning_eval.py            # ⭐ 推理效果对比实验（有本体 vs 无本体）
│
├── tests/                               # 单元测试
│   ├── test_quality_scorer.py           #   质量评分测试
│   ├── test_concept_merger.py           #   概念合并测试
│   ├── test_cycle_detector.py           #   环检测测试
│   ├── test_fk_filter.py               #   外键过滤测试
│   ├── test_property_relation.py        #   属性vs关系测试
│   ├── test_m2m_reifier.py             #   M:N再化测试
│   ├── test_domain_range.py             #   domain/range推断测试
│   ├── test_layer_classifier.py         #   层次分类测试
│   ├── test_derivation_extractor.py     #   派生属性抽取测试
│   ├── test_validation_rules.py         #   验证规则测试
│   ├── test_query_pattern_analyzer.py   #   查询模式分析测试
│   ├── test_glossary_builder.py         #   术语表构建测试
│   ├── test_trigger_rule_extractor.py   #   触发器规则测试
│   ├── test_operation_extractor.py      #   操作抽取测试
│   ├── test_permission_extractor.py     #   权限抽取测试
│   └── test_models_extended.py          #   扩展模型测试
│
├── output/                              # 管线输出目录
│   ├── ontology.json                    #   最终本体 JSON
│   ├── consistency_report.json          #   一致性检查报告
│   └── stage[1-7]_report.json           #   各阶段报告
│
├── requirements.txt
├── .env.example
└── README.md
```

## 核心算法索引

| 算法 | 模块 | 描述 |
|------|------|------|
| Algorithm 1.1 | `quality_scorer.py` | 数据质量评分（5维 0-10 分） |
| Algorithm 2.3 | `concept_merger.py` | 四步概念合并（精确→编辑距离→语义→LLM） |
| Algorithm 2.4 | `granularity_decider.py` | 粒度决策树 |
| Algorithm 3.3 | `cycle_detector.py` | DFS 环检测 + 删最低置信度边消环 |
| Algorithm 4.2 | `property_relation_decider.py` | 属性 vs 关系决策树（Q1-Q3） |
| Algorithm 4.3 | `fk_filter.py` | 外键业务语义过滤（3层规则） |
| Algorithm 4.4 | `m2m_reifier.py` | M:N 关系再化（引入中间节点） |
| Algorithm 5.2-A | `domain_range_inferrer.py` | 统计多数投票 domain/range 推断 |
| NL2SWRL | `nl2swrl.py` | 自然语言→SWRL 四步管线 |
| 一致性检查 | `consistency_checker.py` | 6项一致性验证 |
| 层次分类 | `layer_classifier.py` | 概念三层分类（data/logic/application） |
| 身份标识 | `identity_spec_extractor.py` | PK/UK 约束→身份标识规则 |
| 派生抽取 | `derivation_extractor.py` | 计算属性公式抽取（文本+SQL） |
| 验证规则 | `validation_rule_extractor.py` | DDL约束+文本→验证规则 |
| 查询模式 | `query_pattern_analyzer.py` | 查询日志→可复用数据操作模式 |
| 术语表 | `glossary_builder.py` | 统一业务术语表（同义词+频率） |
| 触发器 | `trigger_rule_extractor.py` | ECA 触发规则（事件-条件-动作） |
| 治理规则 | `governance_rule_generator.py` | 命名/完整性/一致性规则自动生成 |
| 操作抽取 | `operation_extractor.py` | 原子业务操作（文本+查询日志） |
| 服务编排 | `service_composer.py` | 顺序/并行/条件/循环流程组合 |
| 权限抽取 | `permission_extractor.py` | 权限主体+RBAC规则 |
| 符号推理 | `reasoning/symbolic_reasoner.py` | 8种推理（子类闭包/关系继承/路径搜索/约束检查/派生溯源/ECA触发/实例分类/概念全貌） |
| 证明链 | `reasoning/symbolic_reasoner.py` | 每步推理附带规则名+前提+结论+证据ID，实现可审计推理 |
| 本体序列化 | `reasoning/context_builder.py` | 本体→LLM 可读文本（全量/按查询相关性切片） |

## 输出格式

最终输出为 `output/ontology.json`，结构如下：

```json
{
  "version": "1.0",
  "domain": "ecommerce",
  "entity_types": [
    {
      "name": "客户",
      "id": "concept_a1b2c3d4",
      "name_en": "customer",
      "aliases": ["顾客", "消费者"],
      "source": "rdb",
      "confidence": 0.9,
      "is_entity_type": true,
      "layer": "data",
      "identity_spec": "customer_id"
    }
  ],
  "properties": [...],
  "relations": [...],
  "taxonomy": {
    "nodes": {...},
    "root_ids": [...]
  },
  "axioms": [...],
  "rules": [...],
  "glossary": [...],
  "external_mappings": [...],
  "semantic_annotations": [...],
  "trigger_rules": [...],
  "governance_rules": [...],
  "operations": [...],
  "service_compositions": [...],
  "permission_subjects": [...],
  "permission_rules": [...],
  "query_patterns": [...],
  "metadata": {
    "domain": "ecommerce",
    "created_at": "2026-07-04T20:00:00",
    "stats": {
      "entity_type_count": 7,
      "property_count": 15,
      "relation_count": 8,
      "axiom_count": 12,
      "glossary_count": 10,
      "trigger_count": 3,
      "operation_count": 5,
      "permission_count": 4,
      "query_pattern_count": 6
    },
    "consistency_report": {
      "is_consistent": true,
      "violations": [],
      "warnings": []
    }
  }
}
```

## 推理评测输出

运行 `run_reasoning_eval.py` 后，在 `output/reasoning_eval/` 生成：

| 文件 | 说明 |
|------|------|
| `report.json` | 机器可读结果：`meta`（实验配置）+ `summary`（三条件聚合指标）+ `questions`（逐题回答与评分） |
| `report.md` | 人类可读报告：总体指标对比表 → 本体增强效果量（Δ准确率/Δ完整性/Δ幻觉率）→ 逐题明细 → 结论 |

### 评分指标

每个回答按三个维度自动评分（基于中文 bigram 术语覆盖率）：

| 指标 | 含义 | 计算 |
|------|------|------|
| `accuracy` | 准确率 | 标准答案关键术语的长度加权覆盖率 |
| `completeness` | 完整性 | 标准答案关键术语的原始覆盖率 |
| `hallucination` | 幻觉率 | 回答中未被标准答案/本体证据支撑的术语占比 |

### 三条件对比的意义

| 条件 | 回答来源 | 可追溯性 | 幻觉风险 |
|------|----------|----------|----------|
| **无本体（裸LLM）** | 模型参数化知识 | 不可追溯 | 高（可能编造领域细节） |
| **有本体（LLM+本体）** | 本体上下文 + 模型 | 可引用公理 | 低（受本体约束） |
| **符号推理（纯本体）** | 确定性推理引擎 | 完全可追溯（证明链） | 零（不生成） |

> **核心结论**：本体为模型推理提供了**可验证的结构化先验**，把「概率性猜测」转化为「有据可查的推断」。符号推理作为零幻觉基线，LLM+本体在自然语言表达上更灵活，裸 LLM 在领域细节上最易出错。

## 配置说明

### 环境变量 (.env)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_BASE_URL` | LLM API base URL | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | API key（留空=降级模式） | — |
| `OPENAI_MODEL` | 模型名称 | `gpt-4o` |
| `EMBEDDING_MODEL` | Embedding 模型 | `paraphrase-multilingual-MiniLM-L12-v2` |
| `LLM_TIMEOUT` | LLM 请求超时（秒） | `30` |
| `LLM_MAX_RETRIES` | LLM 请求最大重试次数 | `1` |

### 特性开关 (Config)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enable_stage6` | 启用 Stage 6 语义丰富化 | `True` |
| `enable_stage7` | 启用 Stage 7 流程与权限 | `True` |
| `governance_auto_generate` | 自动生成治理规则 | `True` |

### 领域配置 (YAML)

```yaml
domain: ecommerce
business_terms: [客户, 订单, 商品]     # FK 过滤 Rule 3
concept_synonyms:                       # 概念合并辅助
  - standard: 客户
    aliases: [顾客, 消费者, 买家]
relation_synonyms:                      # 关系归一化
  - standard_name: hasOrder
    aliases: [下单, 创建订单]
    inverse: isOrderOf
system_table_tags:                      # FK 过滤 Rule 1
  system_log: system
external_mappings:                      # 跨系统映射
  - internal_term: 客户
    external_system: ERP
    external_term: Customer
    external_code: "C001"
permission_subjects:                    # 权限主体定义
  - name: 管理员
    type: role
    description: 系统管理员
```

## 降级模式

当 LLM API 未配置时，管线自动降级：

| 功能 | 正常模式 | 降级模式 |
|------|----------|----------|
| 概念抽取（RDB） | 规则 + LLM 增强 | 仅规则（表名→概念，字段→属性） |
| 概念抽取（文本） | LLM + 反幻觉规则 | 规则 fallback（中文名词短语 + 词频） |
| 概念合并 | 精确→编辑距离→语义嵌入→LLM | 精确→编辑距离→hash向量 |
| 层次分类 | LLM 分类 + 规则 | 仅规则（基于来源） |
| 层次构建 | LLM 归纳 + Hearst + 实例统计 | Hearst + 实例统计 |
| 关系抽取（文本） | LLM 三元组抽取 | 跳过（仅 DDL FK 路径） |
| 派生属性 | LLM + SQL 模式匹配 | 仅 SQL 模式匹配 |
| 验证规则 | LLM + DDL 约束 | 仅 DDL 约束解析 |
| 公理生成 | LLM 驱动 + 确定性转换 | 仅确定性转换（Taxonomy→subClassOf） |
| NL2SWRL | LLM 四步管线 | 规则 fallback（if-then 分割 + 精确匹配） |
| 术语表 | LLM 增强 + 配置 | 仅从配置构建 |
| 触发器 | LLM + 规则匹配 | 仅规则匹配（关键词模式） |
| 操作抽取 | LLM + 动词短语 | 仅动词短语规则匹配 |
| 服务编排 | LLM 编排 + 规则 | 仅顺序流检测 |
| 权限抽取 | LLM + 配置 | 仅从配置读取 |

## 运行测试

```bash
cd OntologyAutoGen
python -m pytest tests/ -v
```

## 技术决策

1. **SWRL 校验不依赖 owlready2**：用纯 Python 检查变量绑定完整性、类型匹配、本体元素存在性，避免 Java 依赖。
2. **Union-Find 实现传递性合并**：概念合并用并查集确保 A~B, B~C → A~C 自动合并。
3. **Embedding 三级降级**：sentence-transformers → TF-IDF → hash 向量，确保无模型环境也能运行。
4. **JSON Schema 输出**：适配工业 KG/Neo4j 场景，不输出 OWL/Turtle 格式。
5. **7阶段可选架构**：Stage 1-5 为核心管线，Stage 6/7 可通过配置开关独立启用/禁用。
6. **概念三层分类**：data/logic/application 三层架构，支持复杂企业场景。
7. **ECA 触发规则**：事件-条件-动作模式，连接 SWRL 规则与业务流程。
8. **服务编排组合**：支持顺序/并行/条件/循环/异常处理五种编排模式。
