from __future__ import annotations

import logging
import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from kubernetes import client as k8s_client

from .config import AppConfig
from .cost_model import CostBreakdown, compute_monthly_cost_from_requests
from .metrics import PodContainerUsage, UsageKey

logger = logging.getLogger(__name__)


@dataclass
class NamespaceSummary:
    namespace: str
    cpu_vcpu: float
    mem_gib: float
    monthly_cpu_usd: float
    monthly_mem_usd: float
    monthly_total_usd: float
    defaulted_ratio: float  # 0–1

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["defaulted_percent"] = self.defaulted_ratio * 100.0
        return d


@dataclass
class WorkloadSummary:
    workload: str  # kind/name
    namespace: str
    monthly_total_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReportResult:
    namespaces: List[NamespaceSummary]
    workloads: List[WorkloadSummary]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespaces": [ns.to_dict() for ns in self.namespaces],
            "workloads": [wl.to_dict() for wl in self.workloads],
        }


def _parse_cpu_request_millicores(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    v = value.strip()
    if v.endswith("m"):
        return float(v[:-1])
    # Assume cores
    return float(v) * 1000.0


def _parse_memory_request_bytes(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    v = value.strip()
    # Handle simple suffixes
    units = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
    }
    for suffix, mult in units.items():
        if v.endswith(suffix):
            return float(v[: -len(suffix)]) * mult
    # Assume bytes if no suffix
    return float(v)


def is_system_namespace(ns: str, cfg: AppConfig) -> bool:
    if ns in cfg.behavior.system_namespaces:
        return True
    if ns.startswith("kube-"):
        return True
    return False


def workload_key_for_pod(
    pod: k8s_client.V1Pod,
) -> Tuple[str, str]:
    """Return (namespace, workload_id) for a pod.

    Workload id is a human-readable identifier such as:
    - Deployment/my-app
    - StatefulSet/db
    - CronJob/nightly-backup
    - Job/manual-run
    - standalone/pod-name
    """
    ns = pod.metadata.namespace or "default"
    name = pod.metadata.name or "unknown"
    owners = pod.metadata.owner_references or []

    if not owners:
        return ns, f"standalone/{name}"

    owner = owners[0]
    kind = owner.kind or "Unknown"
    oname = owner.name or name

    # Heuristics to map ReplicaSet -> Deployment and Job -> CronJob
    if kind == "ReplicaSet":
        base = _strip_suffix_after_last_dash(oname)
        return ns, f"Deployment/{base}"

    if kind == "Job":
        base = _strip_job_suffix(oname)
        if base != oname:
            return ns, f"CronJob/{base}"
        return ns, f"Job/{oname}"

    if kind in {"StatefulSet", "DaemonSet"}:
        return ns, f"{kind}/{oname}"

    return ns, f"{kind}/{oname}"


def _strip_suffix_after_last_dash(name: str) -> str:
    # Rough heuristic: my-deploy-abcdef123 -> my-deploy
    if "-" not in name:
        return name
    base, _sep, _rest = name.rpartition("-")
    return base or name


def _strip_job_suffix(name: str) -> str:
    # CronJob job names are usually <cronjob-name>-<timestamp>
    base, sep, rest = name.rpartition("-")
    if not sep:
        return name
    if rest.isdigit():
        return base
    return name


def generate_report(
    pods: Iterable[k8s_client.V1Pod],
    config: AppConfig,
    include_system_namespaces: bool,
    namespace_filter: Optional[Iterable[str]] = None,
    usage: Optional[Dict[UsageKey, PodContainerUsage]] = None,
    sort_by: str = "total",
    top_workloads: int = 10,
) -> ReportResult:
    """Generate a report from a set of pods.

    This operates purely on pod objects to keep the core logic reusable
    for both CLI and HTTP server.
    """
    ns_filter_set = set(namespace_filter or [])
    usage = usage or {}

    # Aggregation maps
    ns_cpu_m: Dict[str, float] = {}
    ns_mem_b: Dict[str, float] = {}
    ns_defaulted: Dict[str, int] = {}
    ns_total_containers: Dict[str, int] = {}

    wl_costs: Dict[Tuple[str, str], float] = {}

    def add_ns(ns: str, cpu_m: float, mem_b: float, defaulted_containers: int, containers: int) -> None:
        ns_cpu_m[ns] = ns_cpu_m.get(ns, 0.0) + cpu_m
        ns_mem_b[ns] = ns_mem_b.get(ns, 0.0) + mem_b
        ns_defaulted[ns] = ns_defaulted.get(ns, 0) + defaulted_containers
        ns_total_containers[ns] = ns_total_containers.get(ns, 0) + containers

    for pod in pods:
        ns = pod.metadata.namespace or "default"
        phase = (pod.status.phase or "").lower() if pod.status and pod.status.phase else ""

        if not include_system_namespaces and is_system_namespace(ns, config):
            continue

        if ns_filter_set and ns not in ns_filter_set:
            continue

        if phase == "succeeded" and not config.behavior.include_completed_pods:
            continue

        containers = list(pod.spec.containers or [])
        if not containers:
            continue

        pod_cpu_m = 0.0
        pod_mem_b = 0.0
        defaulted_cont = 0

        for c in containers:
            reqs = (c.resources.requests or {}) if c.resources else {}
            raw_cpu = reqs.get("cpu")
            raw_mem = reqs.get("memory")

            cpu_m = _parse_cpu_request_millicores(raw_cpu)
            mem_b = _parse_memory_request_bytes(raw_mem)

            used_default = False

            if cpu_m is None:
                cpu_m = float(config.defaults.cpu_millicores)
                used_default = True
            if mem_b is None:
                mem_b = float(config.defaults.memory_mib) * 1024 * 1024
                used_default = True

            if used_default:
                defaulted_cont += 1

            pod_cpu_m += cpu_m
            pod_mem_b += mem_b

        add_ns(ns, pod_cpu_m, pod_mem_b, defaulted_cont, len(containers))

        # Workload aggregation (request-based)
        ns_key, wl_key = workload_key_for_pod(pod)
        breakdown = compute_monthly_cost_from_requests(pod_cpu_m, pod_mem_b, config)
        wl_costs[(ns_key, wl_key)] = wl_costs.get((ns_key, wl_key), 0.0) + breakdown.monthly_total_usd

    # Build namespace summaries
    ns_summaries: List[NamespaceSummary] = []
    for ns, cpu_m in ns_cpu_m.items():
        mem_b = ns_mem_b.get(ns, 0.0)
        breakdown = compute_monthly_cost_from_requests(cpu_m, mem_b, config)
        total_cont = ns_total_containers.get(ns, 0) or 1
        defaulted = ns_defaulted.get(ns, 0)
        defaulted_ratio = defaulted / float(total_cont)

        ns_summaries.append(
            NamespaceSummary(
                namespace=ns,
                cpu_vcpu=breakdown.cpu_vcpu,
                mem_gib=breakdown.mem_gib,
                monthly_cpu_usd=breakdown.monthly_cpu_usd,
                monthly_mem_usd=breakdown.monthly_mem_usd,
                monthly_total_usd=breakdown.monthly_total_usd,
                defaulted_ratio=defaulted_ratio,
            )
        )

    # Sort namespaces
    key_map = {
        "total": lambda n: n.monthly_total_usd,
        "cpu": lambda n: n.monthly_cpu_usd,
        "mem": lambda n: n.monthly_mem_usd,
        "defaulted": lambda n: n.defaulted_ratio,
    }
    key_fn = key_map.get(sort_by, key_map["total"])
    ns_summaries.sort(key=key_fn, reverse=True)

    wl_summaries: List[WorkloadSummary] = [
        WorkloadSummary(workload=wl, namespace=ns, monthly_total_usd=cost)
        for (ns, wl), cost in wl_costs.items()
    ]
    wl_summaries.sort(key=lambda w: w.monthly_total_usd, reverse=True)
    if top_workloads > 0:
        wl_summaries = wl_summaries[:top_workloads]

    return ReportResult(namespaces=ns_summaries, workloads=wl_summaries)


