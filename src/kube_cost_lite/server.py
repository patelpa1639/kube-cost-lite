from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import AppConfig
from .k8s_client import load_clients, list_pods
from .metrics import get_pod_usage
from .report import generate_report

logger = logging.getLogger(__name__)

app = FastAPI(title="kube-cost-lite", version="0.1.0")

# Allow a local React/Vite dev server to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/explain")
async def explain() -> dict:
    cfg = AppConfig()
    pricing = cfg.pricing
    defaults = cfg.defaults
    return {
        "model": "requests-based estimator",
        "formulas": {
            "hours_per_month": pricing.hours_per_month,
            "cpu": "vcpu = cpu_millicores / 1000; cpu_cost = vcpu * hours_per_month * cpu_per_vcpu_hour_usd",
            "memory": "mem_gb = memory_bytes / (1024^3); mem_cost = mem_gb * hours_per_month * mem_per_gb_hour_usd",
        },
        "pricing": {
            "cpu_per_vcpu_hour_usd": pricing.cpu_per_vcpu_hour_usd,
            "mem_per_gb_hour_usd": pricing.mem_per_gb_hour_usd,
        },
        "defaults": {
            "cpu_millicores": defaults.cpu_millicores,
            "memory_mib": defaults.memory_mib,
        },
        "disclaimer": "This is an estimator based on Kubernetes requests, not a billing source of truth.",
    }


@app.get("/report")
async def report(
    context: Optional[str] = Query(default=None),
    kubeconfig: Optional[str] = Query(default=None),
    namespace: Optional[List[str]] = Query(default=None),
    include_system_namespaces: bool = Query(default=False),
    sort: str = Query(default="total"),
    top_workloads: int = Query(default=10),
    config_path: Optional[str] = Query(default=None),
) -> JSONResponse:
    try:
        cfg = AppConfig.from_yaml(config_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        core, custom = load_clients(context=context, kubeconfig=kubeconfig)
    except Exception as exc:  # pragma: no cover - network/config
        logger.error("Failed to load Kubernetes clients: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load Kubernetes configuration")

    try:
        pods = list_pods(core, namespaces=namespace)
    except Exception as exc:  # pragma: no cover - network/config
        logger.error("Failed to list pods: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list pods")

    usage = get_pod_usage(custom)

    rep = generate_report(
        pods=pods,
        config=cfg,
        include_system_namespaces=include_system_namespaces,
        namespace_filter=namespace,
        usage=usage,
        sort_by=sort,
        top_workloads=top_workloads,
    )

    return JSONResponse(content=rep.to_dict())


