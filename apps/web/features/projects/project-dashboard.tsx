"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  createTransLokaClient,
  type CreateProjectInput,
  type ProjectResource,
} from "@transloka/api-client";
import { useState } from "react";
import { useForm, type SubmitHandler } from "react-hook-form";
import { z } from "zod";

type ProjectClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  "archiveProject" | "createProject" | "listProjects" | "unarchiveProject"
>;

const PROJECTS_QUERY_KEY = ["projects"] as const;
const defaultClient = createTransLokaClient();
const documentTypes = [
  ["ACADEMIC_PAPER", "Academic paper"],
  ["ACADEMIC_BOOK", "Academic book"],
  ["TECHNICAL_BOOK", "Technical book"],
  ["USER_MANUAL", "User manual"],
  ["BUSINESS_REPORT", "Business report"],
  ["LEGAL_DOCUMENT", "Legal document"],
  ["FICTION_BOOK", "Fiction book"],
  ["NONFICTION_BOOK", "Nonfiction book"],
  ["PRESENTATION_EXPORT", "Presentation export"],
  ["BROCHURE", "Brochure"],
  ["FORM", "Form"],
  ["COMIC_OR_GRAPHIC_BOOK", "Comic or graphic book"],
  ["GENERAL_DOCUMENT", "General document"],
  ["UNKNOWN", "Unknown"],
] as const satisfies ReadonlyArray<
  readonly [CreateProjectInput["document_type"], string]
>;
const translationStyles = [
  ["PROFESSIONAL", "Professional"],
  ["ACADEMIC", "Academic"],
  ["NATURAL", "Natural"],
  ["LITERAL", "Literal"],
] as const satisfies ReadonlyArray<
  readonly [CreateProjectInput["translation_style"], string]
>;
const reconstructionModes = [
  ["HYBRID", "Hybrid"],
  ["REFLOW", "Reflow"],
  ["OVERLAY", "Overlay"],
] as const satisfies ReadonlyArray<
  readonly [CreateProjectInput["reconstruction_mode"], string]
>;

const createProjectSchema = z.object({
  name: z.string().trim().min(1, "Project name is required."),
  description: z.string(),
  source_language: z.literal("en"),
  target_language: z.literal("id"),
  document_type: z.enum(documentTypes.map(([value]) => value)),
  translation_style: z.enum(translationStyles.map(([value]) => value)),
  reconstruction_mode: z.enum(reconstructionModes.map(([value]) => value)),
});

type ProjectFormValues = z.infer<typeof createProjectSchema>;

const defaultProjectValues: ProjectFormValues = {
  name: "",
  description: "",
  source_language: "en",
  target_language: "id",
  document_type: "TECHNICAL_BOOK",
  translation_style: "PROFESSIONAL",
  reconstruction_mode: "HYBRID",
};

function projectRequestError(message: string): Error {
  return new Error(message);
}

