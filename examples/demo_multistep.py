#!/usr/bin/env python3
"""案例三：多步复杂推理案例。

本脚本演示一个端到端的"新业务线上线"场景，把 CRUD + 推理串联成一条
7 步流水线：

  Step 1  新增概念      —— 为"直播带货"新增商品/订单/主播等概念
  Step 2  建立层次      —— 用 subClassOf 把新概念挂到现有分类树
  Step 3  新增关系      —— 创建 直播间->商品、主播->直播间 等关系
  Step 4  验证关系继承  —— 子类是否继承了祖先的关系
  Step 5  多跳路径推理  —— 从 客户 出发，经多跳到达 直播商品
  Step 6  传递闭包验证  —— 直播商品 ⊑ 商品 的多跳闭包
  Step 7  ECA 触发      —— 触发与订单/支付相关的 ECA 规则

每一步都会收集结果，最终输出一份结构化的流水线报告。

运行::

    python examples/demo_multistep.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ontology_gen.reasoning import load_ontology, OntologyEditor, run_multistep_pipeline


def build_config() -> dict:
    """构造多步流水线的配置（描述新业务线需要的本体扩展）。"""
    return {
        # Step 1: 新增概念
        "concepts": [
            {"name": "直播商品", "name_en": "live_product",
             "layer": "data", "description": "在直播中销售的商品"},
            {"name": "直播间", "name_en": "live_room",
             "layer": "logic", "description": "直播销售场所"},
            {"name": "主播", "name_en": "streamer",
             "layer": "application", "description": "直播销售者"},
            {"name": "直播订单", "name_en": "live_order",
             "layer": "data", "description": "通过直播产生的订单"},
        ],
        # Step 2: 建立 subClassOf 层次
        "subclass_edges": [
            ["直播商品", "商品"],
            ["直播订单", "订单"],
            ["主播", "客户"],
        ],
        # Step 3: 新增关系
        "relations": [
            {"name": "hostsLive", "domain": "主播", "range_": "直播间",
             "name_cn": "主持", "description": "主播主持直播间"},
            {"name": "sellsIn", "domain": "直播商品", "range_": "直播间",
             "name_cn": "在售于", "description": "商品在直播间销售"},
            {"name": "placesLiveOrder", "domain": "客户", "range_": "直播订单",
             "name_cn": "下直播单", "description": "客户下直播订单"},
        ],
        # Step 4: 验证关系继承（主播继承客户的关系）
        "inheritance_checks": [
            ["主播", "canPlaceOrder", True],   # 客户有 canPlaceOrder，主播应继承
            ["直播订单", "canPlaceOrder", False],  # 直播订单不应有 canPlaceOrder
        ],
        # Step 5: 多跳路径查询
        "path_queries": [
            ["客户", "直播商品"],   # 客户 -> 直播订单 -> 直播商品 ?
            ["主播", "直播商品"],   # 主播 -> 直播间 -> 直播商品 ?
        ],
        # Step 6: 传递闭包验证（三元组：第三项为期望值）
        "closure_checks": [
            ["直播商品", "商品", True],     # 应为是
            ["直播订单", "订单", True],     # 应为是
            ["主播", "客户", True],         # 应为是
            ["直播商品", "订单", False],    # 应为否（防止误判）
        ],
        # Step 7: ECA 触发
        "trigger_queries": [
            "直播订单未支付",
            "客户超时未确认收货",
        ],
    }


def main() -> None:
    onto_path = os.path.join(ROOT, "output", "ontology.json")
    print("=" * 70)
    print("  案例三：多步复杂推理（新业务线上线）")
    print("=" * 70)

    idx = load_ontology(onto_path)
    editor = OntologyEditor(idx)
    print(f"\n[初始] 概念={len(idx.raw_concepts)}, "
          f"关系={len(idx.raw_relations)}, 公理={len(idx.raw_axioms)}")

    config = build_config()
    print(f"\n[配置] 将执行 {len(config['concepts'])} 个新增概念, "
          f"{len(config['subclass_edges'])} 条层次边, "
          f"{len(config['relations'])} 个关系\n")

    report = run_multistep_pipeline(editor, config)

    # ------------------------------------------------------------------
    print("=" * 70)
    print("  流水线执行结果")
    print("=" * 70)
    for step in report.steps:
        status = "✓ PASS" if step.ok else "✗ FAIL"
        print(f"\n[{status}] {step.name}: {step.description}")
        # 打印每步关键输出
        out = step.output
        if step.name == "step_add_concepts":
            for c in out.get("added", []):
                print(f"    + 概念 {c['name']} (id={c['id']})")
        elif step.name == "step_build_taxonomy":
            for e in out.get("edges", []):
                print(f"    + {e[0]} ⊑ {e[1]}")
        elif step.name == "step_add_relations":
            print(f"    新增关系 ids: {out.get('relations', [])}")
        elif step.name == "step_verify_inheritance":
            for c in out.get("checks", []):
                mark = "✓" if c.get("ok") else "✗"
                print(f"    {mark} {c['concept']} 期望"
                      f"{'继承' if c.get('expected') else '不继承'} "
                      f"{c.get('expected_relation')}: "
                      f"inherited={c.get('inherited')}")
        elif step.name == "step_multi_hop_reasoning":
            for q in out.get("queries", []):
                mark = "✓" if q["found"] else "✗"
                print(f"    {mark} {q['src']} -> {q['dst']}: "
                      f"found={q['found']}, steps={q['proof_steps']}")
        elif step.name == "step_subclass_closure":
            for c in out.get("checks", []):
                mark = "✓" if c["found"] else "✗"
                print(f"    {mark} {c['child']} ⊑ {c['parent']}: "
                      f"{c['answer']} (steps={c['proof_steps']})")
        elif step.name == "step_trigger_firing":
            for q in out.get("queries", []):
                mark = "✓" if q["fired"] else "○"
                print(f"    {mark} {q['query']}: fired={q['fired']}")

    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  流水线汇总")
    print("=" * 70)
    s = report.summary()
    print(f"  总步骤: {s['total_steps']}, 通过: {s['passed']}, "
          f"失败: {s['failed']}, 整体: "
          f"{'全部通过 ✓' if s['all_ok'] else '存在失败 ✗'}")
    print(f"  变更次数: {editor.changelog_summary()['total_changes']}")
    print(f"  最终概念数: {len(idx.raw_concepts)}, "
          f"关系数: {len(idx.raw_relations)}, "
          f"公理数: {len(idx.raw_axioms)}")

    # 保存完整报告
    out_path = os.path.join(ROOT, "output", "multistep_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n  完整报告已保存: {out_path}")

    # 保存扩展后的本体
    onto_out = os.path.join(ROOT, "output", "ontology_multistep_demo.json")
    editor.save(onto_out)
    print(f"  扩展后本体已保存: {onto_out}")

    print("\n" + "=" * 70)
    print("  案例三完成。")
    print("=" * 70)


if __name__ == "__main__":
    main()
