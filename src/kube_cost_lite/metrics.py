from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from kubernetes.client import CustomObjectsApi

logger = logging.getLogger(__name__)


@dataclass
class PodContainerUsage:
    cpu_millicores: float
    memory_bytes: float


UsageKey = Tuple[str, str, str]  # (namespace, pod_name, container_name)


def _parse_quantity_to_millicores(value: str) -> float:
    # Metrics API returns cpu like "50m" or "0.05"; we keep this simple.
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000.0


def _parse_quantity_to_bytes(value: str) -> float:
    # Very small parser for values like "128974848Ki", "100Mi", "1Gi"
    suffixes = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
    }
    for suffix, mult in suffixes.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * mult
    # Assume bytes
    return float(value)


def get_pod_usage(
    custom: Optional[CustomObjectsApi],
) -> Dict[UsageKey, PodContainerUsage]:
    """Fetch pod usage via metrics-server if available.

    Returns a mapping keyed by (namespace, pod_name, container_name).
    If the metrics API is not reachable, returns an empty dict and logs a warning.
    """
    if custom is None:
        logger.info("CustomObjectsApi is not available; skipping usage metrics.")
        return {}

    try:
        resp = custom.list_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="pods",
        )
    except Exception as exc:
        logger.warning(
            "Failed to query metrics.k8s.io (metrics-server likely missing). "
            "Proceeding without usage-based estimates. Error: %s",
            exc,
        )
        return {}

    results: Dict[UsageKey, PodContainerUsage] = {}

    items = resp.get("items", [])
    for item in items:
        meta = item.get("metadata", {})
        ns = meta.get("namespace")
        pod_name = meta.get("name")
        for c in item.get("containers", []):
            cname = c.get("name")
            usage = c.get("usage", {})
            cpu_raw = usage.get("cpu")
            mem_raw = usage.get("memory")
            if not (ns and pod_name and cname and cpu_raw and mem_raw):
                continue
            try:
                cpu_m = _parse_quantity_to_millicores(cpu_raw)
                mem_b = _parse_quantity_to_bytes(mem_raw)
            except Exception:
                continue
            results[(ns, pod_name, cname)] = PodContainerUsage(
                cpu_millicores=cpu_m,
                memory_bytes=mem_b,
            )

    return results


