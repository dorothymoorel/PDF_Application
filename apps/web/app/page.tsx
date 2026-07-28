import { ProjectDashboard } from "../features/projects/project-dashboard";

export default function Home() {
  return (
    <main className="w-full max-w-6xl">
      <p className="text-sm font-medium uppercase tracking-widest text-slate-500">
        Local workspace
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
        Projects
      </h1>
      <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
        TransLoka is a Local-First Personal PDF Translation Application. Create and
        continue English-to-Indonesian projects stored on this computer.
      </p>
      <ProjectDashboard />
    </main>
  );
}
