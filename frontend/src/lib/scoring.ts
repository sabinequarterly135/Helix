import { scaleLinear } from 'd3-scale'

// --- Fitness color scale ---
// Penalty-based: 0 = perfect (green), -10 = worst (red)
// Extracted from IslandsView.tsx to serve as single source of truth.

export const FITNESS_DOMAIN_MIN = -10
export const FITNESS_DOMAIN_MAX = 0

export const fitnessColor = scaleLinear<string>()
  .domain([FITNESS_DOMAIN_MIN, -2, FITNESS_DOMAIN_MAX])
  .range(['#ef4444', '#f59e0b', '#22c55e'])
  .clamp(true)

/** Convenience alias -- returns fitnessColor(score) as a string. */
export function scoreColor(score: number): string {
  return fitnessColor(score) as string
}

/** Penalty-based dot radius: 0 = large (8px, best), very negative = small (min 5px). */
export function getDotRadius(fitnessScore: number): number {
  return Math.max(5, Math.min(8, 8 + fitnessScore * 0.2))
}

// --- Opacity constants ---
export const REJECTED_OPACITY = 0.3
export const ACTIVE_OPACITY = 0.9

// --- Island palette ---
export const ISLAND_COLORS = [
  '#3b82f6',
  '#8b5cf6',
  '#14b8a6',
  '#f97316',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
  '#a855f7',
]
