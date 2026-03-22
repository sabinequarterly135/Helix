import '@testing-library/jest-dom'
import '../i18n'

// Mock ResizeObserver for Radix UI components (used by shadcn)
;(globalThis as unknown as Record<string, unknown>).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
