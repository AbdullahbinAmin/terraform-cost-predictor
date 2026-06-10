"""
AWS Pricing Engine

Loads the static pricing database and estimates monthly costs for
parsed Terraform resource changes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to the bundled pricing database
PRICING_DB_PATH = Path(__file__).parent / "pricing_db.json"

# Hours in a month (30.44 days average)
HOURS_PER_MONTH = 730.0


@dataclass
class CostEstimate:
    """Cost estimate for a single resource."""

    resource_address: str
    resource_type: str
    monthly_cost: float
    currency: str = "USD"
    confidence: str = "medium"  # high | medium | low | unknown
    breakdown: dict[str, float] = None  # component costs
    notes: list[str] = None
    is_estimated: bool = True

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}
        if self.notes is None:
            self.notes = []

    @property
    def formatted_cost(self) -> str:
        return f"${self.monthly_cost:,.2f}"


class PricingEngine:
    """
    Core pricing engine. Loads the pricing DB and estimates costs
    for each ResourceChange.
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or PRICING_DB_PATH
        self._db: dict[str, Any] = {}
        self._load_db()

    def _load_db(self) -> None:
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"Pricing database not found at {self._db_path}. Please reinstall the package."
            )
        with open(self._db_path, encoding="utf-8") as f:
            self._db = json.load(f)
        logger.debug("Pricing DB loaded from %s", self._db_path)

    def estimate(
        self, resource_type: str, config: dict[str, Any], address: str = ""
    ) -> CostEstimate:
        """
        Estimate the monthly cost for a resource.

        Args:
            resource_type: Terraform resource type (e.g., "aws_instance")
            config:        The resource's `after` config dict from the plan
            address:       Full resource address for labeling

        Returns:
            CostEstimate with monthly_cost and breakdown
        """
        handler = self._get_handler(resource_type)
        if handler is None:
            return CostEstimate(
                resource_address=address,
                resource_type=resource_type,
                monthly_cost=0.0,
                confidence="unknown",
                notes=["Resource type not supported — cost not estimated"],
            )
        return handler(resource_type, config, address)

    def _get_handler(self, resource_type: str):
        """Return the appropriate handler method for a resource type."""
        handlers = {
            "aws_instance": self._estimate_ec2,
            "aws_db_instance": self._estimate_rds,
            "aws_rds_cluster": self._estimate_rds_cluster,
            "aws_lb": self._estimate_lb,
            "aws_alb": self._estimate_lb,
            "aws_nat_gateway": self._estimate_nat_gateway,
            "aws_ebs_volume": self._estimate_ebs,
            "aws_s3_bucket": self._estimate_s3,
            "aws_elasticache_cluster": self._estimate_elasticache,
            "aws_elasticache_replication_group": self._estimate_elasticache,
            "aws_lambda_function": self._estimate_lambda,
            "aws_eks_cluster": self._estimate_eks,
            "aws_ecs_service": self._estimate_ecs,
            "aws_cloudfront_distribution": self._estimate_cloudfront,
            "aws_elasticsearch_domain": self._estimate_elasticsearch,
            "aws_opensearch_domain": self._estimate_elasticsearch,
            "aws_kinesis_stream": self._estimate_kinesis,
            "aws_sqs_queue": self._estimate_sqs,
            "aws_sns_topic": self._estimate_sns,
            "aws_api_gateway_rest_api": self._estimate_api_gateway,
            "aws_api_gateway_v2_api": self._estimate_api_gateway_v2,
            "aws_wafv2_web_acl": self._estimate_waf,
            "aws_route53_zone": self._estimate_route53,
        }
        return handlers.get(resource_type)

    # ─── EC2 ──────────────────────────────────────────────────────────────────

    def _estimate_ec2(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_instance", {})
        instance_type = config.get("instance_type", "t3.micro") or "t3.micro"
        pricing = db.get(instance_type) or db.get("_default", {"monthly": 36.50})
        monthly = pricing["monthly"]

        # EBS root volume — default 8 GB gp2
        root_block = config.get("root_block_device") or [{}]
        if isinstance(root_block, list):
            root_block = root_block[0] if root_block else {}
        root_size_gb = root_block.get("volume_size") or 8
        root_type = root_block.get("volume_type") or "gp2"
        ebs_db = self._db.get("aws_ebs_volume", {})
        ebs_pricing = ebs_db.get(root_type) or ebs_db.get("_default", {"per_gb_month": 0.10})
        ebs_cost = float(root_size_gb) * ebs_pricing["per_gb_month"]

        total = monthly + ebs_cost
        confidence = "high" if instance_type in db else "medium"

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(total, 2),
            confidence=confidence,
            breakdown={"ec2_instance": round(monthly, 2), "ebs_root_volume": round(ebs_cost, 2)},
            notes=[
                f"Instance type: {instance_type}",
                f"Root volume: {root_size_gb} GB {root_type}",
            ],
        )

    # ─── RDS ──────────────────────────────────────────────────────────────────

    def _estimate_rds(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_db_instance", {})
        instance_class = config.get("instance_class", "db.t3.micro") or "db.t3.micro"
        pricing = db.get(instance_class) or db.get("_default", {"monthly": 12.41})
        monthly = pricing["monthly"]

        # Multi-AZ doubles the compute cost
        multi_az = config.get("multi_az", False)
        if multi_az:
            monthly *= db.get("_multi_az_multiplier", 2.0)

        # Storage cost
        storage_gb = config.get("allocated_storage") or 20
        storage_type = config.get("storage_type") or "gp2"
        key = f"_storage_{storage_type}_per_gb_month"
        storage_price = db.get(key) or db.get("_storage_gp2_per_gb_month", 0.115)
        storage_cost = float(storage_gb) * storage_price

        total = monthly + storage_cost
        notes = [
            f"Instance class: {instance_class}",
            f"Storage: {storage_gb} GB {storage_type}",
        ]
        if multi_az:
            notes.append("Multi-AZ: enabled (2x compute cost)")

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(total, 2),
            confidence="high" if instance_class in db else "medium",
            breakdown={"rds_instance": round(monthly, 2), "storage": round(storage_cost, 2)},
            notes=notes,
        )

    def _estimate_rds_cluster(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_rds_cluster", {})
        engine = config.get("engine") or "aurora-mysql"
        engine_db = db.get(engine) or db.get("aurora-mysql", {})
        instance_db = engine_db.get("_instance_pricing", {})
        instance_class = config.get("instance_class") or "db.t3.medium"
        pricing = instance_db.get(instance_class) or instance_db.get("_default", {"monthly": 59.86})
        monthly = pricing["monthly"]

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            notes=[
                f"Aurora {engine}, instance: {instance_class}",
                "Storage billed per GB-month separately",
            ],
        )

    # ─── Load Balancer ────────────────────────────────────────────────────────

    def _estimate_lb(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_lb", {})
        lb_type = config.get("load_balancer_type") or "application"
        pricing = db.get(lb_type) or db.get("_default", {"estimated_monthly": 18.0})
        monthly = pricing.get("estimated_monthly", 18.0)

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            breakdown={
                "lb_hourly_base": pricing.get("monthly", 5.84),
                "lcu_estimate": round(monthly - pricing.get("monthly", 5.84), 2),
            },
            notes=[
                f"Type: {lb_type}",
                "LCU cost estimated at 1 LCU/hour average",
            ],
        )

    # ─── NAT Gateway ─────────────────────────────────────────────────────────

    def _estimate_nat_gateway(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_nat_gateway", {})
        base = db.get("monthly_base", 32.85)
        data_cost = db.get("estimated_data_gb_per_month", 100) * db.get(
            "data_processing_per_gb", 0.045
        )

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(base, 2),
            confidence="medium",
            breakdown={"hourly_charge": base, "data_processing": round(data_cost, 2)},
            notes=["Data processing cost varies; estimated 100 GB/month included"],
        )

    # ─── EBS Volume ──────────────────────────────────────────────────────────

    def _estimate_ebs(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_ebs_volume", {})
        vol_type = config.get("type") or "gp2"
        pricing = db.get(vol_type) or db.get("_default", {"per_gb_month": 0.10})
        size_gb = config.get("size") or 20
        monthly = float(size_gb) * pricing["per_gb_month"]

        # IOPS cost for io1/io2/gp3
        iops_cost = 0.0
        iops = config.get("iops")
        per_iops = pricing.get("per_iops_month")
        base_iops = pricing.get("base_iops", 0)
        if per_iops and iops:
            billable_iops = max(0, int(iops) - base_iops)
            iops_cost = billable_iops * per_iops
            monthly += iops_cost

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="high",
            breakdown={
                "storage": round(float(size_gb) * pricing["per_gb_month"], 2),
                "iops": round(iops_cost, 2),
            },
            notes=[f"Volume type: {vol_type}, Size: {size_gb} GB"],
        )

    # ─── S3 ───────────────────────────────────────────────────────────────────

    def _estimate_s3(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_s3_bucket", {})
        monthly = db.get("estimated_monthly", 2.30)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=["Cost depends on actual data stored; estimated 100 GB Standard"],
        )

    # ─── ElastiCache ─────────────────────────────────────────────────────────

    def _estimate_elasticache(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_elasticache_cluster", {})
        node_type = config.get("node_type") or config.get("node_groups", {})
        if isinstance(node_type, (list, dict)):
            node_type = "cache.t3.micro"
        node_type = node_type or "cache.t3.micro"
        pricing = db.get(node_type) or db.get("_default", {"monthly": 12.41})
        num_nodes = config.get("num_cache_nodes") or 1
        monthly = pricing["monthly"] * int(num_nodes)

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="high" if node_type in db else "medium",
            notes=[f"Node type: {node_type}", f"Nodes: {num_nodes}"],
        )

    # ─── Lambda ──────────────────────────────────────────────────────────────

    def _estimate_lambda(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_lambda_function", {})
        monthly = db.get("default_estimated_monthly", 5.00)
        memory = config.get("memory_size") or 128
        confidence = "low"
        note = f"Memory: {memory} MB. Cost depends on invocation count and duration."

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence=confidence,
            notes=[note, "Estimate: 1M invocations, 200ms avg @ configured memory"],
        )

    # ─── EKS ─────────────────────────────────────────────────────────────────

    def _estimate_eks(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_eks_cluster", {})
        monthly = db.get("monthly", 73.0)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="high",
            notes=["Control plane only. Worker node EC2 costs are separate."],
        )

    # ─── ECS ─────────────────────────────────────────────────────────────────

    def _estimate_ecs(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_ecs_service", {})
        monthly = db.get("estimated_monthly", 14.26)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=[
                "Fargate estimate: 0.25 vCPU, 0.5 GB, 24/7. Update task definition for accuracy."
            ],
        )

    # ─── CloudFront ──────────────────────────────────────────────────────────

    def _estimate_cloudfront(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_cloudfront_distribution", {})
        monthly = db.get("estimated_monthly", 10.0)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=["Estimate: 100 GB/month data transfer. Actual cost depends on traffic."],
        )

    # ─── Elasticsearch / OpenSearch ──────────────────────────────────────────

    def _estimate_elasticsearch(
        self, resource_type: str, config: dict, address: str
    ) -> CostEstimate:
        db = self._db.get("aws_elasticsearch_domain", {})
        instance_type = config.get("instance_type") or config.get("cluster_config", {})
        if isinstance(instance_type, dict):
            instance_type = instance_type.get("instance_type", "t3.small.search")
        instance_type = instance_type or "t3.small.search"
        pricing = db.get(instance_type) or db.get("_default", {"monthly": 26.28})
        monthly = pricing["monthly"]

        ebs_size = None
        ebs_conf = config.get("ebs_options")
        if isinstance(ebs_conf, (list, dict)):
            if isinstance(ebs_conf, list):
                ebs_conf = ebs_conf[0] if ebs_conf else {}
            ebs_size = ebs_conf.get("volume_size")
        if ebs_size:
            monthly += float(ebs_size) * db.get("_storage_per_gb_month", 0.135)

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            notes=[f"Instance: {instance_type}"],
        )

    # ─── Kinesis ─────────────────────────────────────────────────────────────

    def _estimate_kinesis(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_kinesis_stream", {})
        shards = config.get("shard_count") or 1
        monthly = db.get("estimated_monthly_per_shard", 10.95) * int(shards)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            notes=[f"Shards: {shards}"],
        )

    # ─── SQS ─────────────────────────────────────────────────────────────────

    def _estimate_sqs(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_sqs_queue", {})
        fifo = config.get("fifo_queue", False)
        key = "per_million_requests_fifo" if fifo else "per_million_requests_standard"
        monthly = db.get(key, 0.40)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=[
                f"Type: {'FIFO' if fifo else 'Standard'}",
                "Estimate: 1M requests/month (free tier excluded)",
            ],
        )

    # ─── SNS ─────────────────────────────────────────────────────────────────

    def _estimate_sns(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_sns_topic", {})
        monthly = db.get("estimated_monthly", 1.0)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=["Estimate: 1M publishes/month"],
        )

    # ─── API Gateway ──────────────────────────────────────────────────────────

    def _estimate_api_gateway(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_api_gateway_rest_api", {})
        monthly = db.get("estimated_monthly", 3.50)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=["REST API. Estimate: 1M API calls/month"],
        )

    def _estimate_api_gateway_v2(
        self, resource_type: str, config: dict, address: str
    ) -> CostEstimate:
        db = self._db.get("aws_api_gateway_v2_api", {})
        monthly = db.get("estimated_monthly", 1.0)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=["HTTP API (cheaper than REST). Estimate: 1M API calls/month"],
        )

    # ─── WAF ──────────────────────────────────────────────────────────────────

    def _estimate_waf(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_wafv2_web_acl", {})
        rules = config.get("rule") or []
        rule_count = len(rules) if isinstance(rules, list) else 5
        monthly = (
            db.get("web_acl_per_month", 5.0)
            + rule_count * db.get("per_rule_per_month", 1.0)
            + db.get("per_million_requests", 0.60)
        )
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            notes=[f"Rules: {rule_count}", "Request cost estimated at 1M/month"],
        )

    # ─── Route53 ─────────────────────────────────────────────────────────────

    def _estimate_route53(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        db = self._db.get("aws_route53_zone", {})
        monthly = db.get("hosted_zone_per_month", 0.50)
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="high",
            notes=["Per-hosted-zone charge. Query costs are separate."],
        )
