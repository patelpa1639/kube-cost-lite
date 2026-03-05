from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import AppConfig, sample_config_yaml
from .k8s_client import load_clients, list_pods
from .metrics import get_pod_usage
from .report import ReportResult, generate_report

app = typer.Typer(help="kube-cost-lite: Kubernetes cost estimator based on resource requests.")
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _print_namespace_table(report: ReportResult) -> None:
    table = Table(title="Namespace monthly cost (requests-based)")
    table.add_column("Namespace", style="bold")
    table.add_column("CPU req (vCPU)", justify="right")
    table.add_column("Mem req (GiB)", justify="right")
    table.add_column("Monthly CPU $", justify="right")
    table.add_column("Monthly Mem $", justify="right")
    table.add_column("Monthly Total $", justify="right", style="bold")
    table.add_column("Defaulted %", justify="right")

    for ns in report.namespaces:
        table.add_row(
            ns.namespace,
            f"{ns.cpu_vcpu:.3f}",
            f"{ns.mem_gib:.3f}",
            f"{ns.monthly_cpu_usd:.2f}",
            f"{ns.monthly_mem_usd:.2f}",
            f"{ns.monthly_total_usd:.2f}",
            f"{ns.defaulted_ratio * 100.0:.1f}",
        )

    console.print(table)


def _print_workload_table(report: ReportResult) -> None:
    table = Table(title="Top workloads overall (requests-based)")
    table.add_column("Workload (kind/name)")
    table.add_column("Namespace")
    table.add_column("Monthly Total $", justify="right", style="bold")

    for wl in report.workloads:
        table.add_row(wl.workload, wl.namespace, f"{wl.monthly_total_usd:.2f}")

    console.print(table)


@app.command()
def report(
    context: Optional[str] = typer.Option(None, help="Kube context name."),
    kubeconfig: Optional[Path] = typer.Option(None, help="Path to kubeconfig file."),
    namespace: List[str] = typer.Option(
        None,
        "--namespace",
        "-n",
        help="Namespace to include (repeatable). If omitted, all namespaces.",
    ),
    include_system_namespaces: bool = typer.Option(
        False, help="Include system namespaces (kube-system, etc.)."
    ),
    sort: str = typer.Option(
        "total",
        help="Sort column for namespaces: total|cpu|mem|defaulted",
    ),
    top_workloads: int = typer.Option(10, help="Number of top workloads to show."),
    output: str = typer.Option(
        "table",
        help="Output format: table|json",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to YAML config file.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Generate a cost report from the current Kubernetes cluster."""
    _setup_logging(verbose)

    try:
        cfg = AppConfig.from_yaml(str(config_path) if config_path else None)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    try:
        core, custom = load_clients(
            context=context,
            kubeconfig=str(kubeconfig) if kubeconfig else None,
        )
    except Exception as exc:
        typer.echo(f"Failed to load Kubernetes configuration: {exc}")
        raise typer.Exit(code=1)

    try:
        pods = list_pods(core, namespaces=namespace or None)
    except Exception as exc:
        typer.echo(f"Failed to list pods: {exc}")
        raise typer.Exit(code=1)

    usage = get_pod_usage(custom)

    rep = generate_report(
        pods=pods,
        config=cfg,
        include_system_namespaces=include_system_namespaces,
        namespace_filter=namespace or None,
        usage=usage,
        sort_by=sort,
        top_workloads=top_workloads,
    )

    if output == "json":
        typer.echo(json.dumps(rep.to_dict(), indent=2))
    else:
        _print_namespace_table(rep)
        _print_workload_table(rep)


@app.command()
def explain(
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Optional config file to show effective pricing.",
    )
) -> None:
    """Explain the pricing model and formulas."""
    try:
        cfg = AppConfig.from_yaml(str(config_path) if config_path else None)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    pricing = cfg.pricing
    defaults = cfg.defaults

    console.print("[bold]kube-cost-lite pricing model[/bold]")
    console.print(
        "\nThis tool estimates costs from Kubernetes resource requests "
        "(and optionally usage) using a simple, configurable model."
    )

    console.print("\n[bold]Formulas[/bold]:")
    console.print("  hours_per_month = 730 (configurable)")
    console.print("  vcpu = cpu_millicores / 1000")
    console.print(
        "  cpu_cost = vcpu * hours_per_month * cpu_per_vcpu_hour_usd",
    )
    console.print("  mem_gb = memory_bytes / (1024^3)")
    console.print(
        "  mem_cost = mem_gb * hours_per_month * mem_per_gb_hour_usd",
    )
    console.print("  total = cpu_cost + mem_cost")

    console.print("\n[bold]Unit prices (USD)[/bold]:")
    console.print(f"  cpu_per_vcpu_hour_usd: {pricing.cpu_per_vcpu_hour_usd}")
    console.print(f"  mem_per_gb_hour_usd:   {pricing.mem_per_gb_hour_usd}")
    console.print(f"  hours_per_month:       {pricing.hours_per_month}")

    console.print("\n[bold]Default requests when missing[/bold]:")
    console.print(f"  cpu_millicores: {defaults.cpu_millicores}")
    console.print(f"  memory_mib:     {defaults.memory_mib}")

    console.print(
        "\n[bold yellow]Disclaimer[/bold yellow]: This is an estimator based on "
        "Kubernetes resource requests and optional usage samples. It is not a "
        "billing or accounting system. Always compare against your cloud "
        "provider's billing data."
    )


@app.command("sample-config")
def sample_config() -> None:
    """Print a sample YAML configuration."""
    typer.echo(sample_config_yaml())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
    port: int = typer.Option(8000, help="Port to bind."),
    reload: bool = typer.Option(False, help="Enable auto-reload (for development)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Run a small HTTP server exposing the same report endpoints."""
    _setup_logging(verbose)

    import uvicorn  # Lazy import to keep CLI fast when not needed

    uvicorn.run("kube_cost_lite.server:app", host=host, port=port, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()

