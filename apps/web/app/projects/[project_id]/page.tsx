import Link from "next/link";

import { ProjectWorkspace } from "../../../features/workspace/project-workspace";

const PROJECT_ID_PATTERN =
  /^prj_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export default async function ProjectDocumentsPage({
  params,
}: Readonly<{
  params: Promise<{ project_id: string }>;
}>) {
  const { project_id: projectId } = await params;

  if (!PROJECT_ID_PATTERN.test(projectId)) {
    return (
      <main className="w-full max-w-4xl">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-950">
          Project unavailable
        </h1>
        <p className="mt-4 text-slate-600">The project link is invalid.</p>
        <Link className="mt-6 inline-block font-medium text-slate-900 underline" href="/">
          Return to projects
        </Link>
      </main>
    );
  }

  return (
    <main className="w-full max-w-5xl">
      <Link className="text-sm font-medium text-slate-600 underline" href="/">
        Back to projects
      </Link>
      <p className="mt-6 text-sm font-medium uppercase tracking-widest text-slate-500">
        Document workspace
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
        Translation workspace
      </h1>
      <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
        Move from immutable PDF import through OCR, local translation, review,
        reconstruction, export, and verified backup.
      </p>
      <ProjectWorkspace projectId={projectId} />
    </main>
  );
}
