from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Tuple

from kubernetes import client, config
from kubernetes.client import CoreV1Api, CustomObjectsApi
from kubernetes.config.config_exception import ConfigException

logger = logging.getLogger(__name__)


def load_clients(
    context: Optional[str] = None,
    kubeconfig: Optional[str] = None,
) -> Tuple[CoreV1Api, Optional[CustomObjectsApi]]:
    """Load Kubernetes API clients.

    Tries KUBECONFIG/local file first, then in-cluster config.
    """
    try:
        config.load_kube_config(config_file=kubeconfig, context=context)
        logger.info("Loaded kubeconfig (context=%s, file=%s)", context, kubeconfig)
    except ConfigException:
        logger.info("Falling back to in-cluster configuration")
        try:
            config.load_incluster_config()
        except ConfigException as exc:
            raise RuntimeError(
                "Failed to load Kubernetes configuration. "
                "Ensure KUBECONFIG is set or you are running inside a cluster."
            ) from exc

    core = client.CoreV1Api()

    # metrics.k8s.io is optional; CustomObjectsApi can still be constructed.
    custom: Optional[CustomObjectsApi]
    try:
        custom = client.CustomObjectsApi()
    except Exception:  # pragma: no cover - extremely unlikely
        custom = None

    return core, custom


def list_pods(
    core: CoreV1Api,
    namespaces: Optional[Iterable[str]] = None,
) -> List[client.V1Pod]:
    """List pods across the cluster or a subset of namespaces."""
    pods: List[client.V1Pod] = []

    if namespaces:
        for ns in namespaces:
            try:
                resp = core.list_namespaced_pod(ns)
                pods.extend(resp.items)
            except Exception as exc:
                logger.warning("Failed to list pods in namespace %s: %s", ns, exc)
    else:
        try:
            resp = core.list_pod_for_all_namespaces()
            pods.extend(resp.items)
        except Exception as exc:
            logger.error("Failed to list pods for all namespaces: %s", exc)
            raise

    return pods


