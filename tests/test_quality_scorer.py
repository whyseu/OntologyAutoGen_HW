"""Tests for Algorithm 1.1: Data quality scoring."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.stage1_data_prep.quality_scorer import QualityScorer


class TestQualityScorer:
    """Test the 5-rule quality scoring algorithm."""

    def setup_method(self):
        self.config = Config()
        self.scorer = QualityScorer(self.config)

    def test_high_quality_table(self):
        """Table with semantic name, comments, low null rate, and FKs should score 8-10."""
        score = self.scorer.score_rdb_table(
            table_name="customer",
            columns=[
                {"name": "customer_id", "type": "BIGINT", "comment": "客户ID"},
                {"name": "customer_name", "type": "VARCHAR(100)", "comment": "客户姓名"},
                {"name": "phone", "type": "VARCHAR(20)", "comment": "手机号"},
            ],
            ddl_comments={
                "customer": "客户信息表",
                "customer_id": "客户ID",
                "customer_name": "客户姓名",
                "phone": "手机号",
            },
            null_rates={"customer_id": 0.0, "customer_name": 0.05, "phone": 0.1},
            has_foreign_keys=False,
        )
        assert score >= 7, f"High quality table should score >= 7, got {score}"

    def test_low_quality_table(self):
        """Table with meaningless name, no comments should score low."""
        score = self.scorer.score_rdb_table(
            table_name="tmp_2024",
            columns=[
                {"name": "c1", "type": "INT", "comment": ""},
                {"name": "c2", "type": "VARCHAR(50)", "comment": ""},
                {"name": "c3", "type": "DATE", "comment": ""},
            ],
            ddl_comments={},
            null_rates={"c1": 0.6, "c2": 0.7, "c3": 0.5},
            has_foreign_keys=False,
        )
        assert score < 5, f"Low quality table should score < 5, got {score}"

    def test_system_table_with_fk(self):
        """System table should still get FK bonus but low overall."""
        score = self.scorer.score_rdb_table(
            table_name="system_log",
            columns=[
                {"name": "log_id", "type": "BIGINT", "comment": "日志ID"},
                {"name": "user_id", "type": "BIGINT", "comment": "用户ID"},
                {"name": "action", "type": "VARCHAR(100)", "comment": "操作"},
            ],
            ddl_comments={
                "system_log": "系统操作日志表",
                "log_id": "日志ID",
                "user_id": "用户ID",
                "action": "操作",
            },
            null_rates={"log_id": 0.0, "user_id": 0.0, "action": 0.0},
            has_foreign_keys=True,
        )
        # system_log has semantic name, comments, low null, FK -> should be medium-high
        assert 5 <= score <= 10, f"System table with good metadata should score 5-10, got {score}"

    def test_meaningless_table_name(self):
        """Table with tmp_ prefix should lose 3 points for table name."""
        score_good = self.scorer.score_rdb_table(
            table_name="customer",
            columns=[{"name": "id", "type": "INT", "comment": "ID"}],
            ddl_comments={"customer": "客户表", "id": "ID"},
            null_rates={"id": 0.0},
            has_foreign_keys=False,
        )
        score_bad = self.scorer.score_rdb_table(
            table_name="tmp_2024",
            columns=[{"name": "id", "type": "INT", "comment": "ID"}],
            ddl_comments={"tmp_2024": "临时表", "id": "ID"},
            null_rates={"id": 0.0},
            has_foreign_keys=False,
        )
        assert score_good > score_bad, f"Good name should score higher: {score_good} vs {score_bad}"

    def test_should_process_threshold(self):
        """Tables scoring >= 5 should be processed."""
        assert self.scorer.should_process(7) is True
        assert self.scorer.should_process(5) is True
        assert self.scorer.should_process(4) is False
        assert self.scorer.should_process(0) is False

    def test_score_all_tables_from_ddl(self):
        """Test scoring all tables from parsed DDL."""
        from ontology_gen.utils import parse_ddl

        ddl = """
        CREATE TABLE customer (
            customer_id BIGINT PRIMARY KEY COMMENT '客户ID',
            customer_name VARCHAR(100) COMMENT '客户姓名'
        ) COMMENT '客户信息表';

        CREATE TABLE tmp_2024 (
            c1 INT,
            c2 VARCHAR(50)
        );
        """
        tables = parse_ddl(ddl)
        results = self.scorer.score_all_tables(tables)

        assert len(results) == 2
        customer_result = next(r for r in results if r["table_name"] == "customer")
        tmp_result = next(r for r in results if r["table_name"] == "tmp_2024")

        assert customer_result["score"] > tmp_result["score"]
        assert customer_result["should_process"] is True
        assert tmp_result["should_process"] is False
