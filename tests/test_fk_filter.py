"""Tests for Algorithm 4.3: FK business semantic filtering (3-layer rules)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.stage4_relation.fk_filter import ForeignKeyFilter


class TestForeignKeyFilter:
    """Test 3-layer FK filtering rules."""

    def setup_method(self):
        self.table_tags = {
            "system_log": "system",
            "tmp_2024": "system",
            "customer": "business",
            "order": "business",
        }
        self.query_log = [
            "SELECT * FROM customer WHERE customer_type = 'VIP'",
            "SELECT c.customer_name, o.total_amount FROM customer c JOIN `order` o ON c.customer_id = o.customer_id",
            "SELECT * FROM `order` WHERE status = 'paid'",
        ]
        self.business_terms = ["客户", "顾客", "订单", "商品", "产品"]
        self.filter = ForeignKeyFilter(self.table_tags)

    def test_system_table_rejected(self):
        """Rule 1: FK from system table should be rejected."""
        fk_info = {
            "fk_table": "system_log",
            "fk_column": "user_id",
            "ref_table": "customer",
            "ref_column": "customer_id",
        }
        result = self.filter.filter(fk_info, self.table_tags, self.query_log, self.business_terms)
        assert result["status"] == "rejected"
        assert result["is_business_relation"] is False
        assert "system" in result["reason"].lower()

    def test_business_fk_accepted(self):
        """FK between business tables should be accepted."""
        fk_info = {
            "fk_table": "order",
            "fk_column": "customer_id",
            "ref_table": "customer",
            "ref_column": "customer_id",
        }
        result = self.filter.filter(fk_info, self.table_tags, self.query_log, self.business_terms)
        assert result["status"] in ("accepted", "needs_review")
        assert result["is_business_relation"] is True or result["status"] == "needs_review"

    def test_system_table_by_pattern(self):
        """Table with 'log' in name should be detected as system table."""
        fk_info = {
            "fk_table": "audit_trail",
            "fk_column": "user_id",
            "ref_table": "customer",
            "ref_column": "customer_id",
        }
        result = self.filter.filter(fk_info, {}, self.query_log, self.business_terms)
        assert result["status"] == "rejected"

    def test_no_business_terms_rejected(self):
        """FK between tables with no business terms should be rejected."""
        fk_info = {
            "fk_table": "config_table",
            "fk_column": "setting_id",
            "ref_table": "config_setting",
            "ref_column": "id",
        }
        result = self.filter.filter(fk_info, {}, [], self.business_terms)
        assert result["status"] == "rejected"

    def test_filter_all(self):
        """Test batch filtering of multiple FKs."""
        fk_list = [
            {"fk_table": "system_log", "fk_column": "user_id", "ref_table": "customer", "ref_column": "customer_id"},
            {"fk_table": "order", "fk_column": "customer_id", "ref_table": "customer", "ref_column": "customer_id"},
        ]
        results = self.filter.filter_all(fk_list, self.table_tags, self.query_log, self.business_terms)
        assert len(results) == 2
        # system_log FK should be rejected
        assert results[0]["result"]["status"] == "rejected"
        # order FK should be accepted or needs_review
        assert results[1]["result"]["status"] in ("accepted", "needs_review")
