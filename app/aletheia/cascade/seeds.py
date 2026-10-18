"""Seed autodetection, canonicalization, and dedup (Phase 17, P17.2).

Design of record: ``docs/PIVOT_CASCADE.md`` sections 3 and 4.1 (the universal
seed horizon). This module turns raw pasted text — the OCR branch feeds text
too — into typed ``Seed`` values.

Honesty rules this detector follows:

- It detects only classes a validator can actually recognize: emails, URLs,
  IPv4 addresses, crypto addresses (BTC legacy/bech32, ETH), conservative
  phone patterns, VINs, standalone domains, and ``@handles``.
- It does **not** guess person names, company names, places, or other
  free-text concepts. Regex cannot recognize arbitrary names honestly, so
  those seeds are typed by the operator (or recognized only when they appear
  as one of the structured classes above inside OCR text).
- Results are canonicalized, deduplicated, and returned in first-appearance
  order — the deterministic ordering the scheduler relies on. A seed never
  runs twice in a run: multi-seed runs consume this list directly
  (``Orchestrator.create_run``).

Matching is conservative on purpose: masked spans prevent double-reporting a
URL's host as a domain or an email's domain as a bare domain, and bounded
patterns (digit counts, base58 alphabets, a file-extension blocklist) keep
obvious prose false positives out.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from aletheia.core.models import Seed, SeedType

__all__ = ["canonicalize_seed", "dedupe_seeds", "detect_seeds"]

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}"
)
_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")
_ETH_RE = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
_BTC_RE = re.compile(r"\b(?:bc1[02-9ac-hj-np-z]{25,62}|[13][1-9A-HJ-NP-Za-km-z]{25,34})\b")
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?!\d)(?!\.\d)")
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_PHONE_INTL_RE = re.compile(r"(?<![\d+])\+\d[\d\s().\-]{6,17}\d")
_PHONE_NATIONAL_RE = re.compile(r"(?<!\d)(?:\(\d{3}\)\s*|\d{3}[\s.\-])\d{3}[\s.\-]?\d{4}(?!\d)")
_DOMAIN_RE = re.compile(
    r"(?<![@\w.\-])(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?![\w\-])"
)
_HANDLE_RE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_]{2,30})\b")

# Common file extensions: "report.pdf" is a file name in prose, not a domain.
_FILE_EXTENSIONS = frozenset(
    {
        "pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods",
        "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico", "tiff", "heic",
        "csv", "tsv", "json", "jsonl", "xml", "yaml", "yml", "toml", "ini", "cfg",
        "conf", "log", "md", "rst", "py", "pyc", "js", "mjs", "ts", "tsx", "jsx",
        "html", "htm", "css", "scss", "sh", "bat", "ps1", "zip", "tar", "gz", "tgz",
        "bz2", "xz", "7z", "rar", "exe", "dll", "so", "dylib", "mp3", "wav", "ogg",
        "flac", "mp4", "mov", "avi", "mkv", "webm", "sqlite", "db", "bak", "tmp",
        "lock", "env",
    }
)

# Text-like seed values deduplicate case-insensitively (collapsed whitespace);
# every other type is already canonicalized exactly.
_CASEFOLD_DEDUP_TYPES = frozenset(
    {
        SeedType.NAME,
        SeedType.PERSON_NAME,
        SeedType.COMPANY_NAME,
        SeedType.BANK_NAME,
        SeedType.LOBBYIST_NAME,
        SeedType.INTELLECTUAL_PROPERTY,
        SeedType.GEOLOCATION,
    }
)


def canonicalize_seed(seed: Seed) -> Seed:
    """Return the canonical form of ``seed`` for dedup and scheduling.

    - username: leading ``@`` stripped, lowercased;
    - email: lowercased;
    - domain: lowercased, trailing dot stripped, IDN -> punycode;
    - URL: scheme and host lowercased, fragment dropped (path/query preserved);
    - IP: validated and re-serialized via :mod:`ipaddress`;
    - phone: separators stripped, ``00`` international prefix -> ``+``;
    - VIN: uppercased;
    - crypto: ETH addresses lowercased (BTC base58 is case-significant);
    - text-like values: whitespace collapsed.
    """
    seed_type = seed.type
    value = seed.value.strip()
    if seed_type is SeedType.EMAIL:
        value = value.lower()
    elif seed_type is SeedType.USERNAME:
        value = value.lstrip("@").lower()
    elif seed_type is SeedType.DOMAIN:
        value = value.lower().rstrip(".")
        try:
            value = value.encode("idna").decode("ascii")
        except UnicodeError:
            pass
    elif seed_type is SeedType.URL:
        value = _canonical_url(value)
    elif seed_type is SeedType.IP:
        try:
            value = str(ipaddress.ip_address(value))
        except ValueError:
            pass
    elif seed_type is SeedType.PHONE:
        value = re.sub(r"[^\d+]", "", value)
        if value.startswith("00"):
            value = "+" + value[2:]
    elif seed_type is SeedType.VIN:
        value = value.upper()
    elif seed_type is SeedType.CRYPTO_ADDRESS:
        if value.lower().startswith("0x"):
            value = "0x" + value[2:].lower()
    else:
        value = " ".join(value.split())
    return Seed(type=seed_type, value=value)


def _canonical_url(value: str) -> str:
    parts = urlsplit(value)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostport = netloc.rsplit("@", 1)
        netloc = f"{userinfo}@{hostport.lower()}"
    else:
        netloc = netloc.lower()
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def _dedup_key(seed: Seed) -> tuple[SeedType, str]:
    if seed.type in _CASEFOLD_DEDUP_TYPES:
        return seed.type, " ".join(seed.value.casefold().split())
    return seed.type, seed.value


def dedupe_seeds(seeds: Iterable[Seed]) -> list[Seed]:
    """Canonicalize, then drop duplicates (same type + canonical value).

    First appearance wins, so the caller's ordering is preserved exactly.
    """
    seen: set[tuple[SeedType, str]] = set()
    result: list[Seed] = []
    for seed in seeds:
        canonical = canonicalize_seed(seed)
        key = _dedup_key(canonical)
        if key in seen:
            continue
        seen.add(key)
        result.append(canonical)
    return result


def _clean_url(value: str) -> str:
    return value.rstrip(".,;:!?")


def _vin_is_plausible(value: str) -> bool:
    return any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value)


def detect_seeds(text: str) -> list[Seed]:
    """Extract typed, canonicalized, deduplicated seeds from raw text.

    Detection classes, in masking priority order: URLs, emails, crypto
    addresses, IPv4 addresses, VINs, phone numbers, standalone domains, and
    ``@handles``. A candidate whose span overlaps an already-accepted match is
    skipped, so an email never also yields its domain seed and a URL never
    yields its host as a bare domain. The returned list is in first-appearance
    order.
    """
    if not isinstance(text, str):
        raise TypeError("detect_seeds expects the raw text as a string")

    found: list[tuple[int, Seed]] = []
    spans: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < span_end and end > span_start for span_start, span_end in spans)

    def record(match: re.Match[str], seed_type: SeedType, value: str | None = None) -> None:
        start, end = match.span()
        if overlaps(start, end):
            return
        raw = value if value is not None else match.group(0)
        if not raw:
            return
        spans.append((start, end))
        found.append((start, Seed(type=seed_type, value=raw)))

    # 1. URLs first: their userinfo form can contain "@", and their hosts must
    #    not leak into the email or domain scans.
    for match in _URL_RE.finditer(text):
        cleaned = _clean_url(match.group(0))
        if urlsplit(cleaned).netloc:
            record(match, SeedType.URL, value=cleaned)

    # 2. Emails (their domain must not leak into the standalone domain scan).
    for match in _EMAIL_RE.finditer(text):
        record(match, SeedType.EMAIL)

    # 3. Crypto addresses.
    for match in _ETH_RE.finditer(text):
        record(match, SeedType.CRYPTO_ADDRESS)
    for match in _BTC_RE.finditer(text):
        record(match, SeedType.CRYPTO_ADDRESS)

    # 4. IPv4 addresses (octets validated by ipaddress, not by the regex).
    for match in _IPV4_RE.finditer(text):
        try:
            ipaddress.ip_address(match.group(0))
        except ValueError:
            continue
        record(match, SeedType.IP)

    # 5. VINs: 17 uppercase alphanumerics without I/O/Q, mixed digits/letters.
    for match in _VIN_RE.finditer(text):
        if _vin_is_plausible(match.group(0)):
            record(match, SeedType.VIN)

    # 6. Phones: the stricter international pattern first, then US-style
    #    national numbers with separators; bare digit runs are never phones.
    for match in _PHONE_INTL_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 8 <= len(digits) <= 15:
            record(match, SeedType.PHONE)
    for match in _PHONE_NATIONAL_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) in {10, 11}:
            record(match, SeedType.PHONE)

    # 7. Standalone domains (emails and URLs have already masked their hosts).
    for match in _DOMAIN_RE.finditer(text):
        value = match.group(0)
        if value.rsplit(".", 1)[-1].casefold() in _FILE_EXTENSIONS:
            continue
        record(match, SeedType.DOMAIN)

    # 8. @handles.
    for match in _HANDLE_RE.finditer(text):
        record(match, SeedType.USERNAME, value="@" + match.group(1))

    found.sort(key=lambda item: item[0])
    return dedupe_seeds(seed for _, seed in found)
