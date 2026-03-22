"""Lineage tracking for prompt evolution.

Provides models and services for recording parent-child relationships
between candidates during evolutionary optimization, plus visualization
via tree rendering, filtering, and mutation statistics.
"""

from api.lineage.collector import LineageCollector
from api.lineage.models import LineageEvent
from api.lineage.renderer import (
    build_lineage_tree,
    build_mutation_stats_table,
    compute_mutation_stats,
    filter_events,
    trace_winning_path,
)

__all__ = [
    "LineageCollector",
    "LineageEvent",
    "build_lineage_tree",
    "build_mutation_stats_table",
    "compute_mutation_stats",
    "filter_events",
    "trace_winning_path",
]
