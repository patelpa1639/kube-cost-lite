import React, { useEffect, useMemo, useState } from "react";

type NamespaceRow = {
  namespace: string;
  cpu_vcpu: number;
  mem_gib: number;
  monthly_cpu_usd: number;
  monthly_mem_usd: number;
  monthly_total_usd: number;
  defaulted_percent: number;
};

type WorkloadRow = {
  workload: string;
  namespace: string;
  monthly_total_usd: number;
};

type ReportResponse = {
  namespaces: NamespaceRow[];
  workloads: WorkloadRow[];
};

const API_BASE =
  (import.meta as any).env.VITE_API_BASE_URL ?? "http://localhost:8000";

const SORT_OPTIONS = [
  { value: "total", label: "Total cost" },
  { value: "cpu", label: "CPU cost" },
  { value: "mem", label: "Memory cost" },
  { value: "defaulted", label: "Defaulted %" },
];

export const App: React.FC = () => {
  const [context, setContext] = useState("kind-kc1");
  const [includeSystem, setIncludeSystem] = useState(false);
  const [sort, setSort] = useState("total");
  const [topWorkloads, setTopWorkloads] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ReportResponse | null>(null);

  const totalMonthly = useMemo(
    () =>
      data?.namespaces.reduce(
        (sum, ns) => sum + ns.monthly_total_usd,
        0,
      ) ?? 0,
    [data],
  );

  const fetchReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const url = new URL("/report", API_BASE);
      if (context.trim()) {
        url.searchParams.set("context", context.trim());
      }
      url.searchParams.set(
        "include_system_namespaces",
        includeSystem ? "true" : "false",
      );
      url.searchParams.set("sort", sort);
      url.searchParams.set("top_workloads", String(topWorkloads));

      const res = await fetch(url.toString());
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status} ${res.statusText}: ${text}`);
      }
      const json = (await res.json()) as ReportResponse;
      setData(json);
    } catch (e: any) {
      setError(e.message ?? String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app-shell">
      <header className="shell-header sticky top-0 z-10">
        <div className="shell-header-inner">
          <div className="shell-title-block">
            <div className="shell-title">kube-cost-lite</div>
            <div className="shell-subtitle">
              Requests-based Kubernetes cost dashboard
            </div>
          </div>
          <div className="shell-controls">
            <div className="flex flex-col">
              <label className="shell-label">Kube context</label>
              <input
                className="shell-input"
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="kind-kc1"
              />
            </div>
            <div className="flex flex-col">
              <label className="shell-label">Sort namespaces</label>
              <select
                className="shell-select"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col">
              <label className="shell-label">Top workloads</label>
              <input
                type="number"
                min={1}
                max={50}
                className="shell-input"
                value={topWorkloads}
                onChange={(e) =>
                  setTopWorkloads(
                    Math.max(1, Math.min(50, Number(e.target.value) || 1)),
                  )
                }
              />
            </div>
            <label className="shell-checkbox">
              <input
                type="checkbox"
                checked={includeSystem}
                onChange={(e) => setIncludeSystem(e.target.checked)}
              />
              <span className="text-xs">Include system namespaces</span>
            </label>
            <button
              onClick={fetchReport}
              className="shell-refresh"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      <main className="shell-main space-y-6">
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="stat-card">
            <div className="stat-label">Total monthly (requests)</div>
            <div className="stat-value">
              ${totalMonthly.toFixed(2)}
            </div>
            <div className="stat-sub">
              Across {data?.namespaces.length ?? 0} namespaces
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Namespaces with defaults</div>
            <div className="stat-value">
              {data
                ? data.namespaces.filter(
                    (ns) => ns.defaulted_percent > 0,
                  ).length
                : 0}
            </div>
            <div className="stat-sub">
              Containers missing requests use configured defaults
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Current context</div>
            <div className="stat-value text-xs md:text-sm truncate">
              {context || "(cluster default)"}
            </div>
            <div className="stat-sub">
              Powered by kube-cost-lite / FastAPI
            </div>
          </div>
        </section>

        {error && (
          <div className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            <div className="font-medium mb-1">Error loading report</div>
            <div className="text-xs whitespace-pre-wrap break-all">{error}</div>
          </div>
        )}

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">Namespaces</h2>
              <span className="panel-subtitle">
                Requests-based monthly estimate
              </span>
            </div>
            <div className="panel-body">
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Namespace</th>
                      <th className="num">CPU (vCPU)</th>
                      <th className="num">Mem (GiB)</th>
                      <th className="num">CPU $</th>
                      <th className="num">Mem $</th>
                      <th className="num">Total $</th>
                      <th className="num">Defaulted %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.namespaces.length ? (
                      data.namespaces.map((ns) => (
                        <tr key={ns.namespace}>
                          <td>{ns.namespace}</td>
                          <td className="num">{ns.cpu_vcpu.toFixed(3)}</td>
                          <td className="num">{ns.mem_gib.toFixed(3)}</td>
                          <td className="num">
                            {ns.monthly_cpu_usd.toFixed(2)}
                          </td>
                          <td className="num">
                            {ns.monthly_mem_usd.toFixed(2)}
                          </td>
                          <td className="num">
                            {ns.monthly_total_usd.toFixed(2)}
                          </td>
                          <td className="num">
                            {ns.defaulted_percent.toFixed(1)}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} className="empty-row">
                          {loading
                            ? "Loading namespaces…"
                            : "No namespaces found for this context."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">Top workloads</h2>
              <span className="panel-subtitle">
                By monthly total requests-based cost
              </span>
            </div>
            <div className="panel-body">
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Workload</th>
                      <th>Namespace</th>
                      <th className="num">Monthly $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.workloads.length ? (
                      data.workloads.map((wl) => (
                        <tr key={`${wl.namespace}:${wl.workload}`}>
                          <td>{wl.workload}</td>
                          <td>{wl.namespace}</td>
                          <td className="num">
                            {wl.monthly_total_usd.toFixed(2)}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3} className="empty-row">
                          {loading
                            ? "Loading workloads…"
                            : "No workloads found for this context."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        <footer className="pt-4 pb-6 text-xs text-slate-500 flex justify-between items-center">
          <span>
            Requests-based estimator. Prices & defaults are configurable via
            kube-cost-lite config.
          </span>
          <span>Dashboard: React + Vite</span>
        </footer>
      </main>
    </div>
  );
};

