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


def sort_data_table_rows(rows):
    """Sort data table rows by sequence (None pushed to end) then by id."""
    return sorted(
        rows,
        key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id),
    )


def sanitize_filename(filename: str) -> str:
    """Strip path components to prevent directory traversal on upload."""
    return os.path.basename(filename)
