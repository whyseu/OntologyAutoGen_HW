"""Query pattern analyzer (Category 7.1-7.7).

Analyzes query logs to extract reusable query/data operation patterns.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

from ..config import Config
from ..models import Concept, Property, QueryPattern

logger = logging.getLogger("ontology_gen.query_pattern_analyzer")


class QueryPatternAnalyzer:
    def __init__(self, config: Config):
        self.config = config

    def analyze(
        self,
        queries: list[str],
        concepts: list[Concept],
        properties: list[Property],
    ) -> list[QueryPattern]:
        if not queries:
            return []

        patterns: list[QueryPattern] = []

        concept_name_map = {}
        for c in concepts:
            if c.name_en:
                concept_name_map[c.name_en.lower()] = c
            concept_name_map[c.name.lower()] = c

        patterns.extend(self._detect_crud_patterns(queries, concept_name_map))
        patterns.extend(self._detect_aggregation_patterns(queries, concept_name_map))
        patterns.extend(self._detect_join_patterns(queries, concept_name_map))
        patterns.extend(self._detect_data_gap_patterns(queries, concept_name_map, properties))
        patterns.extend(self._suggest_indexes(queries, concept_name_map))

        logger.info(f"Query patterns: {len(patterns)} extracted")
        return patterns

    def _detect_crud_patterns(
        self,
        queries: list[str],
        concept_map: dict[str, Concept],
    ) -> list[QueryPattern]:
        patterns = []
        crud_counter: Counter = Counter()

        table_pattern = re.compile(
            r"(?:FROM|INTO|UPDATE)\s+[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )
        where_pattern = re.compile(
            r"WHERE\s+(.+?)(?:GROUP|ORDER|LIMIT|HAVING|$)",
            re.IGNORECASE | re.DOTALL,
        )

        for query in queries:
            query_upper = query.strip().upper()
            tables = table_pattern.findall(query)

            for table in tables:
                table_lower = table.lower()
                if table_lower not in concept_map:
                    continue

                concept = concept_map[table_lower]

                if query_upper.startswith("SELECT"):
                    crud_counter[("entity_lookup", concept.name)] += 1

                    where_match = where_pattern.search(query)
                    if where_match:
                        conditions = where_match.group(1).strip()
                        key = f"filtered_query_{concept.name}_{conditions[:30]}"
                        if crud_counter[key] == 0:
                            crud_counter[key] = 1
                            patterns.append(QueryPattern(
                                name=f"查询{concept.name}",
                                description=f"按条件查询{concept.name}: {conditions[:50]}",
                                pattern_type="filtered_query",
                                target_concepts=[concept.id],
                                filter_conditions=[conditions],
                                source="query_log",
                            ))

                elif query_upper.startswith("UPDATE"):
                    patterns.append(QueryPattern(
                        name=f"更新{concept.name}",
                        description=f"更新{concept.name}数据",
                        pattern_type="update",
                        target_concepts=[concept.id],
                        source="query_log",
                    ))

                elif query_upper.startswith("DELETE"):
                    patterns.append(QueryPattern(
                        name=f"删除{concept.name}",
                        description=f"删除{concept.name}数据",
                        pattern_type="delete",
                        target_concepts=[concept.id],
                        source="query_log",
                    ))

        # Create entity_lookup patterns for frequently accessed tables
        for key, count in crud_counter.items():
            if not isinstance(key, tuple): continue
            (ptype, cname) = key
            if ptype == "entity_lookup" and count >= self.config.query_pattern_min_frequency:
                concept = next((c for c in concept_map.values() if c.name == cname), None)
                if concept:
                    patterns.append(QueryPattern(
                        name=f"查询{cname}",
                        description=f"频繁查询{cname} (出现{count}次)",
                        pattern_type="entity_lookup",
                        target_concepts=[concept.id],
                        frequency=count,
                        source="query_log",
                    ))

        return patterns

    def _detect_aggregation_patterns(
        self,
        queries: list[str],
        concept_map: dict[str, Concept],
    ) -> list[QueryPattern]:
        patterns = []
        agg_pattern = re.compile(
            r"(SUM|COUNT|AVG|MAX|MIN)\s*\(\s*[`\"']?(\w+)[`\"']?\s*\)",
            re.IGNORECASE,
        )
        group_pattern = re.compile(
            r"GROUP\s+BY\s+(.+?)(?:HAVING|ORDER|LIMIT|$)",
            re.IGNORECASE,
        )
        table_pattern = re.compile(
            r"FROM\s+[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )

        for query in queries:
            agg_matches = agg_pattern.findall(query)
            if not agg_matches:
                continue

            tables = table_pattern.findall(query)
            target_ids = []
            for t in tables:
                if t.lower() in concept_map:
                    target_ids.append(concept_map[t.lower()].id)

            agg_funcs = [f"{func}({col})" for func, col in agg_matches]
            group_match = group_pattern.search(query)
            group_cols = group_match.group(1).strip() if group_match else ""

            patterns.append(QueryPattern(
                name=f"统计分析_{'_'.join(agg_funcs[:2])}",
                description=f"聚合查询: {', '.join(agg_funcs)}",
                pattern_type="aggregation",
                target_concepts=target_ids,
                aggregation_functions=agg_funcs,
                filter_conditions=[f"GROUP BY {group_cols}"] if group_cols else [],
                source="query_log",
            ))

        return patterns

    def _detect_join_patterns(
        self,
        queries: list[str],
        concept_map: dict[str, Concept],
    ) -> list[QueryPattern]:
        patterns = []
        join_pattern = re.compile(
            r"JOIN\s+[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )
        from_pattern = re.compile(
            r"FROM\s+[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )

        for query in queries:
            joins = join_pattern.findall(query)
            if not joins:
                continue

            from_tables = from_pattern.findall(query)
            all_tables = from_tables + joins
            target_ids = []
            for t in all_tables:
                if t.lower() in concept_map:
                    target_ids.append(concept_map[t.lower()].id)

            if len(target_ids) >= 2:
                patterns.append(QueryPattern(
                    name=f"联合查询_{'_'.join(t[:10] for t in all_tables[:3])}",
                    description=f"跨表联合查询: {', '.join(all_tables)}",
                    pattern_type="join_query" if len(target_ids) <= 3 else "cross_source",
                    target_concepts=target_ids,
                    source="query_log",
                ))

        return patterns

    def _detect_data_gap_patterns(
        self,
        queries: list[str],
        concept_map: dict[str, Concept],
        properties: list[Property],
    ) -> list[QueryPattern]:
        patterns = []
        null_pattern = re.compile(
            r"(\w+)\s+IS\s+(?:NOT\s+)?NULL",
            re.IGNORECASE,
        )
        coalesce_pattern = re.compile(
            r"(?:COALESCE|IFNULL|ISNULL)\s*\(\s*[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )

        gap_fields = set()
        for query in queries:
            for match in null_pattern.finditer(query):
                gap_fields.add(match.group(1).lower())
            for match in coalesce_pattern.finditer(query):
                gap_fields.add(match.group(1).lower())

        if gap_fields:
            prop_ids = [
                p.id for p in properties
                if p.name.lower() in gap_fields
            ]
            if prop_ids:
                patterns.append(QueryPattern(
                    name="数据缺口检测",
                    description=f"存在NULL检查的字段: {', '.join(gap_fields)}",
                    pattern_type="data_gap",
                    data_gap_fields=prop_ids,
                    compensation_strategy="default_value",
                    source="query_log",
                ))

        return patterns

    def _suggest_indexes(
        self,
        queries: list[str],
        concept_map: dict[str, Concept],
    ) -> list[QueryPattern]:
        patterns = []
        where_col_pattern = re.compile(
            r"WHERE\s+.*?[`\"']?(\w+)[`\"']?\s*[=<>!]",
            re.IGNORECASE,
        )
        order_col_pattern = re.compile(
            r"ORDER\s+BY\s+[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )

        col_frequency: Counter = Counter()
        for query in queries:
            for match in where_col_pattern.finditer(query):
                col_frequency[match.group(1).lower()] += 1
            for match in order_col_pattern.finditer(query):
                col_frequency[match.group(1).lower()] += 1

        frequent_cols = [
            col for col, count in col_frequency.most_common(10)
            if count >= self.config.query_pattern_min_frequency
        ]

        if frequent_cols:
            patterns.append(QueryPattern(
                name="索引优化建议",
                description=f"高频查询列建议建立索引",
                pattern_type="template",
                suggested_indexes=frequent_cols,
                source="query_log",
            ))

        return patterns
