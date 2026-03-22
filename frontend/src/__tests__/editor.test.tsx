import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TemplateEditor from '../components/prompts/TemplateEditor'

// Mock Monaco editor as a textarea for interaction
vi.mock('@monaco-editor/react', () => ({
  default: (props: { value?: string; onChange?: (v: string) => void }) => (
    <textarea
      data-testid="monaco-editor"
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    />
  ),
}))

// Mock SDK
vi.mock('../client/sdk.gen', () => ({
  updateTemplateApiPromptsPromptIdTemplatePut: vi.fn(),
}))

import { updateTemplateApiPromptsPromptIdTemplatePut } from '../client/sdk.gen'

const mockUpdateTemplate = vi.mocked(updateTemplateApiPromptsPromptIdTemplatePut)

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

describe('TemplateEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders with initial template', () => {
    renderWithProviders(
      <TemplateEditor promptId="test" initialTemplate="Hello {{ name }}" />,
    )

    const editor = screen.getByTestId('monaco-editor') as HTMLTextAreaElement
    expect(editor.value).toBe('Hello {{ name }}')
  })

  it('save button calls updateTemplate with editor content', async () => {
    mockUpdateTemplate.mockResolvedValue({ data: {} } as never)

    renderWithProviders(
      <TemplateEditor promptId="my-prompt" initialTemplate="Hello {{ name }}" />,
    )

    const editor = screen.getByTestId('monaco-editor')
    fireEvent.change(editor, { target: { value: 'Updated {{ name }}' } })

    const saveBtn = screen.getByText('Save')
    expect(saveBtn).not.toBeDisabled()
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(mockUpdateTemplate).toHaveBeenCalledWith(
        expect.objectContaining({
          path: { prompt_id: 'my-prompt' },
          body: { template: 'Updated {{ name }}' },
        }),
      )
    })
  })

  it('save button disabled when content unchanged', () => {
    renderWithProviders(
      <TemplateEditor promptId="test" initialTemplate="Hello {{ name }}" />,
    )

    const saveBtn = screen.getByText('Save')
    expect(saveBtn).toBeDisabled()
  })

  it('cancel resets to initial template', () => {
    renderWithProviders(
      <TemplateEditor promptId="test" initialTemplate="Hello {{ name }}" />,
    )

    const editor = screen.getByTestId('monaco-editor') as HTMLTextAreaElement
    fireEvent.change(editor, { target: { value: 'Changed content' } })
    expect(editor.value).toBe('Changed content')

    fireEvent.click(screen.getByText('Cancel'))

    expect((screen.getByTestId('monaco-editor') as HTMLTextAreaElement).value).toBe(
      'Hello {{ name }}',
    )
  })
})
