"""Lineage tree renderer: visualize candidate ancestry as rich trees.

Transforms flat LineageEvent lists into visual trees with filtering,
winning path highlighting, and mutation effectiveness statistics.
"""

from __future__ import annotations

from rich.table import Table
from rich.tree import Tree as RichTree

from api.lineage.models import LineageEvent


def filter_events(
    events: list[LineageEvent],
    *,
    island: int | None = None,
    gen_min: int | None = None,
    gen_max: int | None = None,
    min_fitness: float | None = None,
) -> list[LineageEvent]:
    """Filter lineage events by island, generation range, and minimum fitness.

    All filters are AND-composed. Omitted filters are ignored.
    """
    result = events
    if island is not None:
        result = [e for e in result if e.island == island]
    if gen_min is not None:
        result = [e for e in result if e.generation >= gen_min]
    if gen_max is not None:
        result = [e for e in result if e.generation <= gen_max]
    if min_fitness is not None:
        result = [e for e in result if e.fitness_score >= min_fitness]
    return result


def trace_winning_path(events: list[LineageEvent], best_id: str) -> set[str]:
    """Walk backward from best_id following highest-fitness parent to seed.

    Returns a set of candidate IDs on the winning path.
    Returns empty set if best_id is not found in events.
    """
    index: dict[str, LineageEvent] = {e.candidate_id: e for e in events}
    if best_id not in index:
        return set()

    path: set[str] = set()
    current_id = best_id
    while current_id in index:
        path.add(current_id)
        event = index[current_id]
        if not event.parent_ids:
            break
        # Follow the highest-fitness parent
        best_parent_id = None
        best_parent_fitness = -1.0
        for pid in event.parent_ids:
            if pid in index and index[pid].fitness_score > best_parent_fitness:
                best_parent_fitness = index[pid].fitness_score
                best_parent_id = pid
        if best_parent_id is None:
            break
        current_id = best_parent_id
    return path


def build_lineage_tree(
    events: list[LineageEvent],
    highlight_path: set[str] | None = None,
) -> RichTree:
    """Build a rich.tree.Tree from flat LineageEvent list.

    Args:
        events: List of lineage events to visualize.
        highlight_path: Set of candidate IDs to style bold green.

    Returns:
        A rich Tree with correct parent-child nesting.
    """
    if highlight_path is None:
        highlight_path = set()

    index: dict[str, LineageEvent] = {e.candidate_id: e for e in events}

    # Find the best candidate (highest fitness)
    best_event = max(events, key=lambda e: e.fitness_score) if events else None
    best_id = best_event.candidate_id if best_event else None

    # Find roots: events with no parents or all parents outside the event set
    roots: list[LineageEvent] = []
    for e in events:
        if not e.parent_ids or all(pid not in index for pid in e.parent_ids):
            roots.append(e)

    # Build children index: for each event, map first parent -> children
    # Multi-parent events go under their highest-fitness parent
    children_map: dict[str, list[str]] = {}
    for e in events:
        if not e.parent_ids:
            continue
        known_parents = [pid for pid in e.parent_ids if pid in index]
        if not known_parents:
            continue
        # Pick highest-fitness parent as primary
        primary_parent = max(known_parents, key=lambda pid: index[pid].fitness_score)
        children_map.setdefault(primary_parent, []).append(e.candidate_id)

    tree = RichTree("[bold]Lineage Tree[/bold]")

    def _make_label(event: LineageEvent) -> str:
        id_short = event.candidate_id[:8]
        label = (
            f"{id_short} ({event.fitness_score:.3f}) [{event.mutation_type}] island {event.island}"
        )

        # Multi-parent annotation
        extra_parents = len(event.parent_ids) - 1
        if extra_parents > 0:
            label += f" (+{extra_parents} parent{'s' if extra_parents > 1 else ''})"

        # Rejected annotation
        if event.rejected:
            label += " [red]REJECTED[/red]"

        # Best candidate annotation
        if event.candidate_id == best_id:
            label += " [bold]BEST[/bold]"

        # Apply styling
        if event.candidate_id in highlight_path:
            label = f"[bold green]{label}[/bold green]"
        elif event.rejected:
            pass  # red annotation already in label
        elif not event.survived:
            label = f"[yellow]{label}[/yellow]"
        else:
            label = f"[dim white]{label}[/dim white]"

        return label

    def _add_children(parent_node: RichTree, parent_id: str) -> None:
        child_ids = children_map.get(parent_id, [])
        for cid in child_ids:
            child_event = index[cid]
            child_node = parent_node.add(_make_label(child_event))
            _add_children(child_node, cid)

    for root in roots:
        root_node = tree.add(_make_label(root))
        _add_children(root_node, root.candidate_id)

    return tree


def compute_mutation_stats(events: list[LineageEvent]) -> dict[str, dict]:
    """Compute per-mutation-type effectiveness statistics.

    Skips seed events. For each non-seed event, computes improvement as
    event.fitness_score - max(parent fitness scores).

    Returns:
        Dict keyed by mutation_type with keys: count, improved, avg_delta.
    """
    index: dict[str, LineageEvent] = {e.candidate_id: e for e in events}
    stats: dict[str, dict] = {}

    for event in events:
        if event.mutation_type == "seed":
            continue

        mtype = event.mutation_type
        if mtype not in stats:
            stats[mtype] = {"count": 0, "improved": 0, "total_delta": 0.0}

        stats[mtype]["count"] += 1

        # Compute delta from best parent
        parent_fitnesses = [index[pid].fitness_score for pid in event.parent_ids if pid in index]
        if parent_fitnesses:
            delta = event.fitness_score - max(parent_fitnesses)
        else:
            delta = 0.0

        stats[mtype]["total_delta"] += delta
        if delta > 0:
            stats[mtype]["improved"] += 1

    # Finalize: compute avg_delta, remove total_delta
    for _mtype, s in stats.items():
        s["avg_delta"] = s["total_delta"] / s["count"] if s["count"] > 0 else 0.0
        del s["total_delta"]

    return stats


def build_mutation_stats_table(stats: dict[str, dict]) -> Table:
    """Build a rich Table from mutation stats dict.

    Columns: Mutation Type, Count, Improved, Improvement Rate, Avg Delta.
    """
    table = Table(title="Mutation Effectiveness")
    table.add_column("Mutation Type", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Improved", justify="right")
    table.add_column("Improvement Rate", justify="right")
    table.add_column("Avg Delta", justify="right")

    for mtype, s in sorted(stats.items()):
        count = s["count"]
        improved = s["improved"]
        rate = (improved / count * 100) if count > 0 else 0.0
        table.add_row(
            mtype,
            str(count),
            str(improved),
            f"{rate:.1f}%",
            f"{s['avg_delta']:.4f}",
        )

    return table
