import { SystemHealth } from "../../../features/system/system-health";

export default function SystemHealthPage() {
  return (
    <main className="w-full max-w-4xl">
      <p className="text-sm font-medium uppercase tracking-widest text-slate-500">
        Local system
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
        System health
      </h1>
      <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
        Check the components currently available in this TransLoka milestone. No data leaves
        this computer.
      </p>
      <SystemHealth />
    </main>
  );
}
