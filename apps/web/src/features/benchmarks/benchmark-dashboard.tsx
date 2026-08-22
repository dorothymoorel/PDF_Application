"use client";

import { useEffect, useState } from "react";

export type BenchmarkHardwareProfile = {
  profile_id: string;
  operating_system: string;
  operating_system_version: string;
  cpu_model: string;
  logical_cores: number | null;
  ram_total_gb: number | null;
  ram_available_gb: number | null;
  gpu_vendor: string | null;
  gpu_model: string | null;
  gpu_vram_total_gb: number | null;
  gpu_vram_available_gb: number | null;
  disk_free_gb: number | null;
};

export type BenchmarkModel = {
  id: string;
  label: string;
};

export type FullBenchmarkRunStatus =
  | "RUNNING"
  | "PARTIALLY_COMPLETED"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type FullBenchmarkRecommendation =
  | "RECOMMENDED_DEFAULT"
  | "FALLBACK_ONLY"
  | "EXPERIMENTAL"
  | "REJECTED";

export type FullBenchmarkRun = {
  benchmark_id: string;
  model_id: string;
  status: FullBenchmarkRunStatus;
  recommendation: FullBenchmarkRecommendation;
  completed_runs: number;
  total_runs: number;
  success_rate: number | null;
  quality_score: number | null;
  average_latency_seconds: number | null;
  critical_failure_count: number;
};

export type BenchmarkClient = {
  getHardwareProfile: () => Promise<BenchmarkHardwareProfile>;
  listModels: () => Promise<BenchmarkModel[]>;
  startFullBenchmark: (modelId: string) => Promise<FullBenchmarkRun>;
  cancelBenchmark: (benchmarkId: string) => Promise<FullBenchmarkRun>;
  resumeBenchmark: (benchmarkId: string) => Promise<FullBenchmarkRun>;
};

function recommendationLabel(value: FullBenchmarkRecommendation): string {
  return value.replaceAll("_", " ");
}

function percent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function actionError(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The benchmark request could not be completed.";
}

