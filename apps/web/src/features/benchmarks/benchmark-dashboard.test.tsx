// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BenchmarkDashboard,
  type BenchmarkClient,
  type BenchmarkHardwareProfile,
  type BenchmarkModel,
  type FullBenchmarkRun,
} from "./benchmark-dashboard";

function hardware(): BenchmarkHardwareProfile {
  return {
    profile_id: "hardware_test",
    operating_system: "Windows",
    operating_system_version: "11",
    cpu_model: "Test CPU",
    logical_cores: 8,
    ram_total_gb: 16,
    ram_available_gb: 8,
    gpu_vendor: null,
    gpu_model: null,
    gpu_vram_total_gb: 0,
    gpu_vram_available_gb: 0,
    disk_free_gb: 100,
  };
}

const models: BenchmarkModel[] = [
  { id: "qwen3:1.7b", label: "qwen3:1.7b" },
  { id: "llama3.2:3b", label: "llama3.2:3b" },
];

function run(overrides: Partial<FullBenchmarkRun> = {}): FullBenchmarkRun {
  return {
    benchmark_id: "bmk_full_test",
    model_id: "qwen3:1.7b",
    status: "COMPLETED",
    recommendation: "RECOMMENDED_DEFAULT",
    completed_runs: 90,
    total_runs: 90,
    success_rate: 1,
    quality_score: 1,
    average_latency_seconds: 0.2,
    critical_failure_count: 0,
    ...overrides,
  };
}

function makeClient(overrides: Partial<BenchmarkClient> = {}): BenchmarkClient {
  return {
    getHardwareProfile: vi.fn(() => Promise.resolve(hardware())),
    listModels: vi.fn(() => Promise.resolve(models)),
    startFullBenchmark: vi.fn(() => Promise.resolve(run({ status: "PARTIALLY_COMPLETED", completed_runs: 2 }))),
    cancelBenchmark: vi.fn(() => Promise.resolve(run({ status: "CANCELLED", completed_runs: 2 }))),
    resumeBenchmark: vi.fn(() => Promise.resolve(run())),
    ...overrides,
  };
}

afterEach(() => cleanup());

describe("BenchmarkDashboard", () => {
  it("loads hardware and requires an explicit installed model selection", async () => {
    const client = makeClient();

    render(<BenchmarkDashboard client={client} />);

    expect(await screen.findByText("Test CPU")).toBeTruthy();
    const start = screen.getByRole("button", { name: "Start full benchmark" });
    expect((start as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Benchmark model"), {
      target: { value: "llama3.2:3b" },
    });
    expect((start as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(start);
    await act(async () => {
      await Promise.resolve();
    });

    expect(client.startFullBenchmark).toHaveBeenCalledWith("llama3.2:3b");
    expect(screen.getByText(/2 of 90 runs/)).toBeTruthy();
  });

  it("cancels and resumes a partial benchmark", async () => {
    const client = makeClient();

    render(<BenchmarkDashboard client={client} />);
    await screen.findByText("Test CPU");
    fireEvent.change(screen.getByLabelText("Benchmark model"), {
      target: { value: "qwen3:1.7b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start full benchmark" }));
    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole("button", { name: "Cancel benchmark" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(client.cancelBenchmark).toHaveBeenCalledWith("bmk_full_test");
    expect(screen.getByRole("button", { name: "Resume benchmark" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Resume benchmark" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(client.resumeBenchmark).toHaveBeenCalledWith("bmk_full_test");
    expect(screen.getByText("RECOMMENDED DEFAULT")).toBeTruthy();
  });

  it("surfaces a critical rejection recommendation", async () => {
    const client = makeClient({
      startFullBenchmark: vi.fn(() =>
        Promise.resolve(
          run({
            status: "FAILED",
            recommendation: "REJECTED",
            completed_runs: 90,
            success_rate: 0.7,
            critical_failure_count: 3,
          }),
        ),
      ),
    });

    render(<BenchmarkDashboard client={client} />);
    await screen.findByText("Test CPU");
    fireEvent.change(screen.getByLabelText("Benchmark model"), {
      target: { value: "qwen3:1.7b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start full benchmark" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("REJECTED")).toBeTruthy();
    expect(screen.getByText(/3 critical failure/)).toBeTruthy();
  });
});
