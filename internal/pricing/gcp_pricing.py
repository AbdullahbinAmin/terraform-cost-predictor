"""
GCP Pricing Engine

Fetches live pricing from the public GCP Cloud Pricing Calculator JSON API
and estimates costs for Google Cloud resources.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from internal.pricing.base import CloudPricingProvider, CostEstimate

logger = logging.getLogger(__name__)

# Public but undocumented GCP pricing JSON used by their calculator
GCP_PRICING_API = "https://cloudpricingcalculator.appspot.com/static/data/pricelist.json"


class GCPPricingEngine(CloudPricingProvider):
    """
    GCP pricing engine using the public cloudpricingcalculator JSON API.
    """

    def __init__(self):
        self._db: dict[str, Any] = {}
        self._loaded = False

    def _load_pricing(self):
        if self._loaded:
            return
        try:
            resp = requests.get(GCP_PRICING_API, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._db = data.get("gcp_price_list", {})
            self._loaded = True
        except Exception as e:
            logger.warning(f"Failed to fetch GCP pricing list: {e}")
            self._db = {}
            self._loaded = True  # Prevent retries

    def estimate(
        self, resource_type: str, config: dict[str, Any], address: str = ""
    ) -> CostEstimate:
        self._load_pricing()

        handler = self._get_handler(resource_type)
        if handler is None:
            return CostEstimate(
                resource_address=address,
                resource_type=resource_type,
                monthly_cost=0.0,
                confidence="unknown",
                notes=["GCP resource type not supported — cost not estimated"],
            )
        return handler(resource_type, config, address)

    def _get_handler(self, resource_type: str):
        handlers = {
            "google_compute_instance": self._estimate_compute,
            "google_compute_disk": self._estimate_disk,
            "google_sql_database_instance": self._estimate_sql,
            "google_storage_bucket": self._estimate_storage,
        }
        return handlers.get(resource_type)

    def _estimate_compute(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        machine_type = config.get("machine_type", "e2-medium")
        zone = config.get("zone", "us-central1-a")
        region = zone.rsplit("-", 1)[0] if "-" in zone else "us-central1"

        # Example lookup key in the undocumented API
        key = f"CP-COMPUTEENGINE-VMIMAGE-{machine_type.upper()}"
        pricing = self._db.get(key, {})

        # Look for region price, fallback to us
        hourly_price = pricing.get(region, pricing.get("us", 0.0))

        confidence = "high"
        if not hourly_price:
            hourly_price = 0.033  # fallback e2-medium roughly
            confidence = "low"
            notes = [f"Machine: {machine_type}", "Live price fetch failed, using fallback estimate"]
        else:
            notes = [f"Machine: {machine_type}", "Live price from GCP Calculator API"]

        monthly = hourly_price * 730.0

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence=confidence,
            notes=notes,
        )

    def _estimate_disk(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        disk_type = config.get("type", "pd-standard")
        size_gb = config.get("size") or 100

        # Rough estimates
        price_per_gb = 0.17 if "ssd" in disk_type else 0.04
        monthly = float(size_gb) * price_per_gb

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            notes=[f"Type: {disk_type}", f"Size: {size_gb} GB"],
        )

    def _estimate_sql(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        settings = config.get("settings", [{}])[0] if config.get("settings") else {}
        tier = settings.get("tier", "db-f1-micro")

        monthly = 9.00 if "micro" in tier else 50.00

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=[f"Tier: {tier}", "Estimated fallback cost"],
        )

    def _estimate_storage(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        storage_class = config.get("storage_class", "STANDARD")
        monthly = 2.00

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=[f"Class: {storage_class}", "Estimated base cost (data dependent)"],
        )
