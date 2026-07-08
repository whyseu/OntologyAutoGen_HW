#!/usr/bin/env python3
"""案例二：多 Agent 共享同一本体互动演示。

本脚本展示多个 agent 通过 :class:`AgentTeam` 共享同一个 :class:`OntologyEditor`，
协同完成本体扩展与校验任务：

  - **CuratorAgent**（策展者）：负责新增概念和关系
  - **ValidatorAgent**（校验者）：负责检查一致性、删除无效条目
  - **AnalystAgent**（分析师）：只读，负责多跳推理与路径查询

三个 agent 共享一个消息板，一个 agent 的编辑立即对其他 agent 可见。

运行::

    python examples/demo_multi_agent.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ontology_gen.reasoning import load_ontology, AgentTeam


def main() -> None:
    onto_path = os.path.join(ROOT, "output", "ontology.json")
    print("=" * 70)
    print("  案例二：多 Agent 共享本体互动")
    print("=" * 70)

    idx = load_ontology(onto_path)
    team = AgentTeam.__new__(AgentTeam)  # bypass to reuse editor pattern
    from ontology_gen.reasoning.ontology_editor import OntologyEditor
    editor = OntologyEditor(idx)
    team.__init__(editor)

    curator = team.add_agent("策展者A", "curator")
    validator = team.add_agent("校验者V", "validator")
    analyst = team.add_agent("分析师R", "analyst")

    print(f"\n[团队] agents={list(team.agents.keys())}")
    for a in team.agents.values():
        print(f"  {a.name} (role={a.role}) tools={a.tools}")

    # ------------------------------------------------------------------
    print("\n--- Round 1：策展者新增概念，分析师查询 ---")
    curator.say("我准备为跨境电商新增『海外仓』和『保税仓』两个概念", kind="chat")
    cid1 = curator.call_tool("add_concept", name="海外仓",
                             layer="data",
                             aliases=["overseas_warehouse"],
                             description="海外仓储节点")
    curator.say(f"已新增概念 海外仓 (id={cid1['id']})",
                recipient="分析师R", kind="result")

    # 分析师立即查询（共享 editor，立即可见）
    info = analyst.call_tool("query_concept", ref="海外仓")
    analyst.say(f"查询到 海外仓: found={info['found']}, "
                f"inherited_relations={info.get('inherited_relation_count', 0)}",
                kind="chat")

    # ------------------------------------------------------------------
    print("\n--- Round 2：策展者建立层次，分析师做子类推理 ---")
    curator.call_tool("add_concept", name="保税仓", layer="data",
                      description="保税模式仓储")
    curator.call_tool("add_subclass", child="保税仓", parent="海外仓")
    curator.say("已建立 保税仓 ⊑ 海外仓", kind="chat")

    res = analyst.call_tool("reason_is_a", child="保税仓", parent="海外仓")
    analyst.say(f"推理：保税仓 ⊑ 海外仓 ? answer={res['answer']}, "
                f"proof_steps={res['proof_steps']}", kind="chat")

    res2 = analyst.call_tool("reason_is_a", child="保税仓", parent="商品")
    analyst.say(f"推理：保税仓 ⊑ 商品 ? answer={res2['answer']} "
                f"(预期：否)", kind="chat")

    # ------------------------------------------------------------------
    print("\n--- Round 3：策展者新增关系，校验者检查 ---")
    curator.call_tool("add_relation", name="storedIn",
                      domain="海外仓", range_="商品",
                      name_cn="存储于")
    curator.say("已新增关系 storedIn(海外仓->商品)", kind="chat")

    rels = validator.call_tool("query_relations", ref="海外仓")
    validator.say(f"校验：海外仓 的关系数={len(rels)}", kind="chat")
    for r in rels:
        validator.say(f"  - {r['name']}: {r['domain']} -> {r['range']}",
                      kind="chat")

    # ------------------------------------------------------------------
    print("\n--- Round 4：校验者发现冗余概念并删除 ---")
    # 模拟：策展者又加了一个重复概念
    curator.call_tool("add_concept", name="overseas_warehouse",
                      layer="data", description="重复的海外仓英文概念")
    validator.say("发现冗余概念 overseas_warehouse，正在删除", kind="chat")
    validator.call_tool("delete_concept", ref="overseas_warehouse")
    validator.say("已删除冗余概念 overseas_warehouse", kind="result")

    # 分析师确认海外仓仍在
    info2 = analyst.call_tool("query_concept", ref="海外仓")
    analyst.say(f"删除后确认 海外仓 仍存在: {info2['found']}", kind="chat")

    # ------------------------------------------------------------------
    print("\n--- 通信记录 ---")
    for line in team.transcript():
        print(f"  {line}")

    # ------------------------------------------------------------------
    print("\n--- 变更统计 ---")
    summary = editor.changelog_summary()
    print(f"  总变更次数: {summary['total_changes']}")
    for k, v in summary['by_op_target'].items():
        print(f"    {k}: {v}")

    # ------------------------------------------------------------------
    # 保存产出物
    import json
    out_dir = os.path.join(ROOT, "output")
    report_path = os.path.join(out_dir, "multi_agent_report.json")
    onto_path_out = os.path.join(out_dir, "ontology_multi_agent_demo.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "agents": [{"name": a.name, "role": a.role}
                       for a in team.agents.values()],
            "messages": [m.to_dict() for m in team.board.history()],
            "changelog_summary": summary,
            "changelog": [c.to_dict() for c in editor.changelog],
        }, f, ensure_ascii=False, indent=2)
    editor.save(onto_path_out)
    print(f"\n  通信记录与变更日志已保存: {report_path}")
    print(f"  扩展后本体已保存: {onto_path_out}")

    print("\n" + "=" * 70)
    print("  案例二完成。多 agent 通过共享 editor 协同操作同一本体。")
    print("=" * 70)


if __name__ == "__main__":
    main()