function projectStatusLabel(status: ProjectResource["status"]): string {
  return status
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function projectTypeLabel(value: ProjectResource["document_type"]): string {
  return documentTypes.find(([option]) => option === value)?.[1] ?? "Unknown";
}

function formattedTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "Unknown"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function FieldError({
  id,
  message,
}: Readonly<{ id: string; message: string | undefined }>) {
  return message === undefined ? null : (
    <p className="mt-1 text-sm text-red-700" id={id} role="alert">
      {message}
    </p>
  );
}

function CreateProjectForm({
  client,
}: Readonly<{
  client: ProjectClient;
}>) {
  const queryClient = useQueryClient();
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
  } = useForm<ProjectFormValues>({
    defaultValues: defaultProjectValues,
    resolver: zodResolver(createProjectSchema),
  });
  const createProject = useMutation({
    mutationFn: async (values: ProjectFormValues) => {
      const description = values.description.trim();
      const result = await client.createProject({
        ...values,
        description: description === "" ? null : description,
        name: values.name.trim(),
      });
      if (!result.ok) {
        throw projectRequestError(result.error.message);
      }
      return result.data.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
    },
  });

  const submitProject: SubmitHandler<ProjectFormValues> = async (values) => {
    try {
      await createProject.mutateAsync(values);
      reset(defaultProjectValues);
    } catch {
      // The mutation state renders the normalized, user-actionable message.
    }
  };

  return (
    <section
      aria-labelledby="create-project-heading"
      className="mt-10 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <h2 className="text-xl font-semibold text-slate-950" id="create-project-heading">
        Create project
      </h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        Projects use English source text and Indonesian target text for this Personal MVP.
      </p>

      <form
        className="mt-6 grid gap-5 md:grid-cols-2"
        noValidate
        onSubmit={(event) => void handleSubmit(submitProject)(event)}
      >
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-slate-800" htmlFor="project-name">
            Project name
          </label>
          <input
            aria-describedby={errors.name ? "project-name-error" : undefined}
            aria-invalid={errors.name ? "true" : "false"}
            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-950 outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
            id="project-name"
            {...register("name")}
          />
          <FieldError id="project-name-error" message={errors.name?.message} />
        </div>

        <div className="md:col-span-2">
          <label
            className="block text-sm font-medium text-slate-800"
            htmlFor="project-description"
          >
            Description <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <textarea
            className="mt-2 min-h-24 w-full resize-y rounded-lg border border-slate-300 px-3 py-2.5 text-slate-950 outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
            id="project-description"
            {...register("description")}
          />
        </div>

        <div>
          <label
            className="block text-sm font-medium text-slate-800"
            htmlFor="source-language"
          >
            Source language
          </label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-950"
            id="source-language"
            {...register("source_language")}
          >
            <option value="en">English</option>
          </select>
        </div>

        <div>
          <label
            className="block text-sm font-medium text-slate-800"
            htmlFor="target-language"
          >
            Target language
          </label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-950"
            id="target-language"
            {...register("target_language")}
          >
            <option value="id">Indonesian</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-800" htmlFor="document-type">
            Document type
          </label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-950"
            id="document-type"
            {...register("document_type")}
          >
            {documentTypes.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            className="block text-sm font-medium text-slate-800"
            htmlFor="translation-style"
          >
            Translation style
          </label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-950"
            id="translation-style"
            {...register("translation_style")}
          >
            {translationStyles.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            className="block text-sm font-medium text-slate-800"
            htmlFor="reconstruction-mode"
          >
            Reconstruction mode
          </label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-950"
            id="reconstruction-mode"
            {...register("reconstruction_mode")}
          >
            {reconstructionModes.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-end">
          <button
            className="inline-flex rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={createProject.isPending}
            type="submit"
          >
            {createProject.isPending ? "Creating…" : "Create project"}
          </button>
        </div>

        {createProject.isError ? (
          <p className="text-sm text-red-700 md:col-span-2" role="alert">
            {createProject.error.message}
          </p>
        ) : null}
        {createProject.isSuccess ? (
          <p className="text-sm text-emerald-700 md:col-span-2" role="status">
            Project created.
          </p>
        ) : null}
      </form>
    </section>
  );
}

function ProjectCard({
  busy,
  onArchiveChange,
  project,
}: Readonly<{
  busy: boolean;
  onArchiveChange: (project: ProjectResource) => void;
  project: ProjectResource;
}>) {
  const archived = project.status === "ARCHIVED";
  const progress = Math.round(project.progress * 100);

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-slate-950">{project.name}</h3>
          <p className="mt-1 text-sm text-slate-600">
            {project.source_language.toUpperCase()} → {project.target_language.toUpperCase()} ·{" "}
            {projectTypeLabel(project.document_type)}
          </p>
        </div>
        <span
          className={
            archived
              ? "rounded-full bg-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700"
              : "rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-800"
          }
        >
          {projectStatusLabel(project.status)}
        </span>
      </div>

      {project.description ? (
        <p className="mt-4 text-sm leading-6 text-slate-600">{project.description}</p>
      ) : null}

      <div className="mt-5">
        <div className="flex justify-between text-xs font-medium text-slate-600">
          <span>Progress</span>
          <span>{progress}%</span>
        </div>
        <progress className="mt-2 h-2 w-full accent-slate-900" max={100} value={progress}>
          {progress}%
        </progress>
      </div>

      <div className="mt-5 flex items-center justify-between gap-4 border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-500">Updated {formattedTime(project.updated_at)}</p>
        <button
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy || project.status === "DELETION_QUEUED"}
          onClick={() => onArchiveChange(project)}
          type="button"
        >
          {busy ? "Updating…" : archived ? "Restore" : "Archive"}
        </button>
      </div>
    </article>
  );
}

function ProjectDashboardContent({
  client = defaultClient,
}: Readonly<{ client?: ProjectClient }>) {
  const queryClient = useQueryClient();
  const projects = useQuery({
    queryFn: async ({ signal }) => {
      const result = await client.listProjects({ signal });
      if (!result.ok) {
        throw projectRequestError(result.error.message);
      }
      return result.data.data;
    },
    queryKey: PROJECTS_QUERY_KEY,
  });
  const archiveProject = useMutation({
    mutationFn: async (project: ProjectResource) => {
      const result =
        project.status === "ARCHIVED"
          ? await client.unarchiveProject(project.id)
          : await client.archiveProject(project.id);
      if (!result.ok) {
        throw projectRequestError(result.error.message);
      }
      return result.data.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
    },
  });

  const activeProjects =
    projects.data?.filter((project) => project.status !== "ARCHIVED") ?? [];
  const archivedProjects =
    projects.data?.filter((project) => project.status === "ARCHIVED") ?? [];

  return (
    <>
      <CreateProjectForm client={client} />

      <section aria-labelledby="project-list-heading" className="mt-10">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-slate-950" id="project-list-heading">
              Your projects
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              This list reloads from the local database whenever the page opens.
            </p>
          </div>
          {projects.isSuccess ? (
            <p className="text-sm text-slate-500">
              {projects.data.length} {projects.data.length === 1 ? "project" : "projects"}
            </p>
          ) : null}
        </div>

        {projects.isPending ? (
          <div
            aria-live="polite"
            className="mt-6 rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-600"
            role="status"
          >
            Loading projects…
          </div>
        ) : null}

        {projects.isError ? (
          <div
            className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-6"
            role="alert"
          >
            <p className="font-semibold text-red-900">Projects could not be loaded.</p>
            <p className="mt-2 text-sm text-red-800">{projects.error.message}</p>
            <button
              className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-800"
              onClick={() => void projects.refetch()}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : null}

        {projects.isSuccess && projects.data.length === 0 ? (
          <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <p className="font-semibold text-slate-900">No projects yet</p>
            <p className="mt-2 text-sm text-slate-600">
              Complete the form above to create your first local translation project.
            </p>
          </div>
        ) : null}

        {projects.isSuccess && projects.data.length > 0 ? (
          <div className="mt-6 space-y-10">
            <section aria-labelledby="active-projects-heading">
              <h3 className="text-lg font-semibold text-slate-900" id="active-projects-heading">
                Active projects
              </h3>
              {activeProjects.length === 0 ? (
                <p className="mt-3 text-sm text-slate-600">No active projects.</p>
              ) : (
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  {activeProjects.map((project) => (
                    <ProjectCard
                      busy={
                        archiveProject.isPending &&
                        archiveProject.variables?.id === project.id
                      }
                      key={project.id}
                      onArchiveChange={(selected) => archiveProject.mutate(selected)}
                      project={project}
                    />
                  ))}
                </div>
              )}
            </section>

            <section aria-labelledby="archived-projects-heading">
              <h3
                className="text-lg font-semibold text-slate-900"
                id="archived-projects-heading"
              >
                Archived projects
              </h3>
              {archivedProjects.length === 0 ? (
                <p className="mt-3 text-sm text-slate-600">No archived projects.</p>
              ) : (
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  {archivedProjects.map((project) => (
                    <ProjectCard
                      busy={
                        archiveProject.isPending &&
                        archiveProject.variables?.id === project.id
                      }
                      key={project.id}
                      onArchiveChange={(selected) => archiveProject.mutate(selected)}
                      project={project}
                    />
                  ))}
                </div>
              )}
            </section>
          </div>
        ) : null}

        {archiveProject.isError ? (
          <p className="mt-4 text-sm text-red-700" role="alert">
            {archiveProject.error.message}
          </p>
        ) : null}
      </section>
    </>
  );
}

export function ProjectDashboard({
  client = defaultClient,
}: Readonly<{ client?: ProjectClient }>) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          mutations: { retry: false },
          queries: { retry: false },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ProjectDashboardContent client={client} />
    </QueryClientProvider>
  );
}
