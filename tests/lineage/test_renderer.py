"""Tests for lineage tree renderer: tree building, filtering, winning path, mutation stats."""

from __future__ import annotations

from rich.tree import Tree as RichTree
from rich.table import Table

from api.lineage.models import LineageEvent
from api.lineage.renderer import (
    build_lineage_tree,
    build_mutation_stats_table,
    compute_mutation_stats,
    filter_events,
    trace_winning_path,
)


def _sample_lineage() -> list[LineageEvent]:
    """Build a small lineage across 2 islands for reuse across tests.

    Structure:
        seed-aaa (gen 0, island 0, fitness 0.3, seed)
        +-- rcc-bbb  (gen 1, island 0, fitness 0.5, rcc)
        |   +-- rcc-ddd  (gen 2, island 0, fitness 0.8, rcc)  <-- best
        +-- struct-ccc (gen 1, island 0, fitness 0.4, structural, rejected)
        seed-eee (gen 0, island 1, fitness 0.35, seed)
        +-- fresh-fff (gen 1, island 1, fitness 0.6, fresh)
    """
    return [
        LineageEvent(
            candidate_id="seed-aaa-1111",
            parent_ids=[],
            generation=0,
            island=0,
            fitness_score=0.3,
            mutation_type="seed",
        ),
        LineageEvent(
            candidate_id="rcc-bbb-2222",
            parent_ids=["seed-aaa-1111"],
            generation=1,
            island=0,
            fitness_score=0.5,
            mutation_type="rcc",
        ),
        LineageEvent(
            candidate_id="struct-ccc-3333",
            parent_ids=["seed-aaa-1111"],
            generation=1,
            island=0,
            fitness_score=0.4,
            mutation_type="structural",
            rejected=True,
        ),
        LineageEvent(
            candidate_id="rcc-ddd-4444",
            parent_ids=["rcc-bbb-2222"],
            generation=2,
            island=0,
            fitness_score=0.8,
            mutation_type="rcc",
        ),
        LineageEvent(
            candidate_id="seed-eee-5555",
            parent_ids=[],
            generation=0,
            island=1,
            fitness_score=0.35,
            mutation_type="seed",
        ),
        LineageEvent(
            candidate_id="fresh-fff-6666",
            parent_ids=["seed-eee-5555"],
            generation=1,
            island=1,
            fitness_score=0.6,
            mutation_type="fresh",
        ),
    ]


# ---- filter_events ----


class TestFilterEvents:
    def test_no_filters_returns_all(self):
        events = _sample_lineage()
        result = filter_events(events)
        assert len(result) == 6

    def test_filter_by_island(self):
        events = _sample_lineage()
        result = filter_events(events, island=1)
        assert len(result) == 2
        assert all(e.island == 1 for e in result)

    def test_filter_by_gen_min(self):
        events = _sample_lineage()
        result = filter_events(events, gen_min=1)
        assert all(e.generation >= 1 for e in result)
        assert len(result) == 4

    def test_filter_by_gen_max(self):
        events = _sample_lineage()
        result = filter_events(events, gen_max=0)
        assert all(e.generation <= 0 for e in result)
        assert len(result) == 2

    def test_filter_by_gen_range(self):
        events = _sample_lineage()
        result = filter_events(events, gen_min=1, gen_max=1)
        assert all(e.generation == 1 for e in result)
        assert len(result) == 3

    def test_filter_by_min_fitness(self):
        events = _sample_lineage()
        result = filter_events(events, min_fitness=0.5)
        assert all(e.fitness_score >= 0.5 for e in result)
        assert len(result) == 3

    def test_filters_compose(self):
        events = _sample_lineage()
        result = filter_events(events, island=0, min_fitness=0.5)
        assert len(result) == 2
        assert all(e.island == 0 and e.fitness_score >= 0.5 for e in result)


# ---- trace_winning_path ----


class TestTraceWinningPath:
    def test_traces_from_best_to_seed(self):
        events = _sample_lineage()
        path = trace_winning_path(events, "rcc-ddd-4444")
        assert path == {"rcc-ddd-4444", "rcc-bbb-2222", "seed-aaa-1111"}

    def test_follows_highest_fitness_parent(self):
        """When multiple parents exist, trace follows highest-fitness one."""
        events = [
            LineageEvent(
                candidate_id="parent-a",
                parent_ids=[],
                generation=0,
                island=0,
                fitness_score=0.3,
                mutation_type="seed",
            ),
            LineageEvent(
                candidate_id="parent-b",
                parent_ids=[],
                generation=0,
                island=0,
                fitness_score=0.7,
                mutation_type="seed",
            ),
            LineageEvent(
                candidate_id="child-c",
                parent_ids=["parent-a", "parent-b"],
                generation=1,
                island=0,
                fitness_score=0.9,
                mutation_type="rcc",
            ),
        ]
        path = trace_winning_path(events, "child-c")
        # Should follow parent-b (0.7) not parent-a (0.3)
        assert path == {"child-c", "parent-b"}

    def test_returns_empty_for_unknown_id(self):
        events = _sample_lineage()
        path = trace_winning_path(events, "nonexistent")
        assert path == set()

    def test_seed_is_in_path(self):
        events = _sample_lineage()
        path = trace_winning_path(events, "seed-aaa-1111")
        assert path == {"seed-aaa-1111"}


