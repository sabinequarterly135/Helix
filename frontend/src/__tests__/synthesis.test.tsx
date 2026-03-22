import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PersonaEditor } from '../components/datasets/PersonaEditor'
import type { Persona } from '../components/datasets/PersonaCard'

// Mock shadcn UI components to render as plain HTML elements
vi.mock('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string; size?: string }) => (
    <button {...props}>{children}</button>
  ),
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode; value?: string; onValueChange?: (v: string) => void }) => (
    <div data-testid="select">{children}</div>
  ),
  SelectTrigger: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <button className={className}>{children}</button>
  ),
  SelectValue: () => <span />,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => (
    <option value={value}>{children}</option>
  ),
}))

// Mocks needed by SynthesisDialog
vi.mock('@/lib/api-config', () => ({
  getApiBaseUrl: () => '',
  getWsBaseUrl: () => 'ws://localhost:8000',
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('lucide-react', () => ({
  UserPlus: () => <span>UserPlus</span>,
  Download: () => <span>Download</span>,
  Upload: () => <span>Upload</span>,
  Wrench: () => <span>Wrench</span>,
  Pencil: () => <span>Pencil</span>,
  Trash2: () => <span>Trash2</span>,
}))

const samplePersona: Persona = {
  id: 'confused-customer',
  role: 'Confused Customer',
  traits: ['impatient', 'verbose'],
  communication_style: 'short sentences',
  goal: 'Get help with billing',
  edge_cases: ['Asks same question twice', 'Provides invalid input'],
  behavior_criteria: ['Should use simple language', 'Must stay in character'],
  language: 'en',
  channel: 'text',
}

describe('PersonaEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all persona fields for editing', () => {
    const onSave = vi.fn()
    const onCancel = vi.fn()

    render(<PersonaEditor persona={samplePersona} onSave={onSave} onCancel={onCancel} />)

    // ID field should be disabled in edit mode
    const idInput = screen.getByDisplayValue('confused-customer') as HTMLInputElement
    expect(idInput).toBeDisabled()

    // Role
    expect(screen.getByDisplayValue('Confused Customer')).toBeInTheDocument()

    // Traits (comma-joined)
    expect(screen.getByDisplayValue('impatient, verbose')).toBeInTheDocument()

    // Communication style
    expect(screen.getByDisplayValue('short sentences')).toBeInTheDocument()

    // Goal
    expect(screen.getByDisplayValue('Get help with billing')).toBeInTheDocument()

    // Edge cases and behavior criteria are in textareas (newline-joined values)
    // Query all textareas and verify by their values since multiline getByDisplayValue is unreliable
    const textareas = document.querySelectorAll('textarea') as NodeListOf<HTMLTextAreaElement>
    const textareaValues = Array.from(textareas).map((t) => t.value)

    // Goal textarea
    expect(textareaValues).toContain('Get help with billing')
    // Edge cases (newline-joined)
    expect(textareaValues).toContain('Asks same question twice\nProvides invalid input')
    // Behavior criteria (newline-joined)
    expect(textareaValues).toContain('Should use simple language\nMust stay in character')
  })

  it('calls onSave with updated persona data', async () => {
    const onSave = vi.fn()
    const onCancel = vi.fn()

    render(<PersonaEditor persona={samplePersona} onSave={onSave} onCancel={onCancel} />)

    // Change the role field
    const roleInput = screen.getByDisplayValue('Confused Customer')
    fireEvent.change(roleInput, { target: { value: 'Angry Customer' } })

    // Click Update button
    fireEvent.click(screen.getByText('Update'))

    expect(onSave).toHaveBeenCalledTimes(1)
    const savedPersona = onSave.mock.calls[0][0] as Persona
    expect(savedPersona.role).toBe('Angry Customer')
    // Other fields should be preserved
    expect(savedPersona.id).toBe('confused-customer')
    expect(savedPersona.traits).toEqual(['impatient', 'verbose'])
    expect(savedPersona.communication_style).toBe('short sentences')
    expect(savedPersona.goal).toBe('Get help with billing')
  })

  it('disables save when role is empty', () => {
    const onSave = vi.fn()
    const onCancel = vi.fn()

    // Create mode (no persona prop)
    render(<PersonaEditor onSave={onSave} onCancel={onCancel} />)

    // Create button should be disabled (both id and role are empty)
    const createButton = screen.getByText('Create')
    expect(createButton).toBeDisabled()

    // Fill in only the id field -- find the input with placeholder "persona-id"
    const idInput = screen.getByPlaceholderText('persona-id')
    fireEvent.change(idInput, { target: { value: 'my-persona' } })

    // Create should still be disabled because role is empty
    expect(createButton).toBeDisabled()
  })
})

describe('SynthesisDialog conversation parameters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders conversation parameter inputs', async () => {
    // SynthesisDialog uses fetch + WebSocket; mock global fetch for personas endpoint
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    } as Response)

    // Dynamic import after mocks are set up
    const { SynthesisDialog } = await import('../components/datasets/SynthesisDialog')

    render(
      <SynthesisDialog
        promptId="test-prompt"
        open={true}
        onOpenChange={() => {}}
        onComplete={() => {}}
      />
    )

    // Wait for persona loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading personas...')).not.toBeInTheDocument()
    })

    // Verify conversation parameter labels
    expect(screen.getByText('Conversations per persona')).toBeInTheDocument()
    expect(screen.getByText('Max turns per conversation')).toBeInTheDocument()

    // Find the number inputs and verify their default values
    const numberInputs = screen.getAllByRole('spinbutton') as HTMLInputElement[]
    expect(numberInputs.length).toBeGreaterThanOrEqual(2)

    // First number input: numConversations default = 5
    const conversationsInput = numberInputs[0]
    expect(conversationsInput.value).toBe('5')

    // Second number input: maxTurns default = 10
    const turnsInput = numberInputs[1]
    expect(turnsInput.value).toBe('10')

    // Change the conversations input and verify
    fireEvent.change(conversationsInput, { target: { value: '3' } })
    expect(conversationsInput.value).toBe('3')

    fetchSpy.mockRestore()
  })
})
