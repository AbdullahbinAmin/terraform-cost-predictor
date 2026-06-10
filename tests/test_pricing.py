"""Tests for the AWS pricing engine."""

import pytest
from internal.pricing.aws_pricing import PricingEngine, CostEstimate


class TestPricingEngine:
    def setup_method(self):
        self.engine = PricingEngine()

    # ─── EC2 ──────────────────────────────────────────────────────────────────

    def test_ec2_known_instance_type(self):
        result = self.engine.estimate("aws_instance", {"instance_type": "t3.medium"}, "aws_instance.web")
        assert result.monthly_cost > 0
        assert result.confidence == "high"
        assert "ec2_instance" in result.breakdown

    def test_ec2_with_root_volume(self):
        result = self.engine.estimate(
            "aws_instance",
            {
                "instance_type": "t3.medium",
                "root_block_device": [{"volume_type": "gp3", "volume_size": 50}],
            },
            "aws_instance.web",
        )
        # Should include EBS cost
        assert result.breakdown.get("ebs_root_volume", 0) > 0

    def test_ec2_unknown_instance_type_uses_default(self):
        result = self.engine.estimate(
            "aws_instance", {"instance_type": "custom.xlarge"}, "aws_instance.web"
        )
        assert result.monthly_cost > 0
        assert result.confidence == "medium"

    def test_ec2_missing_instance_type_uses_default(self):
        result = self.engine.estimate("aws_instance", {}, "aws_instance.web")
        assert result.monthly_cost > 0

    # ─── RDS ──────────────────────────────────────────────────────────────────

    def test_rds_basic(self):
        result = self.engine.estimate(
            "aws_db_instance",
            {"instance_class": "db.t3.micro", "allocated_storage": 20, "storage_type": "gp2"},
            "aws_db_instance.main",
        )
        assert result.monthly_cost > 0
        assert "storage" in result.breakdown

    def test_rds_multi_az_doubles_cost(self):
        single = self.engine.estimate(
            "aws_db_instance",
            {"instance_class": "db.t3.micro", "allocated_storage": 20, "multi_az": False},
            "addr",
        )
        multi = self.engine.estimate(
            "aws_db_instance",
            {"instance_class": "db.t3.micro", "allocated_storage": 20, "multi_az": True},
            "addr",
        )
        # Multi-AZ should be more expensive
        assert multi.monthly_cost > single.monthly_cost

    # ─── Load Balancer ────────────────────────────────────────────────────────

    def test_alb_estimate(self):
        result = self.engine.estimate(
            "aws_lb", {"load_balancer_type": "application"}, "aws_lb.main"
        )
        assert result.monthly_cost > 0

    def test_aws_alb_alias(self):
        result = self.engine.estimate("aws_alb", {"load_balancer_type": "application"}, "addr")
        assert result.monthly_cost > 0

    # ─── NAT Gateway ─────────────────────────────────────────────────────────

    def test_nat_gateway(self):
        result = self.engine.estimate("aws_nat_gateway", {}, "aws_nat_gateway.main")
        assert result.monthly_cost > 0

    # ─── EBS ─────────────────────────────────────────────────────────────────

    def test_ebs_gp3(self):
        result = self.engine.estimate(
            "aws_ebs_volume", {"type": "gp3", "size": 100}, "aws_ebs_volume.data"
        )
        # 100GB gp3 = 100 * 0.08 = $8
        assert abs(result.monthly_cost - 8.0) < 1.0

    def test_ebs_io1_with_iops(self):
        result = self.engine.estimate(
            "aws_ebs_volume",
            {"type": "io1", "size": 100, "iops": 3000},
            "aws_ebs_volume.fast",
        )
        # Should include storage + IOPS cost
        assert result.breakdown.get("iops", 0) > 0

    # ─── S3 ───────────────────────────────────────────────────────────────────

    def test_s3_bucket(self):
        result = self.engine.estimate("aws_s3_bucket", {}, "aws_s3_bucket.assets")
        assert result.monthly_cost > 0
        assert result.confidence == "low"

    # ─── ElastiCache ─────────────────────────────────────────────────────────

    def test_elasticache_single_node(self):
        result = self.engine.estimate(
            "aws_elasticache_cluster",
            {"node_type": "cache.t3.medium", "num_cache_nodes": 1},
            "aws_elasticache_cluster.cache",
        )
        assert result.monthly_cost > 0

    def test_elasticache_multiple_nodes(self):
        single = self.engine.estimate(
            "aws_elasticache_cluster",
            {"node_type": "cache.t3.medium", "num_cache_nodes": 1},
            "addr",
        )
        triple = self.engine.estimate(
            "aws_elasticache_cluster",
            {"node_type": "cache.t3.medium", "num_cache_nodes": 3},
            "addr",
        )
        assert abs(triple.monthly_cost - single.monthly_cost * 3) < 0.01

    # ─── Lambda ──────────────────────────────────────────────────────────────

    def test_lambda_estimate(self):
        result = self.engine.estimate(
            "aws_lambda_function",
            {"memory_size": 512, "timeout": 30},
            "aws_lambda_function.handler",
        )
        assert result.monthly_cost > 0
        assert result.confidence == "low"

    # ─── Unsupported Resource ─────────────────────────────────────────────────

    def test_unsupported_resource_returns_zero(self):
        result = self.engine.estimate(
            "aws_security_group", {"name": "my-sg"}, "aws_security_group.sg"
        )
        assert result.monthly_cost == 0.0
        assert result.confidence == "unknown"

    # ─── EKS, Route53, SQS ───────────────────────────────────────────────────

    def test_eks_cluster(self):
        result = self.engine.estimate("aws_eks_cluster", {}, "aws_eks_cluster.prod")
        assert result.monthly_cost == 73.0

    def test_route53_zone(self):
        result = self.engine.estimate("aws_route53_zone", {"name": "example.com"}, "addr")
        assert result.monthly_cost == 0.50

    def test_sqs_standard(self):
        result = self.engine.estimate(
            "aws_sqs_queue", {"fifo_queue": False}, "aws_sqs_queue.jobs"
        )
        assert result.monthly_cost > 0

    def test_sqs_fifo_more_expensive(self):
        standard = self.engine.estimate("aws_sqs_queue", {"fifo_queue": False}, "addr")
        fifo = self.engine.estimate("aws_sqs_queue", {"fifo_queue": True}, "addr")
        assert fifo.monthly_cost > standard.monthly_cost