# ---- build_lineage_tree ----


class TestBuildLineageTree:
    def test_returns_rich_tree(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        assert isinstance(tree, RichTree)

    def test_tree_label_is_lineage(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        assert "Lineage" in str(tree.label)

    def test_roots_are_seeds(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        # Two seed roots
        assert len(tree.children) == 2

    def test_node_shows_short_id(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        # First root should show first 8 chars of seed-aaa-1111
        label = str(tree.children[0].label)
        assert "seed-aaa" in label

    def test_node_shows_fitness(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        label = str(tree.children[0].label)
        assert "0.300" in label

    def test_rejected_annotation(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        # struct-ccc is child of seed-aaa, should have REJECTED
        all_labels = _collect_tree_labels(tree)
        rejected_labels = [label for label in all_labels if "REJECTED" in label]
        assert len(rejected_labels) == 1

    def test_highlight_path_styling(self):
        events = _sample_lineage()
        highlight = {"rcc-ddd-4444", "rcc-bbb-2222", "seed-aaa-1111"}
        tree = build_lineage_tree(events, highlight_path=highlight)
        # Highlighted nodes should have bold green styling
        all_labels = _collect_tree_labels(tree)
        highlighted = [label for label in all_labels if "bold green" in label]
        assert len(highlighted) >= 1

    def test_best_candidate_marked(self):
        events = _sample_lineage()
        tree = build_lineage_tree(events)
        all_labels = _collect_tree_labels(tree)
        best_labels = [label for label in all_labels if "BEST" in label]
        assert len(best_labels) == 1

    def test_multi_parent_annotation(self):
        events = [
            LineageEvent(
                candidate_id="parent-a",
                parent_ids=[],
                generation=0,
                island=0,
                fitness_score=0.3,
                mutation_type="seed",
            ),
            LineageEvent(
                candidate_id="parent-b",
                parent_ids=[],
                generation=0,
                island=0,
                fitness_score=0.7,
                mutation_type="seed",
            ),
            LineageEvent(
                candidate_id="child-c",
                parent_ids=["parent-a", "parent-b"],
                generation=1,
                island=0,
                fitness_score=0.9,
                mutation_type="rcc",
            ),
        ]
        tree = build_lineage_tree(events)
        all_labels = _collect_tree_labels(tree)
        multi_labels = [label for label in all_labels if "+1 parent" in label]
        assert len(multi_labels) == 1


# ---- compute_mutation_stats ----


class TestComputeMutationStats:
    def test_skips_seed_events(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        assert "seed" not in stats

    def test_rcc_count(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        assert stats["rcc"]["count"] == 2

    def test_structural_count(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        assert stats["structural"]["count"] == 1

    def test_fresh_count(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        assert stats["fresh"]["count"] == 1

    def test_improved_count(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        # rcc-bbb improved (0.5 > parent 0.3), rcc-ddd improved (0.8 > parent 0.5)
        assert stats["rcc"]["improved"] == 2

    def test_avg_delta(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        # rcc-bbb delta: 0.5 - 0.3 = 0.2, rcc-ddd delta: 0.8 - 0.5 = 0.3
        assert abs(stats["rcc"]["avg_delta"] - 0.25) < 0.01

    def test_structural_negative_delta(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        # struct-ccc: 0.4 - 0.3 = 0.1 (improved)
        assert stats["structural"]["improved"] == 1
        assert abs(stats["structural"]["avg_delta"] - 0.1) < 0.01


# ---- build_mutation_stats_table ----


class TestBuildMutationStatsTable:
    def test_returns_rich_table(self):
        events = _sample_lineage()
        stats = compute_mutation_stats(events)
        table = build_mutation_stats_table(stats)
        assert isinstance(table, Table)


# ---- helpers ----


def _collect_tree_labels(tree: RichTree) -> list[str]:
    """Recursively collect all node labels from a rich Tree."""
    labels = [str(tree.label)]
    for child in tree.children:
        labels.extend(_collect_tree_labels(child))
    return labels
