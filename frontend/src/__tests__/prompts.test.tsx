import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PromptList from '../components/prompts/PromptList'
import PromptDetail from '../components/prompts/PromptDetail'

// Mock Monaco editor
vi.mock('@monaco-editor/react', () => ({
  default: (props: { value?: string }) => (
    <div data-testid="monaco-editor">{props.value}</div>
  ),
}))

// Mock SDK
vi.mock('../client/sdk.gen', () => ({
  listPromptsApiPromptsGet: vi.fn(),
  getPromptApiPromptsPromptIdGet: vi.fn(),
}))

import { listPromptsApiPromptsGet, getPromptApiPromptsPromptIdGet } from '../client/sdk.gen'

const mockListPrompts = vi.mocked(listPromptsApiPromptsGet)
const mockGetPrompt = vi.mocked(getPromptApiPromptsPromptIdGet)

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const samplePrompts = [
  {
    id: 'ivr-automotor',
    purpose: 'IVR call handling for auto dealership',
    template_variables: ['customer_name', 'language'],
    anchor_variables: ['greeting'],
  },
  {
    id: 'pizza-ivr',
    purpose: 'Pizza ordering IVR',
    template_variables: ['menu'],
    anchor_variables: [],
  },
]

describe('PromptList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders prompts from API', async () => {
    mockListPrompts.mockResolvedValue({ data: samplePrompts } as never)

    renderWithProviders(<PromptList />)

    await waitFor(() => {
      expect(screen.getByText('ivr-automotor')).toBeInTheDocument()
      expect(screen.getByText('pizza-ivr')).toBeInTheDocument()
    })
  })

  it('filters by search input', async () => {
    mockListPrompts.mockResolvedValue({ data: samplePrompts } as never)
    const user = userEvent.setup()

    renderWithProviders(<PromptList />)

    await waitFor(() => {
      expect(screen.getByText('ivr-automotor')).toBeInTheDocument()
    })

    await user.type(screen.getByPlaceholderText('Search prompts...'), 'pizza')

    expect(screen.queryByText('ivr-automotor')).not.toBeInTheDocument()
    expect(screen.getByText('pizza-ivr')).toBeInTheDocument()
  })

  it('shows loading state with skeleton cards', () => {
    mockListPrompts.mockReturnValue(new Promise(() => {}) as never)

    renderWithProviders(<PromptList />)

    // Loading state now uses skeleton cards instead of text
    // The search input is rendered but disabled during loading
    expect(screen.getByPlaceholderText('Search prompts...')).toBeDisabled()
  })

  it('shows empty state when no prompts match filter', async () => {
    mockListPrompts.mockResolvedValue({ data: samplePrompts } as never)
    const user = userEvent.setup()

    renderWithProviders(<PromptList />)

    await waitFor(() => {
      expect(screen.getByText('ivr-automotor')).toBeInTheDocument()
    })

    await user.type(screen.getByPlaceholderText('Search prompts...'), 'nonexistent')

    expect(screen.getByText('No prompts match your search.')).toBeInTheDocument()
  })

  it('shows empty state when no prompts exist', async () => {
    mockListPrompts.mockResolvedValue({ data: [] } as never)

    renderWithProviders(<PromptList />)

    await waitFor(() => {
      expect(screen.getByText('No prompts yet')).toBeInTheDocument()
    })
  })
})

describe('PromptDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders prompt metadata with badges', async () => {
    mockGetPrompt.mockResolvedValue({
      data: {
        id: 'ivr-automotor',
        purpose: 'IVR call handling',
        template_variables: ['customer_name'],
        anchor_variables: ['greeting'],
        template: 'Hello {{ customer_name }}',
        tools: null,
      },
    } as never)

    renderWithProviders(<PromptDetail promptId="ivr-automotor" />)

    await waitFor(() => {
      expect(screen.getByText('ivr-automotor')).toBeInTheDocument()
      expect(screen.getByText('IVR call handling')).toBeInTheDocument()
      expect(screen.getByText('customer_name')).toBeInTheDocument()
      expect(screen.getByText('greeting')).toBeInTheDocument()
    })
  })

  it('shows loading state with skeleton', () => {
    mockGetPrompt.mockReturnValue(new Promise(() => {}) as never)

    const { container } = renderWithProviders(<PromptDetail promptId="test" />)

    // Loading state now uses skeleton cards instead of "Loading prompt..." text
    // Look for skeleton elements (divs with animate-pulse class)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })
})
