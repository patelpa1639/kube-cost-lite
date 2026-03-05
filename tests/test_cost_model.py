from __future__ import annotations

from kube_cost_lite.config import AppConfig
from kube_cost_lite.cost_model import compute_monthly_cost_from_requests


def test_compute_monthly_cost_simple() -> None:
    cfg = AppConfig()

    # 1 vCPU, 1 GiB
    cpu_m = 1000.0
    mem_b = 1024.0**3

    result = compute_monthly_cost_from_requests(cpu_m, mem_b, cfg)

    pricing = cfg.pricing
    expected_cpu = 1.0 * pricing.hours_per_month * pricing.cpu_per_vcpu_hour_usd
    expected_mem = 1.0 * pricing.hours_per_month * pricing.mem_per_gb_hour_usd

    assert result.monthly_cpu_usd == expected_cpu
    assert result.monthly_mem_usd == expected_mem
    assert result.monthly_total_usd == expected_cpu + expected_mem


def test_zero_cost() -> None:
    cfg = AppConfig()
    result = compute_monthly_cost_from_requests(0.0, 0.0, cfg)
    assert result.monthly_cpu_usd == 0.0
    assert result.monthly_mem_usd == 0.0
    assert result.monthly_total_usd == 0.0


