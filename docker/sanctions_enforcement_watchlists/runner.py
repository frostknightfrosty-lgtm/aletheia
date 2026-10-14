from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Iterator

# Every sub-source in this composite publishes a bulk file (XML), not a JSON
# search API. There is therefore deliberately no _fetch_json helper here: the
# runner downloads the published artefact once per run and filters it locally.
# No endpoint below was guessed; each one is linked from the official
# publication page recorded in RATE_LIMITS.md and was fetched successfully
# (HTTP 200, XML) while this adapter was written.

# UK Sanctions List (FCDO). Listed as "XML format UK Sanctions List" on the
# GOV.UK publication page. The OFSI Consolidated List closed on 28 January 2026
# and the UK Sanctions List is now the only source for UK designations.
UK_SANCTIONS_LIST_PAGE = "https://www.gov.uk/government/publications/the-uk-sanctions-list"
UK_SANCTIONS_LIST_URL = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml"

# Swiss SECO sanctions: the "XML consolidated list (current version)" linked
# from the SECO "Searching for subjects of sanctions and overall list" page.
SECO_SANCTIONS_LIST_PAGE = "https://www.seco.admin.ch/en/searching-for-subjects-sanctions"
SECO_SANCTIONS_LIST_URL = (
    "https://www.sesam.search.admin.ch/sesam-search-web/pages/"
    "downloadXmlGesamtliste.xhtml?lang=de&action=downloadXmlGesamtlisteAction"
)

# EU consolidated financial sanctions list: the Financial Sanctions Files (FSF)
# XML export. The fixed public token below is the one published in the European
# Commission's own dataset record on the EU open data portal; the same record
# also documents the CSV, PDF and XSD distributions.
EU_SANCTIONS_LIST_PAGE = (
    "https://data.europa.eu/api/hub/search/datasets/"
    "consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions-fisma"
)
EU_SANCTIONS_LIST_URL = (
    "https://webgate.ec.europa.eu/fsd/fsf/public/files/"
    "xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
)

# Sub-sources with no documented machine-readable public artefact are reported
# as skipped with a plain factual reason and no URL. All three sub-sources this
# adapter covers were verified against their own official publication pages, so
# this map is currently empty; it stays in place so any future unsupported
# sub-source is reported as an auditable skip rather than a fabricated call.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {}

# Official lists are tens of megabytes (the SECO whole list is about 42 MB). Cap
# the download so a misbehaving endpoint cannot exhaust the container memory.
MAX_LIST_BYTES = 64 * 1024 * 1024

# One run answers a single seed. Store at most this many matches per sub-source
# and report the untruncated count in "match_count".
MAX_MATCHES = 25

SUPPORTED_SUB_SOURCES = ("uk-sanctions-list", "swiss-seco", "eu-consolidated-sanctions")

