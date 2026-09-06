import os
import re
import unicodedata


def clean_text(text: str) -> str:
    """Normalize line endings and strip whitespace from slide text."""
    if not text:
        return ""
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x0b", "\n")
        .strip()
    )


def sort_program_items(items):
    """Sort program items by sequence (None pushed to end) then by id."""
    return sorted(
        items,
        key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id),
    )


def get_slides_by_type(hymn, preferred_type: str = "PPT"):
    """Return slides of the preferred type, falling back to the other.

    Returns a list sorted by slide order.
    """
    slides = [s for s in hymn.slides if s.type == preferred_type]
    if not slides:
        fallback = "VMIX" if preferred_type == "PPT" else "PPT"
        slides = [s for s in hymn.slides if s.type == fallback or s.type is None]
    return sorted(slides, key=lambda x: x.order)


def generate_slug(name: str) -> str:
    """Generate a URL-safe slug from a name."""
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = slug.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "table"


# Whole-cell reference to another data table cell: "$<row_number>:<column name>"
CELL_REF_RE = re.compile(r"^\$(\d+):(.+)$", re.S)


def resolve_table_references(rows):
    """Resolve $N:Column cell references in a list of row dicts.

    *rows* is the table's rows in display order ({column: value} dicts).
    A cell whose entire (stripped) value matches $N:Column is replaced by
    the referenced cell's resolved value; chains are followed. Missing
    targets and circular references keep their raw text so the problem
    stays visible instead of silently vanishing.
    """

    def resolve(row_idx, col, seen):
        value = rows[row_idx].get(col, "")
        m = CELL_REF_RE.match((value or "").strip())
        if not m:
            return value
        t_row = int(m.group(1)) - 1
        if not (0 <= t_row < len(rows)):
            return value
        # Case-insensitive column match (mirrors the editor's resolver)
        wanted = m.group(2).strip().lower()
        t_col = next(
            (c for c in rows[t_row] if c.lower() == wanted), None
        )
        if t_col is None:
            return value
        key = (t_row, t_col)
        if key in seen:
            return value
        seen.add(key)
        return resolve(t_row, t_col, seen)

    return [
        {col: resolve(i, col, {(i, col)}) for col in row}
        for i, row in enumerate(rows)
    ]


def sort_data_table_rows(rows):
    """Sort data table rows by sequence (None pushed to end) then by id."""
    return sorted(
        rows,
        key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id),
    )


def sanitize_filename(filename: str) -> str:
    """Strip path components to prevent directory traversal on upload."""
    return os.path.basename(filename)
