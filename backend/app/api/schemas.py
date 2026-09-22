"""Pydantic schemas for Tunora's own HTTP API — never ACE-Step's shapes."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.jobs.models import Job, JobStatus
from app.jobs.titles import derive_title
from app.director.spec import SongSpec
from app.projects.models import Project, ProjectSongEntry, ProjectSummary
from app.songs.models import Song, SongSummary, Version, VersionEntry
from app.storage.filenames import safe_audio_filename

# Job.error holds raw exception text (it can contain filesystem paths or
# provider details), so it stays in the database/logs and is never returned.
PUBLIC_FAILURE_MESSAGE = "Generation failed."

_PUBLIC_AUDIO_FIELDS = ("key", "filename", "media_type", "size_bytes")
_PUBLIC_METADATA_FIELDS = ("bpm", "genres", "key_scale", "time_signature", "prompt", "lyrics")


class CreateJobRequest(BaseModel):
    title: Optional[str] = None
    # Generate another Version of an existing Song instead of a new Song.
    song_id: Optional[str] = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    # Optional: put a brand-new Song in this Project (Phase 6). Ignored when song_id is set.
    project_id: Optional[str] = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    prompt: str
    lyrics: str = ""
    language: str = "en"
    duration: Optional[float] = None
    seed: Optional[int] = None
    instrumental: bool = False
    batch_size: Optional[int] = None


class JobResponse(BaseModel):
    id: str
    title: str
    # Tunora ids of the Song/Version this job generates (null for pre-domain rows).
    song_id: Optional[str] = None
    version_id: Optional[str] = None
    version_number: Optional[int] = None
    provider: str
    status: str
    created_at: str
    submitted_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None

    @classmethod
    def from_job(cls, job: Job, version: Optional[Version] = None) -> "JobResponse":
        return cls(
            id=job.id,
            title=job.title or derive_title(job.request.prompt),
            song_id=version.song_id if version else None,
            version_id=job.version_id,
            version_number=version.version_number if version else None,
            provider=job.provider,
            status=job.status.value,
            created_at=job.created_at.isoformat(),
            submitted_at=job.submitted_at.isoformat() if job.submitted_at else None,
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=PUBLIC_FAILURE_MESSAGE if job.status == JobStatus.FAILED else None,
            result=_public_result(job),
        )


def audio_url_for(job_id: str) -> str:
    """Tunora-owned URL of a job's audio resource (see routes_jobs.get_job_audio)."""

    return f"/api/jobs/{job_id}/audio"


def _public_result(job: Job) -> Optional[dict[str, Any]]:
    """Allowlist of result fields safe to return to clients.

    Built field by field (never copy-then-delete), so anything else the
    backend stores in Job.result -- absolute paths, provider locators -- is
    private by default. Audio is referenced by a Tunora URL, never a path.
    """

    result = job.result
    if job.status != JobStatus.COMPLETED or not isinstance(result, dict):
        return None
    audio = result.get("audio")
    if not isinstance(audio, dict):
        return None
    public_audio = {name: audio.get(name) for name in _PUBLIC_AUDIO_FIELDS}
    public_audio["filename"] = safe_audio_filename(
        audio.get("filename"), job_id=job.id, media_type=str(audio.get("media_type") or "")
    )
    public_audio["audio_url"] = audio_url_for(job.id)
    metadata = result.get("metadata") or {}
    return {
        "audio": public_audio,
        "duration": result.get("duration"),
        "metadata": {name: metadata[name] for name in _PUBLIC_METADATA_FIELDS if name in metadata},
    }


# -- Songs (Phase 5A) ---------------------------------------------------------------------------


class LatestVersionSummary(BaseModel):
    version_number: int
    duration: Optional[float] = None
    created_at: str


class ProjectRef(BaseModel):
    """The minimum needed to link to a Project from a Song: never its description or song list."""

    id: str
    name: str


class SongSummaryResponse(BaseModel):
    id: str
    title: str
    version_count: int
    latest_version: LatestVersionSummary
    created_at: str
    updated_at: str
    # None when the song is not in any Project (Phase 6).
    project: Optional[ProjectRef] = None


class SongListResponse(BaseModel):
    items: list[SongSummaryResponse]


class VersionAudioResponse(BaseModel):
    filename: str
    media_type: str
    size_bytes: int
    audio_url: str


