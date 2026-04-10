"""Shared program serialization logic."""

from typing import Dict, List

from utils import sort_program_items


def serialize_program_items(program) -> List[Dict]:
    """Convert program items to JSON-serializable dicts, respecting mute and sort order."""
    if not program:
        return []
    items = sort_program_items(program.items)
    return [
        {"title": item.title or "", "subtitle": item.subtitle or ""}
        for item in items
        if not item.is_muted
    ]
