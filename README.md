# kube-cost-lite

Small, transparent Kubernetes cost estimator based on resource **requests** (and optionally usage, if metrics-server is installed).

This is intentionally minimal, open-source, and easy to reason about. It is **not** a billing system – just a handy estimator you can run against a local k3s/k8s cluster.

## Features

- **CLI report**: `kube-cost-lite report` prints a per-namespace monthly cost table and a top-workloads table.
- **Simple cost model**: based on CPU/memory *requests*, with configurable unit prices.
- **Defaults when missing**: containers without requests get configurable default CPU/memory and are counted in a “Defaulted %” column.
- **Metrics-server aware**: will attempt to read usage via `metrics.k8s.io` if available (usage is currently not surfaced in the CLI, but the plumbing is there).
- **HTTP API (FastAPI)**: optional `kube-cost-lite serve` command that exposes `/healthz`, `/report`, and `/explain`.
- **Works on k3s/k8s**: uses the standard Kubernetes Python client.

## Quickstart

```bash
git clone https://github.com/<you>/kube-cost-lite.git
cd kube-cost-lite

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .

kube-cost-lite report
```

Requirements:

- Python 3.11+
- A working kubeconfig pointing at your cluster (k3s/k8s).
- Optional: `metrics-server` installed in the cluster for usage metrics.

## Example output

```text
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃           Namespace monthly cost (requests-based)            ┃
┡━━━━━━━━━━━━┯━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━┯━━━┩
│ Namespace  │ CPU req(...) │ Mem req(...) │ Monthly CPU $ │ … │
├────────────┼──────────────┼──────────────┼──────────────┼───┤
│ default    │ 1.500        │ 4.000        │ 3.46         │… │
│ staging    │ 0.750        │ 2.000        │ 1.73         │… │
└────────────┴──────────────┴──────────────┴──────────────┴───┘

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃           Top workloads overall (requests-based)             ┃
┡━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━━━━━━┩
│ Workload (kind/name)  │ Namespace  │ Monthly Total $        │
├───────────────────────┼────────────┼───────────────────────┤
│ Deployment/api        │ default    │ 2.34                  │
│ StatefulSet/db        │ default    │ 1.12                  │
└───────────────────────┴────────────┴───────────────────────┘
```

## Cost model

The model is intentionally simple and transparent. By default:

- `hours_per_month = 730`
- `cpu_per_vcpu_hour_usd = 0.031611`
- `mem_per_gb_hour_usd = 0.004237`

Given **requests**:

- `vcpu = cpu_millicores / 1000`
- `cpu_cost = vcpu * hours_per_month * cpu_per_vcpu_hour_usd`
- `mem_gb = memory_bytes / (1024^3)`
- `mem_cost = mem_gb * hours_per_month * mem_per_gb_hour_usd`
- `total = cpu_cost + mem_cost`

The same formulas can be applied to **usage samples** from `metrics-server` if available, but by default the tool focuses on **requests-based** estimates.

### Defaults and missing requests

If a container is missing resource requests, kube-cost-lite uses defaults:

- `cpu_millicores: 100`
- `memory_mib: 128`

These defaults are configurable via YAML. The CLI shows a “Defaulted %” column per namespace which is:

> (number of containers that used defaults) / (total containers in that namespace)

## CLI commands

### `kube-cost-lite report`

Generate a report against your current cluster:

```bash
kube-cost-lite report \
  --context my-context \
  --kubeconfig ~/.kube/config \
  --namespace default --namespace staging \
  --include-system-namespaces=false \
  --sort total \
  --top-workloads 10 \
  --output table
```

Options:

- `--context`: kube context name (optional).
- `--kubeconfig`: kubeconfig path (optional).
- `--namespace, -n`: filter to these namespaces (repeatable).
- `--include-system-namespaces`: include system namespaces (`kube-system`, etc.).
- `--sort`: `total|cpu|mem|defaulted` (default: `total`).
- `--top-workloads`: number of workloads to show (default: `10`).
- `--output`: `table|json` (default: `table`).
- `--config, -c`: path to YAML config (optional).

The JSON output contains:

- `namespaces[]` with per-namespace metrics and costs.
- `workloads[]` with workload-level costs.

### `kube-cost-lite explain`

Print the pricing model and formulas, using either the defaults or an optional config file:

```bash
kube-cost-lite explain
kube-cost-lite explain --config ./config.yaml
```

### `kube-cost-lite sample-config`

Emit a sample configuration YAML to stdout:

```bash
kube-cost-lite sample-config > config.yaml
```

### `kube-cost-lite serve`

Run a small FastAPI server:

```bash
kube-cost-lite serve --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /healthz` – basic health probe.
- `GET /explain` – same content as `kube-cost-lite explain` but as JSON.
- `GET /report` – JSON report; supports query params:
  - `context`
  - `kubeconfig`
  - `namespace` (repeatable)
  - `include_system_namespaces`
  - `sort`
  - `top_workloads`
  - `config_path`

## Configuration

Config is a single YAML file with three main sections: `pricing`, `defaults`, and `behavior`. Example:

```yaml
pricing:
  hours_per_month: 730
  cpu_per_vcpu_hour_usd: 0.031611
  mem_per_gb_hour_usd: 0.004237

defaults:
  cpu_millicores: 100
  memory_mib: 128

behavior:
  include_completed_pods: false
  system_namespaces:
    - kube-system
    - kube-public
    - kube-node-lease
    - local-path-storage
```

You can point the CLI/server at this file via `--config / ?config_path`.

## Metrics-server

If `metrics-server` is installed, kube-cost-lite will:

- Query `metrics.k8s.io/v1beta1/pods`.
- Parse CPU and memory usage per container.

If the API group is missing or errors, kube-cost-lite logs a warning and falls back to **requests-only** estimates. The report will still work.

## Container image & CronJob

Build a minimal image:

```bash
docker build -t kube-cost-lite:0.1.0 .
```

Run as a CronJob (see `deploy/cronjob.yaml`):

```bash
kubectl apply -f deploy/cronjob.yaml
```

This runs `kube-cost-lite report` daily and prints the table to logs.

## Limitations & disclaimers

- This is a **rough estimator** – always compare against your actual cloud bills.
- Prices are **defaults only**; you should adjust them per region / instance type.
- Using requests as a proxy for cost is approximate but useful for capacity planning and showback.
- Usage-based estimates assume the sampled usage is representative over the month.

## License

MIT – see `LICENSE`.

