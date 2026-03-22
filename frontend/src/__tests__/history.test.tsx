import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RunHistoryTable from '../components/history/RunHistoryTable'

vi.mock('../client/sdk.gen', () => ({
  listPromptsApiPromptsGet: vi.fn(),
  getHistoryApiHistoryPromptIdGet: vi.fn(),
}))

import { listPromptsApiPromptsGet, getHistoryApiHistoryPromptIdGet } from '../client/sdk.gen'

const mockListPrompts = vi.mocked(listPromptsApiPromptsGet)
const mockGetHistory = vi.mocked(getHistoryApiHistoryPromptIdGet)

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const mockRuns = [
  {
    id: 1,
    prompt_id: 'test-prompt',
    status: 'completed',
    best_fitness_score: 0.987,
    total_cost_usd: 1.234,
    generations_completed: 10,
    created_at: '2026-03-14T10:00:00Z',
    meta_model: 'gemini-2.5-pro',
    target_model: 'gemini-3-flash',
  },
  {
    id: 2,
    prompt_id: 'test-prompt',
    status: 'failed',
    best_fitness_score: null,
    total_cost_usd: 0.5,
    generations_completed: 3,
    created_at: '2026-03-13T08:00:00Z',
    meta_model: 'gemini-2.5-pro',
    target_model: 'gemini-3-flash',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockListPrompts.mockResolvedValue({
    data: [
      { id: 'test-prompt', purpose: 'Testing', template_variables: [], anchor_variables: [] },
    ],
    response: {} as Response,
    request: {} as Request,
    error: undefined,
  } as never)
})

describe('RunHistoryTable', () => {
  it('shows prompt selector message when no prompt selected', () => {
    renderWithProviders(<RunHistoryTable />)
    expect(screen.getByText('Select a prompt to view its evolution history.')).toBeInTheDocument()
  })

  it('renders run records when promptId provided via prop', async () => {
    mockGetHistory.mockResolvedValue({
      data: mockRuns,
      response: {} as Response,
      request: {} as Request,
      error: undefined,
    } as never)

    renderWithProviders(<RunHistoryTable promptId="test-prompt" />)

    await waitFor(() => {
      expect(screen.getByText('0.987')).toBeInTheDocument()
      expect(screen.getByText('$1.23')).toBeInTheDocument()
      expect(screen.getByText('--')).toBeInTheDocument()
    })
  })

  it('shows status badges with correct text', async () => {
    mockGetHistory.mockResolvedValue({
      data: mockRuns,
      response: {} as Response,
      request: {} as Request,
      error: undefined,
    } as never)

    renderWithProviders(<RunHistoryTable promptId="test-prompt" />)

    await waitFor(() => {
      expect(screen.getByText('completed')).toBeInTheDocument()
      expect(screen.getByText('failed')).toBeInTheDocument()
    })
  })

  it('formats cost as currency', async () => {
    mockGetHistory.mockResolvedValue({
      data: mockRuns,
      response: {} as Response,
      request: {} as Request,
      error: undefined,
    } as never)

    renderWithProviders(<RunHistoryTable promptId="test-prompt" />)

    await waitFor(() => {
      expect(screen.getByText('$1.23')).toBeInTheDocument()
      expect(screen.getByText('$0.50')).toBeInTheDocument()
    })
  })

  it('empty state when no runs', async () => {
    mockGetHistory.mockResolvedValue({
      data: [],
      response: {} as Response,
      request: {} as Request,
      error: undefined,
    } as never)

    renderWithProviders(<RunHistoryTable promptId="test-prompt" />)

    await waitFor(() => {
      expect(screen.getByText('No evolution runs yet')).toBeInTheDocument()
    })
  })
})
