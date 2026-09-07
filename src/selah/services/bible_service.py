"""Bible translations: catalog, download/cache, reference parsing/resolution.

Data source: https://github.com/Amosamevor/Bible-json
  - locale_version_map.json : {locale: {TRANSLATION NAME: ABBR}}
  - book_name_mapping.json  : {TRANSLATION NAME: {canonical book: localized}}
  - versions/<locale>/<TRANSLATION NAME>.json : {book: {chapter: {verse: text}}}

Books inside a translation file are keyed by localized names; English files
use the canonical names directly (and have no mapping entry). Selah stores
references with canonical English book names so entries survive translation
switches, and renders them with the localized names of the set's translation.

Storage:
  - bundled  : src/selah/bibles (dev) or _internal/bibles (frozen), read-only
  - download : <data_dir>/bibles/<locale>/<sanitized name>.json
"""

import json
import logging
import os
import re
import sys
import threading
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from paths import data_dir

logger = logging.getLogger(__name__)

RAW_BASE = "https://raw.githubusercontent.com/Amosamevor/Bible-json/main"

DEFAULT_TRANSLATION_ID = "en/NEW KING JAMES VERSION"

# Canonical Protestant book order (matches the English files in the repo)
CANONICAL_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai",
    "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation",
]

# Human names for the locale codes used by the repository catalog
LOCALE_NAMES = {
    "af": "Afrikaans", "ar": "Arabic", "bar": "Bavarian", "bg": "Bulgarian",
    "cs": "Czech", "da": "Danish", "de": "German", "el": "Greek",
    "en": "English", "eo": "Esperanto", "es": "Spanish", "eu": "Basque",
    "fi": "Finnish", "fr": "French", "he": "Hebrew", "hr": "Croatian",
    "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian", "it": "Italian",
    "ko": "Korean", "la": "Latin", "lt": "Lithuanian", "lv": "Latvian",
    "mi": "Maori", "nl": "Dutch", "no": "Norwegian", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "sq": "Albanian", "sv": "Swedish",
    "sw": "Swahili", "th": "Thai", "tl": "Tagalog", "tr": "Turkish",
    "uk": "Ukrainian", "vi": "Vietnamese", "zh": "Chinese", "und": "Other",
}


# ---------------------------------------------------------------------------
# Storage locations
# ---------------------------------------------------------------------------

def bundled_dir() -> str:
    """Read-only directory with the translations shipped in the install."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        internal = os.path.join(base, "_internal", "bibles")
        root = os.path.join(base, "bibles")
        return internal if os.path.exists(internal) else root
    # services/ -> src/selah/bibles
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bibles"
    )


def downloads_dir() -> str:
    """Writable directory for user-downloaded translations."""
    path = os.path.join(data_dir(), "bibles")
    os.makedirs(path, exist_ok=True)
    return path


def sanitize_filename(name: str) -> str:
    """Make a repo translation name safe as a Windows filename.

    Repo names may contain characters illegal on Windows (e.g.
    "RUSSIAN: SYNODAL TRANSLATION (1876)") — each is replaced with '_'.
    """
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def split_translation_id(tid: str) -> Tuple[str, str]:
    """'en/KING JAMES BIBLE' -> ('en', 'KING JAMES BIBLE')."""
    locale, _, name = (tid or "").partition("/")
    return locale, name


def _candidate_paths(tid: str) -> List[str]:
    locale, name = split_translation_id(tid)
    fname = sanitize_filename(name) + ".json"
    return [
        os.path.join(downloads_dir(), locale, fname),
        os.path.join(bundled_dir(), locale, fname),
    ]


def translation_path(tid: str) -> Optional[str]:
    """Local file for a translation id, or None if not installed."""
    for path in _candidate_paths(tid):
        if os.path.exists(path):
            return path
    return None


def is_installed(tid: str) -> bool:
    return translation_path(tid) is not None


def is_bundled(tid: str) -> bool:
    return os.path.exists(_candidate_paths(tid)[1])


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

_catalog_cache: Optional[Dict[str, Dict[str, str]]] = None
_book_map_cache: Optional[Dict[str, Dict[str, str]]] = None


def _load_bundled_json(filename: str) -> dict:
    with open(os.path.join(bundled_dir(), filename), encoding="utf-8") as f:
        return json.load(f)


def catalog() -> Dict[str, Dict[str, str]]:
    """{locale: {TRANSLATION NAME: ABBR}} from the vendored repo catalog."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = _load_bundled_json("locale_version_map.json")
    return _catalog_cache


