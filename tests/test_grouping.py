from __future__ import annotations

from dataclasses import dataclass

from kube_cost_lite.report import workload_key_for_pod


@dataclass
class OwnerRef:
    kind: str
    name: str


@dataclass
class Meta:
    namespace: str
    name: str
    owner_references: list[OwnerRef] | None = None


@dataclass
class Pod:
    metadata: Meta
    spec: object = None
    status: object = None


def test_workload_key_deployment_from_replicaset() -> None:
    pod = Pod(
        metadata=Meta(
            namespace="default",
            name="my-app-abc123",
            owner_references=[OwnerRef(kind="ReplicaSet", name="my-app-abc123")],
        )
    )
    ns, workload = workload_key_for_pod(pod)  # type: ignore[arg-type]
    assert ns == "default"
    assert workload == "Deployment/my-app"


def test_workload_key_cronjob_from_job() -> None:
    pod = Pod(
        metadata=Meta(
            namespace="jobs",
            name="nightly-backup-12345",
            owner_references=[OwnerRef(kind="Job", name="nightly-backup-12345")],
        )
    )
    ns, workload = workload_key_for_pod(pod)  # type: ignore[arg-type]
    assert ns == "jobs"
    assert workload == "CronJob/nightly-backup"


def test_workload_key_standalone() -> None:
    pod = Pod(metadata=Meta(namespace="misc", name="debug-pod", owner_references=None))
    ns, workload = workload_key_for_pod(pod)  # type: ignore[arg-type]
    assert ns == "misc"
    assert workload == "standalone/debug-pod"