export function BenchmarkDashboard({
  client,
}: Readonly<{
  client: BenchmarkClient;
}>) {
  const [hardware, setHardware] = useState<BenchmarkHardwareProfile | null>(null);
  const [models, setModels] = useState<BenchmarkModel[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [run, setRun] = useState<FullBenchmarkRun | null>(null);
  const [pendingAction, setPendingAction] = useState<"start" | "cancel" | "resume" | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);
    void Promise.all([client.getHardwareProfile(), client.listModels()])
      .then(([profile, installedModels]) => {
        if (!active) return;
        setHardware(profile);
        setModels(installedModels);
      })
      .catch((cause: unknown) => {
        if (active) setError(actionError(cause));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [client]);

  const startBenchmark = async () => {
    if (selectedModel === "" || pendingAction !== null) return;
    setPendingAction("start");
    setError(null);
    try {
      setRun(await client.startFullBenchmark(selectedModel));
    } catch (cause) {
      setError(actionError(cause));
    } finally {
      setPendingAction(null);
    }
  };

  const cancelBenchmark = async () => {
    if (run === null || pendingAction !== null) return;
    setPendingAction("cancel");
    setError(null);
    try {
      setRun(await client.cancelBenchmark(run.benchmark_id));
    } catch (cause) {
      setError(actionError(cause));
    } finally {
      setPendingAction(null);
    }
  };

  const resumeBenchmark = async () => {
    if (run === null || pendingAction !== null) return;
    setPendingAction("resume");
    setError(null);
    try {
      setRun(await client.resumeBenchmark(run.benchmark_id));
    } catch (cause) {
      setError(actionError(cause));
    } finally {
      setPendingAction(null);
    }
  };

  const canCancel = run?.status === "RUNNING" || run?.status === "PARTIALLY_COMPLETED";
  const canResume = run?.status === "CANCELLED" || run?.status === "PARTIALLY_COMPLETED";

  return (
    <main aria-labelledby="benchmark-dashboard-heading" className="w-full space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Local models</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="benchmark-dashboard-heading">
          Full model benchmark
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Compare installed local models using repeated translation, context, batch, and safety checks.
        </p>
      </header>

      {error !== null ? <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{error}</p> : null}

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading hardware and installed models…
        </p>
      ) : (
        <>
          {hardware !== null ? (
            <section aria-labelledby="benchmark-hardware-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold text-slate-950" id="benchmark-hardware-heading">Hardware profile</h2>
              <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div><dt className="font-medium text-slate-600">Operating system</dt><dd className="mt-1 text-slate-950">{hardware.operating_system} {hardware.operating_system_version}</dd></div>
                <div><dt className="font-medium text-slate-600">CPU</dt><dd className="mt-1 text-slate-950">{hardware.cpu_model}</dd></div>
                <div><dt className="font-medium text-slate-600">Logical cores</dt><dd className="mt-1 text-slate-950">{hardware.logical_cores ?? "Unknown"}</dd></div>
                <div><dt className="font-medium text-slate-600">RAM</dt><dd className="mt-1 text-slate-950">{hardware.ram_total_gb === null ? "Unknown" : `${hardware.ram_total_gb} GB`}</dd></div>
                <div><dt className="font-medium text-slate-600">GPU</dt><dd className="mt-1 text-slate-950">{hardware.gpu_model ?? "Not detected"}</dd></div>
                <div><dt className="font-medium text-slate-600">VRAM</dt><dd className="mt-1 text-slate-950">{hardware.gpu_vram_total_gb === null ? "Unknown" : `${hardware.gpu_vram_total_gb} GB`}</dd></div>
                <div><dt className="font-medium text-slate-600">Free disk</dt><dd className="mt-1 text-slate-950">{hardware.disk_free_gb === null ? "Unknown" : `${hardware.disk_free_gb.toFixed(1)} GB`}</dd></div>
              </dl>
            </section>
          ) : null}

          <section aria-labelledby="benchmark-run-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-950" id="benchmark-run-heading">Run benchmark</h2>
            <p className="mt-1 text-sm text-slate-600">Only models returned by the local provider can be selected.</p>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <label className="text-sm font-medium text-slate-800" htmlFor="benchmark-model">
                Benchmark model
                <select
                  className="mt-1 block min-w-56 rounded-lg border border-slate-300 px-3 py-2 font-normal"
                  id="benchmark-model"
                  onChange={(event) => setSelectedModel(event.target.value)}
                  value={selectedModel}
                >
                  <option value="">Select an installed model</option>
                  {models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
                </select>
              </label>
              <button
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={selectedModel === "" || pendingAction !== null}
                onClick={() => void startBenchmark()}
                type="button"
              >
                {pendingAction === "start" ? "Starting…" : "Start full benchmark"}
              </button>
            </div>
          </section>
        </>
      )}

      {run !== null ? (
        <section aria-labelledby="benchmark-result-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Benchmark result</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950" id="benchmark-result-heading">{run.model_id}</h2>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800">{run.status}</span>
          </div>
          <p className="mt-4 text-sm text-slate-700">{run.completed_runs} of {run.total_runs} runs · success rate {percent(run.success_rate)}</p>
          <progress aria-label="Benchmark progress" className="mt-2 h-3 w-full accent-slate-900" max={run.total_runs} value={run.completed_runs} />
          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs uppercase tracking-wide text-slate-500">Quality score</dt><dd className="mt-1 font-semibold text-slate-950">{percent(run.quality_score)}</dd></div>
            <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs uppercase tracking-wide text-slate-500">Average latency</dt><dd className="mt-1 font-semibold text-slate-950">{run.average_latency_seconds === null ? "—" : `${run.average_latency_seconds.toFixed(2)} s`}</dd></div>
            <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs uppercase tracking-wide text-slate-500">Recommendation</dt><dd className="mt-1 font-semibold text-slate-950">{recommendationLabel(run.recommendation)}</dd></div>
          </dl>
          {run.critical_failure_count > 0 ? <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900" role="alert">{run.critical_failure_count} critical failure(s) prevent this model from being recommended.</p> : null}
          <div className="mt-5 flex flex-wrap gap-3">
            {canCancel ? <button className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50" disabled={pendingAction !== null} onClick={() => void cancelBenchmark()} type="button">{pendingAction === "cancel" ? "Cancelling…" : "Cancel benchmark"}</button> : null}
            {canResume ? <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={pendingAction !== null} onClick={() => void resumeBenchmark()} type="button">{pendingAction === "resume" ? "Resuming…" : "Resume benchmark"}</button> : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}

export { recommendationLabel };
