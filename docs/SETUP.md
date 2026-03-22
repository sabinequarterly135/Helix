# Setup Guide

This guide covers three ways to run Helix: local development, Docker Compose, and hosted deployment.

## Local Development

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.13+ | Backend runtime |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| Node.js | 22+ | Frontend runtime |
| npm | 10+ | Frontend package manager |

### Backend Setup

```bash
# Install Python dependencies
uv sync

# Copy environment template
cp .env.example .env
```

Edit `.env` and set at least one LLM provider API key (see [Environment Variables Reference](#environment-variables-reference) below).

Start the backend server:

```bash
uv run uvicorn api.web.app:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

The API is available at `http://localhost:8000`. The `--reload` flag enables hot reload during development.

**Database**: Helix uses SQLite by default (file-based, zero configuration). For PostgreSQL, set `GENE_DATABASE_URL` to a PostgreSQL connection string. Schema migrations run automatically on startup via `ensure_columns()` -- no manual migration commands needed.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server starts on `http://localhost:5173` and proxies `/api` and `/ws` requests to the backend on port 8000.

To build for production:

```bash
npm run build
```

This runs OpenAPI client generation, TypeScript compilation, and Vite bundling.

### Running Together

For local development, run both servers simultaneously:

- Backend on `http://localhost:8000` (API, WebSocket, SSE)
- Frontend on `http://localhost:5173` (Vite dev server with proxy to backend)

Open `http://localhost:5173` in your browser.

### Running Tests

**Backend:**

```bash
pytest                                    # All tests (skips e2e by default)
pytest tests/api/test_settings.py         # Single file
pytest tests/api/test_settings.py::test_get -x -v  # Single test, stop on first failure
pytest -m e2e                             # E2E tests (requires real API keys in .env)
```

**Frontend:**

```bash
cd frontend
npm run test                              # Vitest
```

### Linting

**Python (ruff):**

```bash
ruff check api/                           # Lint check (line-length 100, py313)
ruff format api/                          # Auto-format
```

**TypeScript (ESLint):**

```bash
cd frontend
npm run lint
```

## Docker Compose

### Production

```bash
docker compose up --build
```

This starts:
- **backend**: FastAPI server on port 8000 (internal)
- **frontend**: nginx reverse proxy on port 80 (public)
- **SQLite database**: persisted in a Docker volume (`db_data`)

Open `http://localhost` to access the dashboard.

### Development with Hot Reload

```bash
docker compose -f docker-compose.dev.yml up
```

This mounts source directories as volumes for hot reload:
- Backend source (`api/`) is mounted, uvicorn runs with `--reload`
- Frontend source is mounted, Vite dev server runs with HMR
- Backend available at `http://localhost:8000`
- Frontend available at `http://localhost:5173`

### PostgreSQL Profile

```bash
docker compose --profile postgres up --build
```

This adds a PostgreSQL 16 container. Update your `.env` to use the PostgreSQL connection string:

```
GENE_DATABASE_URL=postgresql+asyncpg://helix:helix_dev@postgres:5432/helix
POSTGRES_PASSWORD=helix_dev
```

### Environment Variables

Create a `.env` file in the project root before running Docker Compose:

```bash
cp .env.example .env
# Edit .env with your API keys
```

Docker Compose reads `.env` automatically.

### Volumes

| Volume | Purpose |
|--------|---------|
| `db_data` | SQLite database persistence |
| `pgdata` | PostgreSQL data (when using postgres profile) |
| `frontend_node_modules` | Node modules cache (dev compose only) |



## Hosted Deployment

### Frontend on Vercel

Helix's frontend is a static Vite build that can be deployed to Vercel:

1. Connect your repository to Vercel
2. Set the root directory to `frontend`
3. Build command: `npm run build`
4. Output directory: `dist`
5. Set environment variable: `VITE_API_URL=https://your-backend-url.com`

The `VITE_API_URL` variable is critical -- it tells the frontend where to find the backend API. All API calls, WebSocket connections, and SSE streams use this URL as their base.

### Backend on Railway / Fly.io

The backend can be deployed using the included Dockerfile:

1. Point your platform at the repository root
2. It will detect and use the `Dockerfile`
3. Set environment variables (see reference below)
4. For SQLite: attach a persistent volume and set `GENE_DATABASE_URL=sqlite+aiosqlite:////data/helix.db`
5. For PostgreSQL: provision a managed database and set `GENE_DATABASE_URL` to the connection string

**Important**: The backend needs a persistent volume if using SQLite, since container restarts would otherwise lose the database.

### PostgreSQL

For production deployments, PostgreSQL is recommended over SQLite:

1. Provision a managed PostgreSQL instance (Railway, Neon, Supabase, etc.)
2. Set `GENE_DATABASE_URL` to the async connection string:

```
GENE_DATABASE_URL=postgresql+asyncpg://user:password@host:5432/helix
```

Schema migrations run automatically on startup -- no manual setup required.

### Key Deployment Constraint

All frontend API and WebSocket URLs are determined by the `VITE_API_URL` environment variable at build time. This means:

- In local development, leave `VITE_API_URL` empty (Vite proxy handles routing)
- In production, set `VITE_API_URL` to the full backend URL before building

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GENE_GEMINI_API_KEY` | Yes (if using Gemini) | -- | Google Gemini API key |
| `GENE_OPENAI_API_KEY` | No | -- | OpenAI API key |
| `GENE_OPENROUTER_API_KEY` | No | -- | OpenRouter API key |
| `GENE_ANTHROPIC_API_KEY` | No | -- | Anthropic API key |
| `GENE_DATABASE_URL` | No | `sqlite+aiosqlite:///helix.db` | Database connection string |
| `GENE_META_MODEL` | No | `gemini/gemini-2.5-pro` | Meta (critic/author) model |
| `GENE_META_PROVIDER` | No | `gemini` | Meta model provider |
| `GENE_TARGET_MODEL` | No | `gemini/gemini-2.0-flash` | Target (evaluation) model |
| `GENE_TARGET_PROVIDER` | No | `gemini` | Target model provider |
| `GENE_JUDGE_MODEL` | No | `gemini/gemini-2.5-flash` | Judge (scoring) model |
| `GENE_JUDGE_PROVIDER` | No | `gemini` | Judge model provider |

| `GENE_CONCURRENCY_LIMIT` | No | `10` | Max concurrent LLM requests |
| `CORS_ORIGINS` | No | `*` | Allowed CORS origins |
| `VITE_API_URL` | No (dev) / Yes (prod) | -- | Backend URL for frontend builds |
| `POSTGRES_PASSWORD` | No | `helix_dev` | PostgreSQL password (Docker only) |

At least one provider API key is required. Set the key for whichever provider(s) you plan to use.
