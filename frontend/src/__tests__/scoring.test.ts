import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { createElement } from 'react'
import {
  fitnessColor,
  scoreColor,
  getDotRadius,
  REJECTED_OPACITY,
  ACTIVE_OPACITY,
  FITNESS_DOMAIN_MIN,
  FITNESS_DOMAIN_MAX,
  ISLAND_COLORS,
} from '../lib/scoring'
import { FitnessLegend } from '../components/evolution/FitnessLegend'

describe('scoring.ts', () => {
  describe('fitnessColor', () => {
    // d3 scaleLinear returns rgb() format strings
    it('returns green for score 0 (perfect)', () => {
      expect(fitnessColor(0)).toBe('rgb(34, 197, 94)')
    })

    it('returns red for score -10 (worst)', () => {
      expect(fitnessColor(-10)).toBe('rgb(239, 68, 68)')
    })

    it('returns amber for score -2 (mid-range)', () => {
      expect(fitnessColor(-2)).toBe('rgb(245, 158, 11)')
    })

    it('clamps to red for values below domain min (-15)', () => {
      expect(fitnessColor(-15)).toBe('rgb(239, 68, 68)')
    })

    it('clamps to green for values above domain max (5)', () => {
      expect(fitnessColor(5)).toBe('rgb(34, 197, 94)')
    })
  })

  describe('scoreColor', () => {
    it('returns same value as fitnessColor for the same input', () => {
      expect(scoreColor(0)).toBe(fitnessColor(0))
      expect(scoreColor(-10)).toBe(fitnessColor(-10))
      expect(scoreColor(-2)).toBe(fitnessColor(-2))
      expect(scoreColor(-5)).toBe(fitnessColor(-5))
    })
  })

  describe('getDotRadius', () => {
    it('returns 8 for score 0 (best fitness = max radius)', () => {
      expect(getDotRadius(0)).toBe(8)
    })

    it('returns value >= 5 for very negative scores (clamped min)', () => {
      expect(getDotRadius(-100)).toBe(5)
    })

    it('returns 6 for score -10', () => {
      // 8 + (-10 * 0.2) = 8 - 2 = 6
      expect(getDotRadius(-10)).toBe(6)
    })
  })

  describe('constants', () => {
    it('REJECTED_OPACITY equals 0.3', () => {
      expect(REJECTED_OPACITY).toBe(0.3)
    })

    it('ACTIVE_OPACITY equals 0.9', () => {
      expect(ACTIVE_OPACITY).toBe(0.9)
    })

    it('FITNESS_DOMAIN_MIN equals -10', () => {
      expect(FITNESS_DOMAIN_MIN).toBe(-10)
    })

    it('FITNESS_DOMAIN_MAX equals 0', () => {
      expect(FITNESS_DOMAIN_MAX).toBe(0)
    })
  })

  describe('ISLAND_COLORS', () => {
    it('is an array of length 8', () => {
      expect(Array.isArray(ISLAND_COLORS)).toBe(true)
      expect(ISLAND_COLORS.length).toBe(8)
    })

    it('all entries are hex color strings starting with #', () => {
      for (const color of ISLAND_COLORS) {
        expect(typeof color).toBe('string')
        expect(color.startsWith('#')).toBe(true)
      }
    })
  })
})

describe('FitnessLegend', () => {
  it('renders with "Fitness" title text, "-10" and "0" labels', () => {
    const { container } = render(
      createElement('svg', null, createElement(FitnessLegend, { x: 0, y: 0 }))
    )
    const texts = container.querySelectorAll('text')
    const textContents = Array.from(texts).map((t) => t.textContent)
    expect(textContents).toContain('Fitness')
    expect(textContents).toContain('-10')
    expect(textContents).toContain('0')
  })

  it('renders a gradient rect element', () => {
    const { container } = render(
      createElement('svg', null, createElement(FitnessLegend, { x: 10, y: 20 }))
    )
    const rects = container.querySelectorAll('rect')
    expect(rects.length).toBeGreaterThanOrEqual(1)
  })

  it('accepts a custom gradientId prop', () => {
    const { container } = render(
      createElement('svg', null, createElement(FitnessLegend, { x: 0, y: 0, gradientId: 'custom-grad' }))
    )
    const gradient = container.querySelector('#custom-grad')
    expect(gradient).toBeInTheDocument()
  })
})