def _book_mapping(name: str) -> Dict[str, str]:
    """{canonical book: localized book} for one translation (empty = English)."""
    global _book_map_cache
    if _book_map_cache is None:
        _book_map_cache = _load_bundled_json("book_name_mapping.json")
    return _book_map_cache.get(name, {})


def abbreviation(tid: str) -> str:
    locale, name = split_translation_id(tid)
    return catalog().get(locale, {}).get(name, "")


def installed_translations() -> List[dict]:
    """All locally available translations, bundled and downloaded."""
    found = {}
    for base, bundled in ((downloads_dir(), False), (bundled_dir(), True)):
        if not os.path.isdir(base):
            continue
        for locale in sorted(os.listdir(base)):
            locale_dir = os.path.join(base, locale)
            if not os.path.isdir(locale_dir):
                continue
            for fname in sorted(os.listdir(locale_dir)):
                if not fname.lower().endswith(".json"):
                    continue
                stem = fname[:-5]
                # Recover the repo name (sanitized chars can't be restored,
                # so match against the catalog by sanitized form)
                name = _unsanitize(locale, stem)
                tid = f"{locale}/{name}"
                if tid not in found:
                    found[tid] = {
                        "id": tid,
                        "locale": locale,
                        "language": LOCALE_NAMES.get(locale, locale),
                        "name": name,
                        "abbr": catalog().get(locale, {}).get(name, ""),
                        "bundled": bundled,
                    }
                elif bundled:
                    found[tid]["bundled"] = True
    return sorted(found.values(), key=lambda t: (t["language"], t["name"]))


def _unsanitize(locale: str, stem: str) -> str:
    """Map a sanitized filename stem back to its catalog translation name."""
    for name in catalog().get(locale, {}):
        if sanitize_filename(name) == stem:
            return name
    return stem


def download_translation(locale: str, name: str) -> str:
    """Fetch one translation from the repo into the downloads dir.

    Returns the translation id. Raises on network/format errors.
    """
    if name not in catalog().get(locale, {}):
        raise ValueError(f"Unknown translation: {locale}/{name}")
    url = "{}/versions/{}/{}.json".format(
        RAW_BASE, urllib.parse.quote(locale), urllib.parse.quote(name)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "selah"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError("Downloaded file is not a valid translation")

    target_dir = os.path.join(downloads_dir(), locale)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, sanitize_filename(name) + ".json")
    with open(target, "wb") as f:
        f.write(raw)
    logger.info("Downloaded Bible translation %s/%s (%d bytes)",
                locale, name, len(raw))
    return f"{locale}/{name}"


def delete_translation(tid: str) -> bool:
    """Remove a downloaded translation file (bundled ones are kept)."""
    path = os.path.join(
        downloads_dir(),
        split_translation_id(tid)[0],
        sanitize_filename(split_translation_id(tid)[1]) + ".json",
    )
    if os.path.exists(path):
        os.remove(path)
        with _cache_lock:
            _translation_cache.pop(tid, None)
        logger.info("Removed Bible translation %s", tid)
        return True
    return False


# ---------------------------------------------------------------------------
# Loaded translations (in-memory, LRU-cached)
# ---------------------------------------------------------------------------

