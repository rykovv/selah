"""Shared program serialization and reference resolution logic."""

from typing import Dict, List

from utils import resolve_table_references, sort_program_items

# Column names usable in $row:Column references inside the program editor
ITEM_REF_COLUMNS = ("Title", "Subtitle", "Tag")


def resolve_program_item_rows(items_sorted) -> List[Dict]:
    """Resolve $row:Column references across program items.

    Row numbers follow the editor's display order, muted items included.
    """
    rows = [
        {
            "Title": item.title or "",
            "Subtitle": item.subtitle or "",
            "Tag": item.tag or "",
        }
        for item in items_sorted
    ]
    return resolve_table_references(rows)


def annotate_display_fields(items_sorted):
    """Attach resolved display_* attributes for read-only rendering.

    Uses non-column attributes so the ORM session is never dirtied with
    resolved values.
    """
    for item, row in zip(items_sorted, resolve_program_item_rows(items_sorted)):
        item.display_title = row["Title"]
        item.display_subtitle = row["Subtitle"]
        item.display_tag = row["Tag"]
    return items_sorted


def serialize_program_items(program) -> List[Dict]:
    """Convert program items to JSON-serializable dicts, respecting mute and
    sort order. References are resolved before muted items are filtered so
    row numbers always match the editor."""
    if not program:
        return []
    items = sort_program_items(program.items)
    rows = resolve_program_item_rows(items)
    return [
        {"title": row["Title"], "subtitle": row["Subtitle"]}
        for item, row in zip(items, rows)
        if not item.is_muted
    ]
