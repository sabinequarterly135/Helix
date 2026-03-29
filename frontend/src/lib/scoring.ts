// --- Fitness color scale ---
// Penalty-based: 0 = perfect (green), -10 = worst (red)
// 3-stop linear interpolation: red (#ef4444) → amber (#f59e0b) → green (#22c55e)

export const FITNESS_DOMAIN_MIN = -10
export const FITNESS_DOMAIN_MAX = 0

// Color stops: [r, g, b]
const COLOR_RED: [number, number, number] = [239, 68, 68]
const COLOR_AMBER: [number, number, number] = [245, 158, 11]
const COLOR_GREEN: [number, number, number] = [34, 197, 94]

function lerp3(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ]
}

/** Map a fitness score to an `rgb(r, g, b)` color string (clamped to domain). */
export function fitnessColor(score: number): string {
  // Clamp to domain [-10, 0]
  const s = Math.max(FITNESS_DOMAIN_MIN, Math.min(FITNESS_DOMAIN_MAX, score))
  let rgb: [number, number, number]
  if (s <= -2) {
    // -10 → -2 : red → amber
    const t = (s - FITNESS_DOMAIN_MIN) / (-2 - FITNESS_DOMAIN_MIN)
    rgb = lerp3(COLOR_RED, COLOR_AMBER, t)
  } else {
    // -2 → 0 : amber → green
    const t = (s - -2) / (FITNESS_DOMAIN_MAX - -2)
    rgb = lerp3(COLOR_AMBER, COLOR_GREEN, t)
  }
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
}

/** Convenience alias -- returns fitnessColor(score) as a string. */
export function scoreColor(score: number): string {
  return fitnessColor(score)
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
