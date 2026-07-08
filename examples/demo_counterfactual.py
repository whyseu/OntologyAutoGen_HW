#!/usr/bin/env python3
"""案例四：反事实推理 (Counterfactual Reasoning) 演示

通过假设性地修改本体结构（移除/添加公理、移除概念等），
分析"如果 X 不成立 / 成立，会有什么影响？"
这是纯本体结构级别的因果推断，LLM 很难做到。

四种反事实场景：
  1. 移除子类关系：如果 VIP客户 不是 客户 的子类
  2. 移除关系：如果移除 hasOrder 关系
  3. 添加子类关系：如果 订单 成为 商品 的子类（荒谬但可验证）
  4. 移除概念：如果完全移除"客户"概念

每个场景输出影响分析 + 推理证明链。

运行:
    cd OntologyAutoGen
    python examples/demo_counterfactual.py

输出:
    output/counterfactual_report.json
"""
from __future__ import annotations

import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ontology_gen.reasoning import load_ontology, SymbolicReasoner

ONTOLOGY_PATH = os.path.join(project_root, "output", "ontology.json")
OUTPUT_DIR = os.path.join(project_root, "output")
REPORT_PATH = os.path.join(OUTPUT_DIR, "counterfactual_report.json")


def main():
    print("=" * 70)
    print("  案例四：反事实推理 (Counterfactual Reasoning)")
    print("=" * 70)
    print()

    idx = load_ontology(ONTOLOGY_PATH)
    reasoner = SymbolicReasoner(idx)

    scenarios: list[dict] = []

    # ================================================================
    # 场景 1: 移除子类 — 如果 VIP客户 不是 客户 的子类
    # ================================================================
    print("=" * 60)
    print("场景 1: 如果 VIP客户 不是 客户 的子类？")
    print("=" * 60)
    result1 = reasoner.counterfactual_remove_subclass("VIP客户", "客户")
    print(result1.answer)
    print()
    print("推理链：")
    for i, step in enumerate(result1.proof_chain, 1):
        print(f"  {i}. [{step.rule}] {step.premise}")
        print(f"     → {step.conclusion}")
    print()
    scenarios.append({
        "id": "cf_scenario_1",
        "title": "移除子类：VIP客户 ⊑ 客户",
        "hypothesis": "如果 VIP客户 不是 客户 的子类",
        "type": "remove_subclass",
        "result": result1.to_dict(),
    })

    # ================================================================
    # 场景 2: 移除关系 — 如果移除 canPlaceOrder 关系
    # ================================================================
    print("=" * 60)
    print("场景 2: 如果移除 canPlaceOrder（客户→订单）关系？")
    print("=" * 60)
    result2 = reasoner.counterfactual_remove_relation("canPlaceOrder")
    print(result2.answer)
    print()
    print("推理链：")
    for i, step in enumerate(result2.proof_chain, 1):
        print(f"  {i}. [{step.rule}] {step.premise}")
        print(f"     → {step.conclusion}")
    print()
    scenarios.append({
        "id": "cf_scenario_2",
        "title": "移除关系：canPlaceOrder",
        "hypothesis": "如果移除 canPlaceOrder（客户→订单）关系",
        "type": "remove_relation",
        "result": result2.to_dict(),
    })

    # ================================================================
    # 场景 3: 添加子类 — 如果 订单 成为 商品 的子类（荒谬假设）
    # ================================================================
    print("=" * 60)
    print("场景 3: 如果 订单 成为 商品 的子类？（荒谬假设验证）")
    print("=" * 60)
    result3 = reasoner.counterfactual_add_subclass("订单", "商品")
    print(result3.answer)
    print()
    print("推理链：")
    for i, step in enumerate(result3.proof_chain, 1):
        print(f"  {i}. [{step.rule}] {step.premise}")
        print(f"     → {step.conclusion}")
    print()
    scenarios.append({
        "id": "cf_scenario_3",
        "title": "添加子类：订单 ⊑ 商品",
        "hypothesis": "如果 订单 成为 商品 的子类（荒谬假设）",
        "type": "add_subclass",
        "result": result3.to_dict(),
    })

    # ================================================================
    # 场景 4: 移除概念 — 如果完全移除"客户"概念
    # ================================================================
    print("=" * 60)
    print("场景 4: 如果完全移除'客户'概念？")
    print("=" * 60)
    result4 = reasoner.counterfactual_remove_concept("客户")
    print(result4.answer)
    print()
    print("推理链：")
    for i, step in enumerate(result4.proof_chain, 1):
        print(f"  {i}. [{step.rule}] {step.premise}")
        print(f"     → {step.conclusion}")
    print()
    scenarios.append({
        "id": "cf_scenario_4",
        "title": "移除概念：客户",
        "hypothesis": "如果完全移除客户概念",
        "type": "remove_concept",
        "result": result4.to_dict(),
    })

    # ================================================================
    # 保存报告
    # ================================================================
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = {
        "title": "反事实推理报告",
        "description": "通过假设性修改本体结构，分析因果影响",
        "ontology": ONTOLOGY_PATH,
        "scenarios": scenarios,
        "summary": {
            "total_scenarios": len(scenarios),
            "scenario_types": list(set(s["type"] for s in scenarios)),
        },
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("=" * 60)
    print(f"报告已保存至: {REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
