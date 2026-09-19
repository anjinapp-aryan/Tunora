# Tunora Backend

Python + FastAPI backend for Tunora. Orchestrates music generation through the
`MusicGenerationProvider` abstraction (`app/providers/`) so the rest of the
application never depends on a specific AI model or its API shape.

## Setup

```bash
cd backend
uv sync
```

## Tests

```bash
# Unit tests only (mocked HTTP, no GPU/server required)
uv run pytest tests -m "not smoke"

# Include the real ACE-Step smoke test (requires the ACE-Step API server
# running locally at http://127.0.0.1:8001; generates one short real song)
uv run pytest tests -m smoke
```