class VersionResponse(BaseModel):
    id: str
    version_number: int
    is_latest: bool
    # How this version was made (ORIGINAL / EXTEND / REMIX / REPAINT) and, for the creative
    # operations, which version of the SAME song it was made from (a number, never an id).
    operation: str = "ORIGINAL"
    source_version_number: Optional[int] = None
    status: str
    created_at: str
    duration: Optional[float] = None
    # Null when the version has no stored audio (failed, still generating, or never completed).
    audio: Optional[VersionAudioResponse] = None
    prompt: str
    lyrics: str
    language: str
    instrumental: bool
    seed: Optional[int] = None


class SongDetailsResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    versions: list[VersionResponse]
    project: Optional[ProjectRef] = None


def _project_ref(project_id: Optional[str], projects: dict[str, Project]) -> Optional[ProjectRef]:
    project = projects.get(project_id) if project_id else None
    return ProjectRef(id=project.id, name=project.name) if project else None


def song_summary_response(summary: SongSummary, projects: Optional[dict[str, Project]] = None) -> SongSummaryResponse:
    latest = summary.latest
    return SongSummaryResponse(
        id=summary.song.id,
        title=summary.song.title,
        version_count=summary.version_count,
        latest_version=LatestVersionSummary(
            version_number=latest.version_number,
            duration=latest.audio.duration if latest.audio else None,
            created_at=latest.created_at.isoformat(),
        ),
        created_at=summary.song.created_at.isoformat(),
        updated_at=summary.song.updated_at.isoformat(),
        project=_project_ref(summary.song.project_id, projects or {}),
    )


def song_details_response(
    song: Song, entries: list[VersionEntry], project: Optional[Project] = None
) -> SongDetailsResponse:
    """Built field by field: no storage key, absolute path, provider name or task id can leak."""

    # "Latest" is the newest version that has audio: a failed or still-generating version is not.
    playable = [e.version.version_number for e in entries if e.version.audio is not None]
    latest_number = max(playable) if playable else max((e.version.version_number for e in entries), default=None)
    number_by_id = {e.version.id: e.version.version_number for e in entries}
    versions = []
    for entry in entries:
        v = entry.version
        audio = None
        if v.audio is not None and entry.job_id:
            audio = VersionAudioResponse(
                filename=safe_audio_filename(v.audio.filename, job_id=entry.job_id, media_type=v.audio.media_type),
                media_type=v.audio.media_type,
                size_bytes=v.audio.size_bytes,
                audio_url=audio_url_for(entry.job_id),
            )
        versions.append(
            VersionResponse(
                id=v.id,
                version_number=v.version_number,
                is_latest=v.version_number == latest_number,
                operation=v.operation,
                source_version_number=number_by_id.get(v.source_version_id) if v.source_version_id else None,
                status=entry.job_status or "CREATED",
                created_at=v.created_at.isoformat(),
                duration=v.audio.duration if v.audio else None,
                audio=audio,
                prompt=v.spec.prompt,
                lyrics=v.spec.lyrics,
                language=v.spec.language,
                instrumental=v.spec.instrumental,
                seed=v.spec.seed,
            )
        )
    return SongDetailsResponse(
        id=song.id,
        title=song.title,
        created_at=song.created_at.isoformat(),
        updated_at=song.updated_at.isoformat(),
        versions=versions,
        project=ProjectRef(id=project.id, name=project.name) if project else None,
    )


class VersionOperationRequest(BaseModel):
    """Body of POST /api/songs/{song_id}/versions/{version_id}/{operation}.

    Which fields apply depends on the operation (extend: extend_seconds; remix: prompt,
    remix_strength; repaint: prompt, repaint_start, repaint_end); the service validates them.
    """

    prompt: Optional[str] = Field(default=None, max_length=1000)
    lyrics: Optional[str] = Field(default=None, max_length=5000)
    extend_seconds: Optional[float] = Field(default=None, allow_inf_nan=False)
    repaint_start: Optional[float] = Field(default=None, allow_inf_nan=False)
    repaint_end: Optional[float] = Field(default=None, allow_inf_nan=False)
    remix_strength: Optional[float] = Field(default=None, allow_inf_nan=False)


# -- Projects (Phase 6) ---------------------------------------------------------------------------
#
# A Project is organizational metadata only: it never carries audio, a Version or a storage
# path, so none of that can leak through these responses by construction.


