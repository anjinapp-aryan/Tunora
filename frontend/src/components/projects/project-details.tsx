"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeftIcon, ArrowRightIcon, PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/jobs";
import {
  addSongToProject,
  deleteProject,
  getProjectDetails,
  removeSongFromProject,
  updateProject,
  type ProjectDetails as ProjectDetailsData,
} from "@/lib/api/projects";
import { listSongSummaries, type SongSummary } from "@/lib/api/songs";
import { formatDate } from "@/lib/format-date";
import { cn } from "@/lib/utils";

type Result = { key: string; project?: ProjectDetailsData; notFound?: boolean; error?: string };

/**
 * One Project: its name/description, an Edit panel, an Add-existing-song panel and the
 * list of songs it contains, each linking into the existing Song Details page. Adding or
 * removing a song here only changes organizational metadata -- it never touches audio.
 */
export function ProjectDetailsView({ projectId }: { projectId: string }) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);

  const key = `${projectId}|${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    getProjectDetails(projectId, { signal: controller.signal })
      .then((project) => setResult({ key, project }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        console.error("project load failed", error);
        if (error instanceof ApiError && error.kind === "not_found") setResult({ key, notFound: true });
        else setResult({ key, error: error instanceof ApiError ? error.message : "Could not load this project. Please try again." });
      });
    return () => controller.abort();
  }, [key, projectId]);

  const current = result?.key === key ? result : null;
  const reload = () => setAttempt((n) => n + 1);

  if (!current) {
    return (
      <p role="status" className="text-sm text-muted-foreground" data-testid="project-loading">
        Loading project…
      </p>
    );
  }

  if (current.notFound) {
    return (
      <section aria-labelledby="project-heading" className="rounded-xl border border-border/60 p-6" data-testid="project-not-found">
        <h1 id="project-heading" className="text-2xl font-semibold tracking-tight">
          Project not found
        </h1>
        <Alert variant="destructive" role="alert" className="mt-4">
          <AlertDescription>We couldn&apos;t find this project. It may have been removed, or the link is incorrect.</AlertDescription>
        </Alert>
        <BackToProjects />
      </section>
    );
  }

  if (current.error || !current.project) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 text-sm" data-testid="project-error">
        <span>{current.error}</span>
        <button type="button" className={cn(buttonVariants({ variant: "outline", size: "sm" }))} onClick={reload}>
          Try again
        </button>
      </div>
    );
  }

  const project = current.project;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <BackToProjects />
        <h1 data-testid="project-title" className="mt-4 text-2xl font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-3xl">
          {project.name}
        </h1>
        {project.description && (
          <p className="mt-2 text-sm text-muted-foreground [overflow-wrap:anywhere]" data-testid="project-description">
            {project.description}
          </p>
        )}
        <p className="mt-1 text-sm text-muted-foreground" data-testid="project-song-count">
          {project.songs.length} {project.songs.length === 1 ? "song" : "songs"} · Updated {formatDate(project.updated_at)}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" aria-expanded={editing} onClick={() => setEditing((v) => !v)}>
            Edit Project
          </Button>
          <DeleteProjectButton projectId={project.id} projectName={project.name} />
        </div>
        {editing && <EditProjectForm project={project} onSaved={() => (setEditing(false), reload())} onCancel={() => setEditing(false)} />}
      </div>

      <section aria-labelledby="songs-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="songs-heading" className="text-lg font-medium">
            Songs
          </h2>
          <Button type="button" size="sm" aria-expanded={adding} onClick={() => setAdding((v) => !v)}>
            <PlusIcon aria-hidden="true" /> Add Existing Song
          </Button>
        </div>

        {adding && (
          <AddSongPanel
            projectId={project.id}
            existingIds={new Set(project.songs.map((s) => s.id))}
            onAdded={() => {
              setAdding(false);
              reload();
            }}
            onCancel={() => setAdding(false)}
          />
        )}

        {project.songs.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground" data-testid="project-songs-empty">
            No songs in this project yet.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {project.songs.map((song) => (
              <li key={song.id} className="rounded-xl border border-border/60 p-4" data-testid="project-song-item">
                <h3 className="text-base font-medium [overflow-wrap:anywhere]">{song.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {song.version_count} {song.version_count === 1 ? "version" : "versions"}
                  {song.latest_version_number ? ` · Latest Version ${song.latest_version_number}` : ""}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link href={`/songs/${encodeURIComponent(song.id)}`} aria-label={`Open song: ${song.title}`} className={cn(buttonVariants({ variant: "outline", size: "sm" }))}>
                    Open Song <ArrowRightIcon aria-hidden="true" />
                  </Link>
                  <RemoveSongButton projectId={project.id} songId={song.id} songTitle={song.title} onRemoved={reload} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function BackToProjects() {
  return (
    <Link href="/projects" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4")}>
      <ArrowLeftIcon aria-hidden="true" /> Projects
    </Link>
  );
}

function EditProjectForm({ project, onSaved, onCancel }: { project: ProjectDetailsData; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
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
      await updateProject(project.id, { name: trimmed, description: description.trim() });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save this project. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      aria-label="Edit project"
      onSubmit={onSubmit}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
      className="mt-4 flex max-w-xl flex-col gap-3 rounded-xl border border-border/60 p-4"
      data-testid="edit-project-form"
    >
      <label className="flex flex-col gap-1 text-sm">
        Project name
        <Input value={name} maxLength={200} autoFocus onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Description
        <Textarea value={description} maxLength={2000} rows={2} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DeleteProjectButton({ projectId, projectName }: { projectId: string; projectName: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onConfirm() {
    setBusy(true);
    setError(null);
    try {
      await deleteProject(projectId);
      router.push("/projects");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete this project. Please try again.");
      setBusy(false);
    }
  }

  if (!confirming) {
    return (
      <Button type="button" size="sm" variant="destructive" onClick={() => setConfirming(true)}>
        Delete Project
      </Button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-destructive/40 p-3 text-sm" role="alertdialog" aria-label={`Delete ${projectName}?`} data-testid="delete-project-confirm">
      <p>
        Delete <strong>{projectName}</strong>? Deleting this project will not delete its songs or audio — they will just no longer be grouped
        together.
      </p>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="destructive" onClick={onConfirm} disabled={busy}>
          {busy ? "Deleting…" : "Yes, delete project"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setConfirming(false)} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function RemoveSongButton({ projectId, songId, songTitle, onRemoved }: { projectId: string; songId: string; songTitle: string; onRemoved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    setBusy(true);
    setError(null);
    try {
      await removeSongFromProject(projectId, songId);
      onRemoved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove this song. Please try again.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <Button type="button" size="sm" variant="outline" aria-label={`Remove ${songTitle} from this project`} onClick={onClick} disabled={busy}>
        {busy ? "Removing…" : "Remove from Project"}
      </Button>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function AddSongPanel({
  projectId,
  existingIds,
  onAdded,
  onCancel,
}: {
  projectId: string;
  existingIds: Set<string>;
  onAdded: () => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SongSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addingId, setAddingId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      listSongSummaries({ query, signal: controller.signal })
        .then(setResults)
        .catch((e) => {
          if (controller.signal.aborted) return;
          setError(e instanceof ApiError ? e.message : "Could not search your songs.");
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  async function add(songId: string) {
    setAddingId(songId);
    setError(null);
    try {
      await addSongToProject(projectId, songId);
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add this song. Please try again.");
      setAddingId(null);
    }
  }

  const candidates = (results ?? []).filter((s) => !existingIds.has(s.id));

  return (
    <div
      className="mt-4 flex flex-col gap-3 rounded-xl border border-border/60 p-4"
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
      data-testid="add-song-panel"
    >
      <label className="flex flex-col gap-1 text-sm">
        Search your songs
        <Input value={query} autoFocus placeholder="Title or description" maxLength={100} onChange={(e) => setQuery(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {candidates.length === 0 && results !== null && (
          <li className="text-sm text-muted-foreground" data-testid="add-song-empty">
            {query ? "No matching songs to add." : "All your songs are already in this project, or you have none yet."}
          </li>
        )}
        {candidates.map((song) => (
          <li key={song.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/60 p-2 text-sm" data-testid="add-song-candidate">
            <span className="[overflow-wrap:anywhere]">{song.title}</span>
            <Button type="button" size="sm" onClick={() => add(song.id)} disabled={addingId === song.id}>
              {addingId === song.id ? "Adding…" : "Add"}
            </Button>
          </li>
        ))}
      </ul>
      <Button type="button" size="sm" variant="outline" className="w-fit" onClick={onCancel}>
        Close
      </Button>
    </div>
  );
}
