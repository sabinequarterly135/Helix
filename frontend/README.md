# Helix Frontend

React web dashboard for Helix. Provides prompt management, dataset editing, evolution configuration, and real-time visualization of evolution runs.

## Setup

```bash
npm install
```

### Development

```bash
npm run dev
```

Starts the Vite dev server on `http://localhost:5173`. The backend must be running on port 8000 (or set `VITE_API_URL` to override).

### Production Build

```bash
npm run build
```

Output goes to `dist/`. The build step auto-generates the OpenAPI client first (`openapi-ts`), then runs TypeScript compilation and Vite bundling.

### Preview Production Build

```bash
npm run preview
```

### Tests

```bash
npm run test          # Single run
npm run test:watch    # Watch mode
```

Tests use Vitest + React Testing Library + jsdom. Test files live in `src/__tests__/`.

### Lint

```bash
npm run lint
```

### Regenerate OpenAPI Client

When backend API endpoints change, regenerate the TypeScript client:

```bash
# 1. Export the OpenAPI schema (backend must be running)
curl http://localhost:8000/openapi.json -o openapi.json

# 2. Generate client
npm run generate-client
```

Config is in `openapi-ts.config.ts`. The generated client goes to `src/client/`.

## Project Structure

```
src/
  client/           # Auto-generated API client (from OpenAPI schema)
  components/
    datasets/       # Case list, case editor, JSON file import
    evolution/      # Dashboard, FitnessChart, LineageGraph,
                    # DiffViewer, MutationStats, SummaryCards, CaseResults
    history/        # Run history views
    layout/         # App shell, navigation
    prompts/        # Prompt list, detail view, template editor
    ui/             # shadcn/ui primitives
  hooks/
    useEvolutionSocket.ts  # WebSocket connection for live evolution data
    useModels.ts           # Model browser/selection
    useRunResults.ts       # Fetch completed run results
  pages/            # Route-level page components
    PromptsPage         # Prompt listing
    PromptDatasetPage   # Dataset management
    PromptEvolutionPage # Evolution configuration + live dashboard
    PromptTemplatePage  # Template editor
    PromptHistoryPage   # Run history
    RunDetailPage       # Single run deep-dive
  types/            # Shared TypeScript types
  lib/              # Utilities (cn, etc.)
```

## Key Technologies

- React 19, TypeScript 5.9, Vite 8
- Tailwind CSS 4 with shadcn/ui components
- Recharts (fitness charts), custom SVG (lineage graph, island summary)
- Monaco Editor (prompt template editing)
- TanStack Query (data fetching)
- React Router v7
- @hey-api/openapi-ts (API client generation)
