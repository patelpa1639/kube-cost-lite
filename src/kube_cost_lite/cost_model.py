from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any

from .config import AppConfig


@dataclass
class CostBreakdown:
    cpu_vcpu: float
    mem_gib: float
    monthly_cpu_usd: float
    monthly_mem_usd: float

    @property
    def monthly_total_usd(self) -> float:
        return self.monthly_cpu_usd + self.monthly_mem_usd

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["monthly_total_usd"] = self.monthly_total_usd
        return d


def cpu_millicores_to_vcpu(cpu_millicores: float) -> float:
    return cpu_millicores / 1000.0


def memory_bytes_to_gib(memory_bytes: float) -> float:
    return memory_bytes / (1024.0**3)


def compute_monthly_cost_from_requests(
    cpu_millicores: float,
    memory_bytes: float,
    config: AppConfig,
) -> CostBreakdown:
    """Compute monthly cost from resource *requests*.

    This is intentionally simple and transparent, using the formulas:

    - vcpu = cpu_millicores / 1000
    - cpu_cost = vcpu * hours_per_month * cpu_per_vcpu_hour_usd
    - mem_gb = memory_bytes / (1024^3)
    - mem_cost = mem_gb * hours_per_month * mem_per_gb_hour_usd
    """
    pricing = config.pricing

    vcpu = cpu_millicores_to_vcpu(cpu_millicores)
    mem_gib = memory_bytes_to_gib(memory_bytes)

    monthly_cpu = vcpu * pricing.hours_per_month * pricing.cpu_per_vcpu_hour_usd
    monthly_mem = mem_gib * pricing.hours_per_month * pricing.mem_per_gb_hour_usd

    return CostBreakdown(
        cpu_vcpu=vcpu,
        mem_gib=mem_gib,
        monthly_cpu_usd=monthly_cpu,
        monthly_mem_usd=monthly_mem,
    )


