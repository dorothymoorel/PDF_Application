import Link from "next/link";

export default function Home() {
  return (
    <main className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
      <p className="text-sm font-medium uppercase tracking-widest text-slate-500">
        Personal MVP
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">TransLoka</h1>
      <p className="mt-4 text-lg leading-8 text-slate-600">
        Local-First Personal PDF Translation Application
      </p>
      <Link
        className="mt-8 inline-flex rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
        href="/settings/system"
      >
        View system health
      </Link>
    </main>
  );
}
