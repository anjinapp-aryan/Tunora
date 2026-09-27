"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowRightIcon, PlusIcon } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/jobs";
import { createProject, listProjects, type ProjectSort, type ProjectSummary } from "@/lib/api/projects";
import { formatDate } from "@/lib/format-date";
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 300;
const LOAD_ERROR = "Could not load your projects. Please try again.";
const NAME_MAX = 200;
const DESCRIPTION_MAX = 2000;

type Result = { key: string; projects?: ProjectSummary[]; error?: string };

/** The Projects page: search/sort existing Projects, create a new one, open one. */
export function ProjectList() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ProjectSort>("newest");
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(input), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  const key = `${query}|${sort}|${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    listProjects({ query, sort, signal: controller.signal })
      .then((projects) => setResult({ key, projects }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        console.error("project list load failed", error);
        setResult({ key, error: error instanceof ApiError ? error.message : LOAD_ERROR });
      });
    return () => controller.abort();
  }, [key, query, sort]);

  const loading = result?.key !== key;
  const projects = result?.key === key ? result.projects : undefined;
  const error = result?.key === key ? result.error : undefined;

  function onCreated() {
    setCreating(false);
    setAttempt((n) => n + 1);
  }

  return (
    <section aria-label="Projects" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="grid flex-1 gap-4 sm:grid-cols-[1fr_auto]">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="project-search" className="text-sm font-medium">
              Search projects
            </label>
            <Input id="project-search" type="search" placeholder="Project name" maxLength={100} value={input} onChange={(e) => setInput(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="project-sort" className="text-sm font-medium">
              Sort by
            </label>
            <NativeSelect id="project-sort" className="w-full sm:w-44" value={sort} onChange={(e) => setSort(e.target.value as ProjectSort)}>
              <NativeSelectOption value="newest">Recently updated</NativeSelectOption>
              <NativeSelectOption value="oldest">Oldest first</NativeSelectOption>
              <NativeSelectOption value="title">Title (A–Z)</NativeSelectOption>
            </NativeSelect>
          </div>
        </div>
        <Button type="button" onClick={() => setCreating((v) => !v)} aria-expanded={creating} aria-controls="create-project-form">
          <PlusIcon aria-hidden="true" /> Create Project
        </Button>
      </div>

      {creating && <CreateProjectForm onCreated={onCreated} onCancel={() => setCreating(false)} />}

      <div role="status" aria-live="polite" className="min-h-5 text-sm text-muted-foreground" data-testid="project-list-status">
        {loading ? "Loading projects…" : projects ? `${projects.length} ${projects.length === 1 ? "project" : "projects"}` : ""}
      </div>

      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm" data-testid="project-list-error">
          <span>{error}</span>
          <button type="button" className={cn(buttonVariants({ variant: "outline", size: "sm" }))} onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      )}

      {projects && projects.length === 0 && (
        <p className="rounded-xl border border-border/60 p-6 text-sm text-muted-foreground" data-testid="project-list-empty">
          {query ? "No projects match your search." : "No projects yet. Create one to start organizing your songs."}
        </p>
      )}

      {projects && projects.length > 0 && (
        <ul className="flex flex-col gap-3">
          {projects.map((project) => (
            <li key={project.id} className="rounded-xl border border-border/60 p-4" data-testid="project-item">
              <h2 className="text-base font-medium [overflow-wrap:anywhere]">{project.name}</h2>
              {project.description && <p className="mt-1 text-sm text-muted-foreground [overflow-wrap:anywhere]">{project.description}</p>}
              <p className="mt-1 text-sm text-muted-foreground" data-testid="project-song-count">
                {project.song_count} {project.song_count === 1 ? "song" : "songs"}
              </p>
              <p className="text-sm text-muted-foreground">Updated {formatDate(project.updated_at)}</p>
              <Link href={`/projects/${encodeURIComponent(project.id)}`} aria-label={`Open project: ${project.name}`} className={cn(buttonVariants({ variant: "outline" }), "mt-3")}>
                Open Project <ArrowRightIcon aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CreateProjectForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Project name is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createProject(trimmed, description.trim());
      onCreated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create this project. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      id="create-project-form"
      aria-label="Create project"
      onSubmit={onSubmit}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
      className="flex flex-col gap-3 rounded-xl border border-border/60 p-4"
      data-testid="create-project-form"
    >
      <label className="flex flex-col gap-1 text-sm">
        Project name
        <Input value={name} maxLength={NAME_MAX} autoFocus onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Description (optional)
        <Textarea value={description} maxLength={DESCRIPTION_MAX} rows={2} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="text-sm text-destructive" data-testid="create-project-error">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "Creating…" : "Create"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