class Translation:
    """A parsed translation with canonical-name indexing."""

    def __init__(self, tid: str, data: dict):
        self.id = tid
        locale, name = split_translation_id(tid)
        self.locale = locale
        self.name = name
        self.abbr = abbreviation(tid)

        mapping = _book_mapping(name)  # canonical -> localized
        reverse = {v: k for k, v in mapping.items()}

        self.books = OrderedDict()          # canonical -> {ch: {v: text}}
        self.display_names = {}             # canonical -> localized
        self.book_order = []                # canonical, file order
        for file_key, chapters in data.items():
            canonical = reverse.get(file_key, file_key)
            self.books[canonical] = chapters
            self.display_names[canonical] = file_key
            self.book_order.append(canonical)

        # casefolded name -> canonical, for both localized and canonical names
        self._lookup = {}
        for canonical in self.book_order:
            self._lookup[canonical.casefold()] = canonical
            self._lookup[self.display_names[canonical].casefold()] = canonical

    def display(self, canonical: str) -> str:
        return self.display_names.get(canonical, canonical)

    def match_book(self, raw: str) -> Tuple[Optional[str], List[str]]:
        """Resolve user input to a canonical book name.

        Returns (canonical, candidates): exact/casefold match wins; otherwise
        a unique prefix match. On ambiguity canonical is None and candidates
        holds the possible display names.
        """
        key = (raw or "").strip().rstrip(".").casefold()
        if not key:
            return None, []
        if key in self._lookup:
            return self._lookup[key], []
        hits = OrderedDict()
        for name_cf, canonical in self._lookup.items():
            if name_cf.startswith(key):
                hits[canonical] = None
        if len(hits) == 1:
            return next(iter(hits)), []
        return None, [self.display(c) for c in hits]

    def chapter_count(self, canonical: str) -> int:
        chapters = self.books.get(canonical, {})
        return max((int(c) for c in chapters if c.isdigit()), default=0)

    def verse_count(self, canonical: str, chapter: int) -> int:
        verses = self.books.get(canonical, {}).get(str(chapter), {})
        return max((int(v) for v in verses if v.isdigit()), default=0)

    def verse_text(self, canonical: str, chapter: int, verse: int) -> Optional[str]:
        return self.books.get(canonical, {}).get(str(chapter), {}).get(str(verse))

    def structure(self) -> dict:
        """Compact book/chapter/verse-count map for client-side pickers."""
        books = []
        for canonical in self.book_order:
            n = self.chapter_count(canonical)
            books.append({
                "book": canonical,
                "display": self.display(canonical),
                "chapters": [self.verse_count(canonical, c)
                             for c in range(1, n + 1)],
            })
        return {"books": books}


_translation_cache: "OrderedDict[str, Translation]" = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 3


