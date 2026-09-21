/**
 * Tunora API client for Projects (Phase 6). Mirrors backend/app/api/schemas.py
 * (Project* request/response models). A Project only ever carries a name,
 * description and its songs' organizational data -- never audio or Version
 * detail, so nothing here can leak provider or storage internals.
 */

import { ApiError } from "@/lib/api/jobs";

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary extends Project {
  song_count: number;
}

export interface ProjectSong {
  id: string;
  title: string;
  version_count: number;
  latest_version_number: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetails extends Project {
  songs: ProjectSong[];
}

export type ProjectSort = "newest" | "oldest" | "title";

const LOAD_LIST_ERROR = "Could not load your projects. Please try again.";
const LOAD_ERROR = "Could not load this project. Please try again.";
const NETWORK_ERROR = "Can't reach the Tunora service. Check that it is running and try again.";
const SAVE_ERROR = "Could not save this project. Please try again.";

async function request<T>(
  url: string,
  init: RequestInit | undefined,
  notFoundMessage: string,
  genericMessage: string,
): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", ...init });
  } catch (error) {
    console.error("project request network failure", error);
    throw new ApiError("network", NETWORK_ERROR);
  }
  if (response.status === 204) return null;
  if (response.status === 404 || response.status === 422) {
    // A malformed id and an unknown project look the same to a user.
    let detail = notFoundMessage;
    try {
      const body = (await response.json()) as { detail?: string };
      if (response.status === 422 && body.detail) detail = body.detail; // e.g. "Project name is required."
    } catch {
      /* keep the default message */
    }
    throw new ApiError(response.status === 422 ? "validation" : "not_found", detail);
  }
  if (!response.ok) {
    console.error("project request failed", response.status);
    throw new ApiError("server", genericMessage);
  }
  try {
    const text = await response.text();
    return text ? (JSON.parse(text) as T) : null;
  } catch (error) {
    console.error("project request returned unreadable body", error);
    throw new ApiError("server", genericMessage);
  }
}

export async function listProjects(
  options: { query?: string; sort?: ProjectSort; signal?: AbortSignal } = {},
): Promise<ProjectSummary[]> {
  const params = new URLSearchParams({ sort: options.sort ?? "newest" });
  const query = (options.query ?? "").trim();
  if (query) params.set("q", query.slice(0, 100));
  const body = await request<{ items: ProjectSummary[] }>(
    `/api/projects?${params.toString()}`,
    { signal: options.signal },
    LOAD_LIST_ERROR,
    LOAD_LIST_ERROR,
  );
  return body?.items ?? [];
}

export function getProjectDetails(projectId: string, options: { signal?: AbortSignal } = {}): Promise<ProjectDetails> {
  return request<ProjectDetails>(`/api/projects/${encodeURIComponent(projectId)}`, { signal: options.signal }, "We couldn't find that project.", LOAD_ERROR) as Promise<ProjectDetails>;
}

export function createProject(name: string, description = ""): Promise<Project> {
  return request<Project>(
    "/api/projects",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }) },
    SAVE_ERROR,
    SAVE_ERROR,
  ) as Promise<Project>;
}

export function updateProject(projectId: string, changes: { name?: string; description?: string }): Promise<Project> {
  return request<Project>(
    `/api/projects/${encodeURIComponent(projectId)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) },
    "We couldn't find that project.",
    SAVE_ERROR,
  ) as Promise<Project>;
}

export async function deleteProject(projectId: string): Promise<void> {
  await request<null>(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" }, "We couldn't find that project.", "Could not delete this project. Please try again.");
}

/** Adds an EXISTING song to a project. Creates nothing: no song, version, job or audio file. */
export function addSongToProject(projectId: string, songId: string): Promise<ProjectSong> {
  return request<ProjectSong>(
    `/api/projects/${encodeURIComponent(projectId)}/songs`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ song_id: songId }) },
    "Project or song not found.",
    "Could not add this song. Please try again.",
  ) as Promise<ProjectSong>;
}

/** Removes a song from a project. The song, its versions and its audio are untouched. */
export async function removeSongFromProject(projectId: string, songId: string): Promise<void> {
  await request<null>(
    `/api/projects/${encodeURIComponent(projectId)}/songs/${encodeURIComponent(songId)}`,
    { method: "DELETE" },
    "Project or song not found.",
    "Could not remove this song. Please try again.",
  );
}