class CreateProjectRequest(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=2000)


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class AssignSongRequest(BaseModel):
    """Body of POST /api/projects/{project_id}/songs: add an EXISTING song by id."""

    song_id: str = Field(max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str


class ProjectSummaryResponse(ProjectResponse):
    song_count: int


class ProjectListResponse(BaseModel):
    items: list[ProjectSummaryResponse]


class ProjectSongResponse(BaseModel):
    """One Song inside a Project: enough to link to Song Details, no Version/audio detail
    (Song Details already owns that)."""

    id: str
    title: str
    version_count: int
    latest_version_number: Optional[int] = None
    created_at: str
    updated_at: str


class ProjectDetailsResponse(ProjectResponse):
    songs: list[ProjectSongResponse]


def project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


def project_summary_response(summary: ProjectSummary) -> ProjectSummaryResponse:
    return ProjectSummaryResponse(**project_response(summary.project).model_dump(), song_count=summary.song_count)


def project_details_response(project: Project, entries: list[ProjectSongEntry]) -> ProjectDetailsResponse:
    songs = [
        ProjectSongResponse(
            id=e.song.id,
            title=e.song.title,
            version_count=e.version_count,
            latest_version_number=e.latest_version_number,
            created_at=e.song.created_at.isoformat(),
            updated_at=e.song.updated_at.isoformat(),
        )
        for e in entries
    ]
    return ProjectDetailsResponse(**project_response(project).model_dump(), songs=songs)


# -- AI Song Director (Phase 7) -----------------------------------------------------------------
#
# The Director never generates audio; it only turns natural language into a SongSpec the
# user reviews. `SongPlanResponse` is built field by field from a validated `SongSpec`, so it
# can never carry an ACE-Step task id, internal path, or any other provider-owned detail.


class CreateSongPlanRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    # The user's own explicit choices, if any -- the Director must never override these.
    instrumental: bool = False
    language: Optional[str] = Field(default=None, max_length=10)
    duration: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    title: Optional[str] = Field(default=None, max_length=80)


class SongPlanResponse(BaseModel):
    title: str
    prompt: str
    lyrics: str
    language: str
    duration: Optional[float] = None
    instrumental: bool
    # Informational hints only -- never sent to generation, never guaranteed (see
    # docs/PHASE-7-AI-SONG-DIRECTOR.md, "No fake capabilities").
    bpm: Optional[int] = None
    key_scale: Optional[str] = None
    time_signature: Optional[str] = None
    # Which fields above are the user's OWN explicit choice rather than an AI guess.
    requested_fields: list[str] = Field(default_factory=list)


def song_plan_response(spec: SongSpec) -> SongPlanResponse:
    return SongPlanResponse(
        title=spec.title,
        prompt=spec.prompt,
        lyrics=spec.lyrics,
        language=spec.language,
        duration=spec.duration,
        instrumental=spec.instrumental,
        bpm=spec.bpm,
        key_scale=spec.key_scale,
        time_signature=spec.time_signature,
        requested_fields=sorted(spec.requested_fields),
    )


# -- AI Song Director: plan refinement (Phase 8) ---------------------------------------------
#
# Refinement is stateless, like planning: it creates no Song, Version or Job. The incoming
# `SongSpecPayload` is the plan the user currently has on screen (possibly already edited),
# never a stored/trusted record -- so it is bounded exactly like `SongPlanResponse`'s own
# fields, not treated as safe just because it round-tripped through the client once.


class SongSpecPayload(BaseModel):
    title: str = Field(default="", max_length=80)
    prompt: str = Field(min_length=1, max_length=2000)
    lyrics: str = Field(default="", max_length=5000)
    language: str = Field(default="", max_length=10)
    duration: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    instrumental: bool = False
    bpm: Optional[int] = Field(default=None, ge=0, le=1000)
    key_scale: Optional[str] = Field(default=None, max_length=40)
    time_signature: Optional[str] = Field(default=None, max_length=10)
    requested_fields: list[str] = Field(default_factory=list)

    def to_spec(self) -> SongSpec:
        return SongSpec(
            title=self.title,
            prompt=self.prompt,
            lyrics=self.lyrics,
            language=self.language,
            duration=self.duration,
            instrumental=self.instrumental,
            bpm=self.bpm,
            key_scale=self.key_scale,
            time_signature=self.time_signature,
            requested_fields=frozenset(self.requested_fields),
        )


class RefineSongPlanRequest(BaseModel):
    song_spec: SongSpecPayload
    instruction: str = Field(min_length=1, max_length=500)
