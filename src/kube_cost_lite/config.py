from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


class PricingConfig(BaseModel):
    """Unit pricing configuration.

    All values are in USD.
    """

    hours_per_month: float = Field(
        default=730.0,
        description="Number of hours per month used for cost projection.",
    )
    cpu_per_vcpu_hour_usd: float = Field(
        default=0.031611,
        description="Price per vCPU-hour in USD.",
    )
    mem_per_gb_hour_usd: float = Field(
        default=0.004237,
        description="Price per GB-hour of memory in USD.",
    )


class DefaultRequestsConfig(BaseModel):
    """Default requests to use when pods/containers do not specify resources."""

    cpu_millicores: int = Field(
        default=100,
        description="Default CPU request in millicores for containers missing requests.",
    )
    memory_mib: int = Field(
        default=128,
        description="Default memory request in MiB for containers missing requests.",
    )


class BehaviorConfig(BaseModel):
    include_completed_pods: bool = Field(
        default=False,
        description="Whether to include Completed pods in cost calculations.",
    )
    system_namespaces: List[str] = Field(
        default_factory=lambda: [
            "kube-system",
            "kube-public",
            "kube-node-lease",
            "kube-apiserver",
            "local-path-storage",
        ],
        description="Default list of system namespaces.",
    )


class AppConfig(BaseModel):
    """Top-level configuration model for kube-cost-lite."""

    pricing: PricingConfig = Field(default_factory=PricingConfig)
    defaults: DefaultRequestsConfig = Field(default_factory=DefaultRequestsConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)

    @classmethod
    def from_yaml(cls, path: Optional[str | Path]) -> "AppConfig":
        """Load configuration from a YAML file, or return defaults if path is None."""
        if path is None:
            return cls()

        cfg_path = Path(path)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config file not found: {cfg_path}")

        with cfg_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # pydantic will merge provided values with defaults.
        return cls.model_validate(data)


def sample_config_yaml() -> str:
    """Return a sample configuration YAML string."""
    cfg = AppConfig()
    as_dict = cfg.model_dump()
    header = (
        "# kube-cost-lite sample configuration\n"
        "# Prices and defaults are intentionally simple and should be adjusted\n"
        "# to match your environment and cloud provider.\n"
        "#\n"
        "# WARNING: This is an estimator, not a billing source of truth.\n\n"
    )
    return header + yaml.safe_dump(as_dict, sort_keys=False)


