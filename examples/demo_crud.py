#!/usr/bin/env python3
"""案例一：本体增删改查（CRUD）演示。

本脚本展示如何用 :class:`OntologyEditor` 对已生成的本体做完整的增删改查：

  1. Create  —— 新增概念"海外仓"、新增关系"发货至"
  2. Read    —— 按 id / 名称 / 别名查询概念，列出关系
  3. Update  —— 给概念添加别名、修改描述
  4. Delete  —— 删除概念，并验证悬挂引用被自动清理

每一步都打印结果和变更日志，最后把编辑后的本体保存到
``output/ontology_crud_demo.json``。

运行::

    python examples/demo_crud.py
"""
from __future__ import annotations

import os
import sys

# add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ontology_gen.reasoning import load_ontology, OntologyEditor


def main() -> None:
    onto_path = os.path.join(ROOT, "output", "ontology.json")
    print("=" * 70)
    print("  案例一：本体增删改查（CRUD）")
    print("=" * 70)

    idx = load_ontology(onto_path)
    editor = OntologyEditor(idx)
    print(f"\n[初始] 概念数={len(idx.raw_concepts)}, "
          f"关系数={len(idx.raw_relations)}, "
          f"公理数={len(idx.raw_axioms)}")

    # ------------------------------------------------------------------
    print("\n--- 1. CREATE：新增概念 + 关系 ---")
    wh_id = editor.add_concept(
        name="海外仓", name_en="overseas_warehouse",
        aliases=["跨境仓", "保税仓"], layer="data",
        description="位于海外的仓储节点，用于跨境物流")
    print(f"  新增概念 海外仓 -> id={wh_id}")

    ship_id = editor.add_relation(
        name="shipFrom", domain_ref="商品", range_ref="海外仓",
        name_cn="发货自", description="商品从海外仓发货")
    print(f"  新增关系 shipFrom(商品->海外仓) -> id={ship_id}")

    sub_id = editor.add_subclass_axiom("海外仓", "仓库") \
        if idx.resolve_concept_id("仓库") else None
    # 若本体中无"仓库"概念，则新建并建立层次
    if not idx.resolve_concept_id("仓库"):
        wh2_id = editor.add_concept(name="仓库", layer="data",
                                    description="通用仓储节点")
        sub_id = editor.add_subclass_axiom("海外仓", "仓库")
        print(f"  新增概念 仓库 -> id={wh2_id}")
    print(f"  新增公理 subClassOf(海外仓 ⊑ 仓库) -> id={sub_id}")

    # ------------------------------------------------------------------
    print("\n--- 2. READ：按 id/名称/别名查询 ---")
    for ref in [wh_id, "海外仓", "跨境仓", "仓库"]:
        c = editor.get_concept(ref)
        if c:
            print(f"  get_concept({ref!r}) -> name={c['name']}, "
                  f"aliases={c.get('aliases')}, layer={c.get('layer')}")
        else:
            print(f"  get_concept({ref!r}) -> 未找到")

    rel = editor.get_relation("shipFrom")
    print(f"  get_relation('shipFrom') -> {rel['name']}: "
          f"{rel.get('name_cn')}")

    # ------------------------------------------------------------------
    print("\n--- 3. UPDATE：修改概念 ---")
    ok = editor.update_concept("海外仓",
                               aliases=["跨境仓", "保税仓", "海外集货仓"],
                               description="位于海外的仓储节点，支持跨境与保税两种模式")
    print(f"  update_concept('海外仓', ...) -> changed={ok}")
    c = editor.get_concept("海外仓")
    print(f"  修改后 aliases={c['aliases']}")
    print(f"  修改后 description={c['description']}")

    # ------------------------------------------------------------------
    print("\n--- 4. DELETE：删除概念并验证引用清理 ---")
    # 先记录删除前的关系数
    rel_before = len(idx.raw_relations)
    prop_before = len(idx.raw_properties)
    ok = editor.delete_concept("海外仓")
    print(f"  delete_concept('海外仓') -> deleted={ok}")
    print(f"  删除后概念数={len(idx.raw_concepts)} "
          f"(关系 {rel_before}->{len(idx.raw_relations)}, "
          f"属性 {prop_before}->{len(idx.raw_properties)})")
    # 验证 shipFrom 关系已被级联删除
    print(f"  get_relation('shipFrom') -> "
          f"{'仍存在(异常!)' if editor.get_relation('shipFrom') else '已级联删除 ✓'}")
    # 验证海外仓相关公理已清理
    print(f"  get_concept('海外仓') -> "
          f"{'仍存在(异常!)' if editor.get_concept('海外仓') else '已删除 ✓'}")

    # ------------------------------------------------------------------
    print("\n--- 5. 变更日志 ---")
    summary = editor.changelog_summary()
    print(f"  总变更次数: {summary['total_changes']}")
    for k, v in summary['by_op_target'].items():
        print(f"    {k}: {v}")
    print("  变更记录:")
    for r in summary['records']:
        print(f"    {r}")

    # ------------------------------------------------------------------
    print("\n--- 6. 保存编辑后的本体 ---")
    out_path = os.path.join(ROOT, "output", "ontology_crud_demo.json")
    editor.save(out_path)
    print(f"  已保存到 {out_path}")

    print("\n" + "=" * 70)
    print("  案例一完成。")
    print("=" * 70)


if __name__ == "__main__":
    main()
