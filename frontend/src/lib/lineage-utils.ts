import type { LineageNode } from '../types/evolution';

export interface IslandTransition {
  fromIsland: number;
  toIsland: number;
  atCandidateId: string;
}

/**
 * Trace the winning path from bestId back to seed(s) by following
 * the highest-fitness parent at each step.
 */
export function traceWinningPath(
  events: LineageNode[],
  bestId: string | null,
): Set<string> {
  if (!bestId) return new Set();
  const index = new Map<string, LineageNode>(events.map((e) => [e.candidateId, e]));
  if (!index.has(bestId)) return new Set();

  const path = new Set<string>();
  let currentId: string | null = bestId;

  while (currentId && index.has(currentId)) {
    path.add(currentId);
    const event: LineageNode = index.get(currentId)!;
    if (event.parentIds.length === 0) break;

    let bestParentId: string | null = null;
    let bestParentFitness = -Infinity;
    for (const pid of event.parentIds) {
      const parent: LineageNode | undefined = index.get(pid);
      if (parent && parent.fitnessScore > bestParentFitness) {
        bestParentFitness = parent.fitnessScore;
        bestParentId = pid;
      }
    }
    currentId = bestParentId;
  }

  return path;
}

/**
 * Deduplicate lineage events by candidateId, keeping the last event
 * for each candidate (which has the final state).
 */
export function deduplicateEvents(events: LineageNode[]): LineageNode[] {
  const map = new Map<string, LineageNode>();
  for (const e of events) {
    map.set(e.candidateId, e);
  }
  return Array.from(map.values());
}

/**
 * Detect island transitions in an ordered path of lineage nodes.
 * Returns transitions where consecutive nodes are on different islands.
 */
export function detectIslandTransitions(
  orderedPath: LineageNode[],
): IslandTransition[] {
  const transitions: IslandTransition[] = [];
  for (let i = 1; i < orderedPath.length; i++) {
    if (orderedPath[i].island !== orderedPath[i - 1].island) {
      transitions.push({
        fromIsland: orderedPath[i - 1].island,
        toIsland: orderedPath[i].island,
        atCandidateId: orderedPath[i].candidateId,
      });
    }
  }
  return transitions;
}
