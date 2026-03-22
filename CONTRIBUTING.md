# Contributing to Helix

Thank you for considering contributing to Helix. This document covers the workflow, code style, testing, and pull request process.

## How to Contribute

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/your-username/helix.git`
3. **Create a branch** for your change: `git checkout -b feat/your-feature`
4. **Make your changes** (see code style and testing sections below)
5. **Commit** with a conventional commit message
6. **Push** to your fork: `git push origin feat/your-feature`
7. **Open a Pull Request** against `main`

## Development Setup

See [docs/SETUP.md](docs/SETUP.md) for detailed instructions on setting up the backend, frontend, and Docker environment.

Quick start:

```bash
uv sync                    # Backend dependencies
cd frontend && npm install # Frontend dependencies
cp .env.example .env       # Configure API keys
```

## Code Style

### Python

- **Formatter/linter**: [ruff](https://docs.astral.sh/ruff/) (line-length 100, target py313)
- **Future annotations**: Always include `from __future__ import annotations` at the top of every module
- **Type hints**: Use `X | None` instead of `Optional[X]`, `list[T]` instead of `List[T]`
- **Async**: Use `async/await` for all database and LLM operations

Run before committing:

```bash
ruff check api/
ruff format api/
```

### TypeScript

- **Linter**: ESLint (project config in `frontend/eslint.config.js`)
- **Path aliases**: Use `@/` for imports from `frontend/src/` (e.g., `import { Button } from "@/components/ui/button"`)
- **Components**: shadcn/ui primitives in `components/ui/`, application components alongside their pages

Run before committing:

```bash
cd frontend
npm run lint
```

## Testing

### Backend (pytest)

```bash
pytest                           # All tests (excludes e2e)
pytest tests/path/to/test.py    # Single file
pytest -x -v                     # Stop on first failure, verbose
```

- Test framework: `pytest` with `pytest-asyncio` (async mode: auto)
- API tests use `httpx.ASGITransport` with FastAPI dependency overrides
- All tests must pass before merging

### Frontend (vitest)

```bash
cd frontend
npm run test
```

## Commit Messages

Use [conventional commits](https://www.conventionalcommits.org/):

```
feat: add new scoring strategy
fix: handle null tool_calls in evaluator
docs: update setup guide for PostgreSQL
refactor: extract provider config to registry
test: add cases for Boltzmann selection edge cases
chore: update ruff to 0.5.0
```

Format: `type: short description` (lowercase, no period at end).

## Pull Requests

When opening a PR, please include:

- **Summary**: What the PR does and why
- **Testing**: How you verified the changes work (test commands, manual steps)
- **Screenshots**: If the change affects the UI

PRs are reviewed for correctness, code style, and test coverage. Keep PRs focused on a single concern when possible.

## Reporting Issues

Open a GitHub issue with:

- Steps to reproduce the problem
- Expected vs. actual behavior
- Environment details (OS, Python version, Node version, browser)
- Relevant logs or error messages

## License

By contributing to Helix, you agree that your contributions will be licensed under the [MIT License](LICENSE).