EU_NAMESPACE = "http://eu.europa.ec/fpi/fsd/export"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_bytes(url: str, timeout: int = 120, max_bytes: int = MAX_LIST_BYTES) -> tuple[bytes | None, int, str | None]:
    """Fetch a published bulk artefact. Returns (body, http_status, error)."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Aletheia/0.7.0 (sanctions-watchlists)",
            "Accept": "application/xml,text/xml,text/csv,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return None, response.status, (
                    "Response exceeded the " + str(max_bytes // (1024 * 1024)) + " MB safety limit"
                )
            return body, response.status, None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, "HTTP " + str(exc.code) + ": " + detail[:500]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__ + ": " + str(exc)


class SourceResult:
    def __init__(
        self,
        name: str,
        data: dict | list | None = None,
        http_status: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ):
        self.name = name
        self.data = data
        self.http_status = http_status
        self.error = error
        self.skipped = skipped
        self.skip_reason = skip_reason
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.raw_hash = _sha256(json.dumps(data, sort_keys=True).encode()) if data else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.name,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "timestamp": self.timestamp,
            "http_status": self.http_status,
            "error": self.error,
            "raw_hash": self.raw_hash,
            "data": self.data,
        }


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _name_matches(query: str, candidate: str) -> bool:
    """Plain normalized substring test in either direction.

    This is deliberately not a fuzzy or phonetic match: a hit means the query
    text appears in a listed name (or the listed name appears in the query) and
    must still be reviewed by a human before it is treated as the same person or
    organisation.
    """
    normalized_query = _normalize(query)
    normalized_candidate = _normalize(candidate)
    if len(normalized_query) < 3 or len(normalized_candidate) < 3:
        return False
    return normalized_query in normalized_candidate or normalized_candidate in normalized_query


def _iter_top_level(body: bytes, tags: frozenset[str], root_holder: dict[str, ET.Element] | None = None) -> Iterator[ET.Element]:
    """Yield top-level elements whose tag is in the tag set, clearing each after use.

    ElementTree.iterparse keeps the parsed document alive unless elements are
    released, so each yielded element is cleared once the caller is done with
    it. Only direct children of the document root are yielded, which keeps
    historical nested records (for example a target inside a modification) out
    of the current-state view. The document root is never cleared; when a holder
    is supplied it receives the root element so the caller can read the
    list-level attributes and elements (list type, generation date, and so on).
    """
    depth = 0
    for event, element in ET.iterparse(io.BytesIO(body), events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 1 and root_holder is not None:
                root_holder["element"] = element
            continue
        depth -= 1
        if depth == 1 and element.tag in tags:
            yield element
            element.clear()


def _root_element(holder: dict[str, ET.Element]) -> ET.Element | None:
    return holder.get("element")


def _xml_error(name: str, status: int, exc: Exception) -> SourceResult:
    return SourceResult(name, http_status=status, error="XML parse error: " + str(exc))


# -- UK Sanctions List ---------------------------------------------------------


def _uk_name_block(name_element: ET.Element) -> str:
    """Join the ordered Name1..Name6 parts of one Name block into a full name.

    The published list normally carries the whole name in a single part; joining
    the populated parts keeps a name that is split across parts matchable as one
    name instead of turning each fragment into a separate candidate.
    """
    parts: list[tuple[int, str]] = []
    for child in name_element:
        suffix = child.tag[4:] if child.tag.startswith("Name") else ""
        if not suffix.isdigit():
            continue
        value = (child.text or "").strip()
        if value:
            parts.append((int(suffix), value))
    return " ".join(value for _order, value in sorted(parts)).strip()


def _uk_names(designation: ET.Element) -> list[str]:
    """Collect the full name of every Name block of a designation."""
    names: list[str] = []
    for name_element in designation.findall("Names/Name"):
        name = _uk_name_block(name_element)
        if name and name not in names:
            names.append(name)
    return names


def _uk_primary_name(designation: ET.Element) -> str:
    for name_element in designation.findall("Names/Name"):
        name_type = (name_element.findtext("NameType") or "").strip().casefold()
        if name_type != "primary name":
            continue
        name = _uk_name_block(name_element)
        if name:
            return name
    names = _uk_names(designation)
    return names[0] if names else ""


def query_uk_sanctions_list(query: str) -> SourceResult:
    body, status, error = _fetch_bytes(UK_SANCTIONS_LIST_URL)
    if error:
        return SourceResult("uk-sanctions-list", http_status=status, error=error)

    holder: dict[str, ET.Element] = {}
    matches: list[dict[str, Any]] = []
    total = 0
    try:
        for designation in _iter_top_level(body, frozenset({"Designation"}), holder):
            names = _uk_names(designation)
            matched = [name for name in names if _name_matches(query, name)]
            if not matched:
                continue
            total += 1
            if len(matches) >= MAX_MATCHES:
                continue
            matches.append(
                {
                    "unique_id": (designation.findtext("UniqueID") or "").strip(),
                    "ofsi_group_id": (designation.findtext("OFSIGroupID") or "").strip(),
                    "un_reference_number": (designation.findtext("UNReferenceNumber") or "").strip(),
                    "primary_name": _uk_primary_name(designation),
                    "subject_kind": (designation.findtext("IndividualEntityShip") or "").strip(),
                    "regime_name": (designation.findtext("RegimeName") or "").strip(),
                    "designation_source": (designation.findtext("DesignationSource") or "").strip(),
                    "sanctions_imposed": (designation.findtext("SanctionsImposed") or "").strip(),
                    "date_designated": (designation.findtext("DateDesignated") or "").strip(),
                    "last_updated": (designation.findtext("LastUpdated") or "").strip(),
                    "matched_names": matched,
                    "name_count": len(names),
                }
            )
    except ET.ParseError as exc:
        return _xml_error("uk-sanctions-list", status, exc)

    if not matches:
        return SourceResult("uk-sanctions-list", http_status=status)

    root_element = _root_element(holder)
    data = {
        "list_source": "UK Sanctions List (FCDO)",
        "list_publication_page": UK_SANCTIONS_LIST_PAGE,
        "list_url": UK_SANCTIONS_LIST_URL,
        "date_generated": (
            (root_element.findtext("DateGenerated") or "").strip() if root_element is not None else ""
        ),
        "query": query,
        "match_count": total,
        "truncated": total > len(matches),
        "matches": matches,
    }
    return SourceResult("uk-sanctions-list", data=data, http_status=status)


# -- Swiss SECO sanctions list -------------------------------------------------


def _seco_subject(target: ET.Element) -> tuple[str, str]:
    for tag in ("individual", "entity", "object"):
        element = target.find(tag)
        if element is not None:
            return tag, element.get("object-type", "")
    return "", ""


def _seco_names(target: ET.Element) -> list[tuple[str, str]]:
    """Return (name-type, value) pairs for every name element of a target."""
    names: list[tuple[str, str]] = []
    for name_element in target.iter("name"):
        parts = [(part.text or "").strip() for part in name_element.findall("name-part/value")]
        value = " ".join(part for part in parts if part).strip()
        if value:
            names.append((name_element.get("name-type", ""), value))
    return names


def _seco_de_listed(target: ET.Element) -> bool:
    """A target is historical once its final modification is a de-listing.

    The SECO schema documents that the final modification describes the
    de-listed event, so the last modification decides the current state.
    """
    modifications = target.findall("modification")
    if not modifications:
        return False
    return modifications[-1].get("modification-type", "") == "de-listed"


def query_swiss_seco(query: str) -> SourceResult:
    body, status, error = _fetch_bytes(SECO_SANCTIONS_LIST_URL)
    if error:
        return SourceResult("swiss-seco", http_status=status, error=error)

    holder: dict[str, ET.Element] = {}
    # A target references a sanctions set, and the set belongs to a sanctions
    # program, so the set ssid is what resolves a target to its programme.
    sets: dict[str, dict[str, str]] = {}
    matches: list[dict[str, Any]] = []
    total = 0
    try:
        for element in _iter_top_level(body, frozenset({"sanctions-program", "target"}), holder):
            if element.tag == "sanctions-program":
                program_key = ""
                for key_element in element.findall("program-key"):
                    if key_element.get("lang") == "eng":
                        program_key = (key_element.text or "").strip()
                        break
                program = {
                    "program_key": program_key,
                    "origin": (element.findtext("origin") or "").strip(),
                    "version_date": element.get("version-date", ""),
                }
                for set_element in element.findall("sanctions-set"):
                    sets[set_element.get("ssid", "")] = program
                continue

            if _seco_de_listed(element):
                continue
            names = _seco_names(element)
            matched = [value for _name_type, value in names if _name_matches(query, value)]
            if not matched:
                continue
            total += 1
            if len(matches) >= MAX_MATCHES:
                continue
            primary = next(
                (value for name_type, value in names if name_type == "primary-name"),
                matched[0],
            )
            subject_type, object_type = _seco_subject(element)
            set_ids = [(child.text or "").strip() for child in element.findall("sanctions-set-id")]
            program = sets.get(set_ids[0], {}) if set_ids else {}
            matches.append(
                {
                    "ssid": element.get("ssid", ""),
                    "subject_type": subject_type,
                    "object_type": object_type,
                    "primary_name": primary,
                    "matched_names": matched,
                    "name_types": sorted({name_type for name_type, _value in names if _value in matched}),
                    "sanctions_set_ids": set_ids,
                    "program_key": program.get("program_key", ""),
                    "program_origin": program.get("origin", ""),
                    "program_version_date": program.get("version_date", ""),
                }
            )
    except ET.ParseError as exc:
        return _xml_error("swiss-seco", status, exc)

    if not matches:
        return SourceResult("swiss-seco", http_status=status)

    root_element = _root_element(holder)
    data = {
        "list_source": "Swiss sanctions list (SECO / SESAM)",
        "list_publication_page": SECO_SANCTIONS_LIST_PAGE,
        "list_url": SECO_SANCTIONS_LIST_URL,
        "list_type": root_element.get("list-type", "") if root_element is not None else "",
        "list_date": root_element.get("date", "") if root_element is not None else "",
        "query": query,
        "match_count": total,
        "truncated": total > len(matches),
        "matches": matches,
    }
    return SourceResult("swiss-seco", data=data, http_status=status)


# -- EU consolidated financial sanctions list ----------------------------------


def query_eu_consolidated_sanctions(query: str) -> SourceResult:
    body, status, error = _fetch_bytes(EU_SANCTIONS_LIST_URL)
    if error:
        return SourceResult("eu-consolidated-sanctions", http_status=status, error=error)

    holder: dict[str, ET.Element] = {}
    matches: list[dict[str, Any]] = []
    total = 0
    prefix = "{" + EU_NAMESPACE + "}"
    try:
        for entity in _iter_top_level(body, frozenset({prefix + "sanctionEntity"}), holder):
            names = [
                (alias.get("wholeName") or "").strip()
                for alias in entity.findall(prefix + "nameAlias")
            ]
            names = [name for name in names if name]
            matched = [name for name in names if _name_matches(query, name)]
            if not matched:
                continue
            total += 1
            if len(matches) >= MAX_MATCHES:
                continue
            subject_type = entity.find(prefix + "subjectType")
            regulation = entity.find(prefix + "regulation")
            matches.append(
                {
                    "logical_id": entity.get("logicalId", ""),
                    "eu_reference_number": entity.get("euReferenceNumber", ""),
                    "united_nation_id": entity.get("unitedNationId", ""),
                    "subject_type": subject_type.get("code", "") if subject_type is not None else "",
                    "designation_details": entity.get("designationDetails", ""),
                    "remark": (entity.findtext(prefix + "remark") or "").strip(),
                    "programme": regulation.get("programme", "") if regulation is not None else "",
                    "regulation_number_title": regulation.get("numberTitle", "") if regulation is not None else "",
                    "regulation_publication_date": (
                        regulation.get("publicationDate", "") if regulation is not None else ""
                    ),
                    "primary_name": matched[0],
                    "matched_names": matched,
                    "name_count": len(names),
                }
            )
    except ET.ParseError as exc:
        return _xml_error("eu-consolidated-sanctions", status, exc)

    if not matches:
        return SourceResult("eu-consolidated-sanctions", http_status=status)

    root_element = _root_element(holder)
    data = {
        "list_source": "EU consolidated financial sanctions list (Financial Sanctions Files)",
        "list_publication_page": EU_SANCTIONS_LIST_PAGE,
        "list_url": EU_SANCTIONS_LIST_URL,
        "generation_date": root_element.get("generationDate", "") if root_element is not None else "",
        "global_file_id": root_element.get("globalFileId", "") if root_element is not None else "",
        "query": query,
        "match_count": total,
        "truncated": total > len(matches),
        "matches": matches,
    }
    return SourceResult("eu-consolidated-sanctions", data=data, http_status=status)


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print("ok")
        return 0

    if len(sys.argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        print("input_type: name, company_name, person_name", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    valid_types = {"name", "company_name", "person_name"}
    if input_type not in valid_types:
        print("Invalid input_type: " + input_type + ". Must be one of: " + str(sorted(valid_types)), file=sys.stderr)
        return 2

    # Every sub-source is reported once per run. A sub-source that publishes no
    # machine-readable artefact would be reported here as a documented skip.
    results = [
        query_uk_sanctions_list(value),
        query_swiss_seco(value),
        query_eu_consolidated_sanctions(value),
    ]

    output = {
        "input_type": input_type,
        "input_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [result.to_dict() for result in results],
    }

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
