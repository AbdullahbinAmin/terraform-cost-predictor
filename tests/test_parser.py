"""Tests for the Terraform plan parser."""

import json
import pytest
from pathlib import Path

from internal.parser.plan_parser import (
    PlanParser,
    PlanParseError,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_NO_OP,
    ACTION_REPLACE,
)


SAMPLE_PLAN = {
    "format_version": "1.1",
    "terraform_version": "1.6.4",
    "resource_changes": [
        {
            "address": "aws_instance.web",
            "type": "aws_instance",
            "name": "web",
            "module_address": "",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {
                    "instance_type": "t3.medium",
                    "ami": "ami-12345",
                },
                "after_unknown": {},
            },
        },
        {
            "address": "aws_db_instance.db",
            "type": "aws_db_instance",
            "name": "db",
            "module_address": "",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {
                "actions": ["delete"],
                "before": {"instance_class": "db.t3.micro", "allocated_storage": 20},
                "after": None,
                "after_unknown": {},
            },
        },
        {
            "address": "aws_security_group.sg",
            "type": "aws_security_group",
            "name": "sg",
            "module_address": "",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {
                "actions": ["no-op"],
                "before": {"name": "my-sg"},
                "after": {"name": "my-sg"},
                "after_unknown": {},
            },
        },
        {
            "address": "aws_instance.old",
            "type": "aws_instance",
            "name": "old",
            "module_address": "",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {
                "actions": ["delete", "create"],
                "before": {"instance_type": "t3.micro"},
                "after": {"instance_type": "t3.large"},
                "after_unknown": {},
            },
        },
    ],
    "configuration": {
        "provider_config": {
            "aws": {
                "name": "aws",
                "expressions": {"region": {"constant_value": "us-east-1"}},
            }
        }
    },
}


class TestPlanParser:
    def setup_method(self):
        self.parser = PlanParser()

    def test_parse_dict_basic(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        assert plan.terraform_version == "1.6.4"
        assert plan.format_version == "1.1"
        assert len(plan.resource_changes) == 4

    def test_parse_creates_resource_changes(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        addresses = [r.address for r in plan.resource_changes]
        assert "aws_instance.web" in addresses
        assert "aws_db_instance.db" in addresses

    def test_action_create(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        web = next(r for r in plan.resource_changes if r.name == "web")
        assert web.action == ACTION_CREATE

    def test_action_delete(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        db = next(r for r in plan.resource_changes if r.name == "db")
        assert db.action == ACTION_DELETE

    def test_action_no_op(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        sg = next(r for r in plan.resource_changes if r.name == "sg")
        assert sg.action == ACTION_NO_OP

    def test_action_replace(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        old = next(r for r in plan.resource_changes if r.name == "old")
        assert old.action == ACTION_REPLACE

    def test_supported_resource_detection(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        web = next(r for r in plan.resource_changes if r.name == "web")
        assert web.is_supported is True
        sg = next(r for r in plan.resource_changes if r.name == "sg")
        assert sg.is_supported is False

    def test_relevant_changes_excludes_noop(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        relevant = plan.relevant_changes
        assert all(r.action != ACTION_NO_OP for r in relevant)

    def test_created_resources_property(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        created = plan.created_resources
        assert all(r.action == ACTION_CREATE for r in created)

    def test_region_extracted_from_config(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        web = next(r for r in plan.resource_changes if r.name == "web")
        assert web.region == "us-east-1"

    def test_after_config_populated(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        web = next(r for r in plan.resource_changes if r.name == "web")
        assert web.after.get("instance_type") == "t3.medium"

    def test_before_config_populated_for_delete(self):
        plan = self.parser.parse_dict(SAMPLE_PLAN)
        db = next(r for r in plan.resource_changes if r.name == "db")
        assert db.before.get("instance_class") == "db.t3.micro"

    def test_parse_json_string(self):
        plan = self.parser.parse_json(json.dumps(SAMPLE_PLAN))
        assert len(plan.resource_changes) == 4

    def test_parse_invalid_json_raises(self):
        with pytest.raises(PlanParseError, match="Invalid JSON"):
            self.parser.parse_json("{not valid json}")

    def test_parse_wrong_structure_raises(self):
        with pytest.raises(PlanParseError):
            self.parser.parse_dict({"not": "a plan"})

    def test_parse_nonexistent_file_raises(self):
        with pytest.raises(PlanParseError, match="not found"):
            self.parser.parse_file("/nonexistent/plan.json")

    def test_parse_non_json_extension_raises(self, tmp_path):
        tf_file = tmp_path / "plan.tfplan"
        tf_file.write_text("{}")
        with pytest.raises(PlanParseError, match="JSON file"):
            self.parser.parse_file(tf_file)

    def test_parse_sample_file(self):
        sample_path = Path(__file__).parent.parent / "examples" / "sample_plan.json"
        if sample_path.exists():
            plan = self.parser.parse_file(sample_path)
            assert len(plan.resource_changes) > 0