def load_translation(tid: str) -> Translation:
    """Load (or fetch from cache) a parsed translation.

    Raises FileNotFoundError when the translation is not installed.
    """
    with _cache_lock:
        if tid in _translation_cache:
            _translation_cache.move_to_end(tid)
            return _translation_cache[tid]

    path = translation_path(tid)
    if not path:
        raise FileNotFoundError(f"Translation not installed: {tid}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    translation = Translation(tid, data)

    with _cache_lock:
        _translation_cache[tid] = translation
        _translation_cache.move_to_end(tid)
        while len(_translation_cache) > _CACHE_MAX:
            _translation_cache.popitem(last=False)
    return translation


# ---------------------------------------------------------------------------
# Verse references
# ---------------------------------------------------------------------------

class VerseRef:
    """One contiguous run of verses in a single chapter."""

    __slots__ = ("book", "chapter", "start", "end")

    def __init__(self, book: str, chapter: int, start: int, end: int):
        self.book = book        # canonical name
        self.chapter = chapter
        self.start = start
        self.end = end

    def to_dict(self) -> dict:
        return {"book": self.book, "chapter": self.chapter,
                "start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, d: dict) -> "VerseRef":
        return cls(d["book"], int(d["chapter"]),
                   int(d["start"]), int(d["end"]))


# "Book 3", "Book 3:16", "Book 3:16-18", "Book 3:16,18-20"
_SEGMENT_RE = re.compile(r"^(.+?)\s+(\d+)\s*(?::\s*([\d\s,\-–—]+))?$")
_RANGE_RE = re.compile(r"^(\d+)\s*(?:[-–—]\s*(\d+))?$")


class RefParseError(ValueError):
    pass


def parse_refs(text: str, translation: Translation) -> List[VerseRef]:
    """Parse user reference text ("John 3:16-18; Пс 22") into VerseRefs.

    Raises RefParseError with a user-facing message on invalid input.
    """
    refs: List[VerseRef] = []
    segments = [s.strip() for s in (text or "").split(";")]
    segments = [s for s in segments if s]
    if not segments:
        raise RefParseError("Enter at least one reference, e.g. John 3:16-18")

    for seg in segments:
        m = _SEGMENT_RE.match(seg)
        if not m:
            raise RefParseError(
                f'"{seg}" — expected a reference like John 3:16-18'
            )
        book_raw, chapter_s, verse_spec = m.group(1), m.group(2), m.group(3)
        canonical, candidates = translation.match_book(book_raw)
        if not canonical:
            if candidates:
                raise RefParseError(
                    '"{}" is ambiguous: {}'.format(
                        book_raw.strip(), ", ".join(sorted(candidates)[:6])
                    )
                )
            raise RefParseError(f'Unknown book: "{book_raw.strip()}"')

        chapter = int(chapter_s)
        max_ch = translation.chapter_count(canonical)
        if not 1 <= chapter <= max_ch:
            raise RefParseError(
                "{} has {} chapters (asked for {})".format(
                    translation.display(canonical), max_ch, chapter
                )
            )
        max_v = translation.verse_count(canonical, chapter)

        if verse_spec is None:
            refs.append(VerseRef(canonical, chapter, 1, max_v))
            continue

        for part in verse_spec.split(","):
            part = part.strip()
            rm = _RANGE_RE.match(part)
            if not rm:
                raise RefParseError(
                    f'"{seg}" — bad verse range "{part}"'
                )
            start = int(rm.group(1))
            end = int(rm.group(2)) if rm.group(2) else start
            if start > end:
                start, end = end, start
            if not (1 <= start <= max_v and 1 <= end <= max_v):
                raise RefParseError(
                    "{} {} has {} verses (asked for {}-{})".format(
                        translation.display(canonical), chapter, max_v,
                        start, end,
                    )
                )
            refs.append(VerseRef(canonical, chapter, start, end))
    return refs


def parse_entry_groups(text: str, translation: Translation) -> List[List[VerseRef]]:
    """Parse reference text into entry groups.

    "!" separates entries (each becomes its own feed row / slide);
    ";" combines references inside one entry. So
    "John 3:16; Romans 5:8" is one combined entry, while
    "John 3:16! Romans 5:8" is two entries.
    """
    groups = [g.strip() for g in (text or "").split("!")]
    groups = [g for g in groups if g]
    if not groups:
        raise RefParseError("Enter at least one reference, e.g. John 3:16-18")
    return [parse_refs(g, translation) for g in groups]


def refs_from_json(refs_json: str) -> List[VerseRef]:
    try:
        return [VerseRef.from_dict(d) for d in json.loads(refs_json or "[]")]
    except (ValueError, KeyError, TypeError):
        return []


def refs_to_json(refs: List[VerseRef]) -> str:
    return json.dumps([r.to_dict() for r in refs])


def format_ref(ref: VerseRef, translation: Optional[Translation]) -> str:
    """Display form of one ref, localized when a translation is given."""
    book = translation.display(ref.book) if translation else ref.book
    whole_chapter = (
        translation is not None
        and ref.start == 1
        and ref.end >= translation.verse_count(ref.book, ref.chapter)
    )
    if whole_chapter:
        return f"{book} {ref.chapter}"
    if ref.start == ref.end:
        return f"{book} {ref.chapter}:{ref.start}"
    return f"{book} {ref.chapter}:{ref.start}-{ref.end}"


def format_refs(refs: List[VerseRef], translation: Optional[Translation]) -> str:
    return "; ".join(format_ref(r, translation) for r in refs)


def resolve_refs_blocks(refs: List[VerseRef], translation: Translation) -> List[dict]:
    """Resolve an entry into one block per reference.

    Each block: {label, book (display name), chapter, verses: [(num, text)]}.
    Blocks whose verses are all missing from the translation are dropped.
    """
    blocks = []
    for ref in refs:
        verses: List[Tuple[int, str]] = []
        for v in range(ref.start, ref.end + 1):
            text = translation.verse_text(ref.book, ref.chapter, v)
            if text:
                verses.append((v, text.strip()))
        if verses:
            blocks.append({
                "label": format_ref(ref, translation),
                "book": translation.display(ref.book),
                "chapter": ref.chapter,
                "verses": verses,
            })
    return blocks


def block_text(verses: List[Tuple[int, str]]) -> str:
    """Running text of one block; verse numbers inline when it spans several."""
    if len(verses) == 1:
        return verses[0][1]
    return " ".join(f"{num} {text}" for num, text in verses)


def resolve_refs_text(refs: List[VerseRef], translation: Translation) -> str:
    """Combined verse text for one entry.

    A single reference renders as running text. When the entry combines
    verses from several places, each part starts on a new line under its
    own reference, so consumers can see where each passage begins.
    """
    blocks = resolve_refs_blocks(refs, translation)
    if not blocks:
        return ""
    if len(blocks) == 1:
        return block_text(blocks[0]["verses"])
    return "\n".join(
        "{}\n{}".format(b["label"], block_text(b["verses"])) for b in blocks
    )
