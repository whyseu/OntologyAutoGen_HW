from __future__ import annotations
import os

class StageVisualizer:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def visualize_stage1(self, data: dict):
        """Generate a markdown report for Stage 1."""
        md = ["# Stage 1: Data Preparation\n"]
        md.append("## Quality Scores")
        md.append("| Table Name | Score | Should Process |")
        md.append("|------------|-------|----------------|")
        for qs in data.get("quality_scores", []):
            md.append(f"| {qs.get('table_name')} | {qs.get('score')} | {qs.get('should_process')} |")
        
        with open(os.path.join(self.output_dir, "stage1_visualization.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))

    def visualize_stage2(self, data: dict):
        """Generate a mermaid graph for Concepts."""
        concepts = data.get("concepts", [])
        md = ["# Stage 2: Concepts\n", "```mermaid", "classDiagram"]
        for c in concepts:
            md.append(f"    class {c.id} {{")
            md.append(f"        <<{c.layer.value}>>")
            md.append(f"        name: {c.name}")
            if c.identity_spec:
                md.append(f"        ID: {c.identity_spec}")
            md.append("    }")
        md.append("```")
        with open(os.path.join(self.output_dir, "stage2_visualization.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))

    def visualize_stage3(self, data: dict):
        """Generate a mermaid graph for Taxonomy."""
        taxonomy = data.get("taxonomy")
        md = ["# Stage 3: Taxonomy\n", "```mermaid", "graph TD"]
        if taxonomy:
            for node_id, node in taxonomy.nodes.items():
                for child_id in node.children_ids:
                    md.append(f"    {node_id} -->|is-a| {child_id}")
        md.append("```")
        with open(os.path.join(self.output_dir, "stage3_visualization.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))

    def visualize_stage4(self, stage2_data: dict, stage4_data: dict):
        """Generate a mermaid graph for Relations & Properties."""
        concepts = stage2_data.get("concepts", [])
        properties = stage4_data.get("properties", [])
        relations = stage4_data.get("relations", [])
        
        concept_names = {c.id: c.name for c in concepts}
        
        md = ["# Stage 4: Relations & Properties\n", "```mermaid", "erDiagram"]
        
        for p in properties:
            cname = concept_names.get(p.domain_concept_id, p.domain_concept_id)
            md.append(f"    {cname} {{")
            md.append(f"        {p.value_type} {p.name}")
            md.append("    }")
            
        for r in relations:
            domain = concept_names.get(r.domain_concept_id, r.domain_concept_id)
            range_c = concept_names.get(r.range_concept_id, r.range_concept_id)
            md.append(f"    {domain} ||--o{{ {range_c} : \"{r.name}\"")
            
        md.append("```")
        with open(os.path.join(self.output_dir, "stage4_visualization.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))
