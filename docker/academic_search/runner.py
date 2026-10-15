"""Academic search batch runner.

One query per sub-source per run. Every endpoint, query parameter and response
shape below was read from the provider's own official documentation; the
verbatim parameter name, auth method, documented rate limit, response format and
documentation URL of each sub-source are recorded in RATE_LIMITS.md next to this
file. No endpoint was guessed and no parameter was inferred from a response
example.

Standard library only (urllib, json, xml.etree.ElementTree, hashlib, os, sys):
the container has no third-party packages.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources, each with a documented search parameter:
#   openalex         /works?search=            (docs: /api/searching/)
#   crossref         /works?query.bibliographic=
#   semantic-scholar /graph/v1/paper/search?query=
#   arxiv            /api/query?search_query=
#   core             /v3/search/works/?q=
#   openaire         /graph/v3/research-products?search=
SUPPORTED_SUB_SOURCES = (
    "openalex",
    "crossref",
    "semantic-scholar",
    "arxiv",
    "core",
    "openaire",
)

# Dropped sub-source. Unpaywall documents no title/keyword/author search: the
# only live endpoint is a DOI lookup (GET /v2/:doi) and the documented title
# search (GET /v2/search?query=...) was retired on 18 September 2026 and now
# returns 410 Gone. It is therefore reported once per run as an auditable skip
# with this reason and no URL is ever built for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "unpaywall": (
        "Unpaywall documents no title, keyword or author search: its only live endpoint is a DOI lookup "
        "(GET /v2/:doi) and the documented title search (GET /v2/search?query=...) was retired on "
        "18 September 2026 and now returns 410 Gone, so no documented search contract exists for this adapter's "
        "name-based input types."
    ),
}

# Official documentation and the exact published endpoint of every implemented
# sub-source.
OPENALEX_DOCS = "https://help.openalex.org/api/searching/"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
CROSSREF_DOCS = "https://api.crossref.org/swagger-docs"
CROSSREF_ENDPOINT = "https://api.crossref.org/works"
SEMANTIC_SCHOLAR_DOCS = "https://api.semanticscholar.org/api-docs/graph"
SEMANTIC_SCHOLAR_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_DOCS = "https://info.arxiv.org/help/api/user-manual.html"
ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"
CORE_DOCS = "https://api.core.ac.uk/docs/v3"
CORE_ENDPOINT = "https://api.core.ac.uk/v3/search/works/"
OPENAIR_E_DOCS = "https://graph.openaire.eu/docs/apis/graph-api/"
OPENAIR_E_ENDPOINT = "https://api.openaire.eu/graph/v3/research-products"

# Fields requested from the Semantic Scholar paper search. Every name is a
# property of the published Paper/FullPaper schema in the official API
# reference; the reference's own example requests use the same "fields"
# parameter.
SEMANTIC_SCHOLAR_FIELDS = "paperId,title,year,venue,externalIds,url,authors,citationCount,publicationDate"

# One run answers a single seed. Store at most this many records per sub-source
# and report the untruncated count in "record_count".
MAX_RECORDS = 10

# Cap any single response so a misbehaving endpoint cannot exhaust memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

USER_AGENT = "Aletheia/0.7.0 (academic-search)"

ARXIV_NAMESPACE = "{http://www.w3.org/2005/Atom}"
ARXIV_EXTRA_NAMESPACE = "{http://arxiv.org/schemas/atom}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_bytes(
    url: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[bytes | None, int, str | None]:
    """Fetch a search endpoint. Returns (body, http_status, error)."""
    query = urllib.parse.urlencode(params or {})
    full_url = url + ("?" + query if query else "")
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,application/atom+xml,text/xml,*/*"}
    request_headers.update(headers or {})
    request = urllib.request.Request(full_url, headers=request_headers)
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


def _fetch_json(
    url: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict | list | None, int, str | None]:
    body, status, error = _fetch_bytes(url, params, headers)
    if error:
        return None, status, error
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


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


def _skip(name: str, reason: str) -> SourceResult:
    """A sub-source that is deliberately not queried this run, with its reason."""
    return SourceResult(name, skipped=True, skip_reason=reason)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _text(value: Any) -> str:
    """Collapse whitespace in publisher text fields (arXiv and Crossref wrap them)."""
    return " ".join(_clean(value).split())


def _records_payload(
    api_source: str,
    api_documentation: str,
    endpoint: str,
    query: str,
    records: list[dict[str, Any]],
    total: int,
) -> dict[str, Any]:
    return {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "endpoint": endpoint,
        "query": query,
        "record_count": total,
        "truncated": total > len(records),
        "records": records,
    }


# -- OpenAlex ------------------------------------------------------------------
#
# "The `search` parameter finds results matching a given text search."
# (https://help.openalex.org/api/searching/) Example from the same page:
# https://api.openalex.org/works?search=dna
#
# Auth: none for basic use; a free key may be sent as the api_key query
# parameter or as an Authorization bearer token. Documented limits: 10
# requests/second without a key, 30/second with a free key.


def query_openalex(query: str) -> SourceResult:
    params = {"search": query, "per_page": str(MAX_RECORDS)}
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if api_key:
        # Sent as the documented api_key query parameter; never echoed in output.
        params["api_key"] = api_key

    payload, status, error = _fetch_json(OPENALEX_ENDPOINT, params)
    if error:
        return SourceResult("openalex", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("openalex", http_status=status, error="Unexpected OpenAlex response shape")

    results = payload.get("results") or []
    meta = payload.get("meta") or {}
    records: list[dict[str, Any]] = []
    for work in results[:MAX_RECORDS]:
        if not isinstance(work, dict):
            continue
        authors = [
            _clean((authorship.get("author") or {}).get("display_name"))
            for authorship in (work.get("authorships") or [])
            if isinstance(authorship, dict)
        ]
        authors = [author for author in authors if author]
        source = (work.get("primary_location") or {}).get("source") or {}
        records.append(
            {
                "record_id": _clean(work.get("id")).rsplit("/", 1)[-1],
                "title": _clean(work.get("title")),
                "doi": _clean(work.get("doi")).replace("https://doi.org/", ""),
                "authors": authors,
                "year": work.get("publication_year"),
                "venue": _clean(source.get("display_name")),
                "url": _clean(work.get("id")),
                "type": _clean(work.get("type")),
                "cited_by_count": work.get("cited_by_count"),
                "publication_date": _clean(work.get("publication_date")),
                "is_oa": (work.get("open_access") or {}).get("is_oa"),
            }
        )

    if not records:
        return SourceResult("openalex", http_status=status)

    total = meta.get("count")
    total = total if isinstance(total, int) else len(records)
    data = _records_payload(
        "OpenAlex works",
        OPENALEX_DOCS,
        OPENALEX_ENDPOINT,
        query,
        records,
        total,
    )
    return SourceResult("openalex", data=data, http_status=status)


# -- Crossref ------------------------------------------------------------------
#
# Official reference: "Some queries look only in one or several fields. For
# example, `/works?query.bibliographic=Richard+Feynmann` only incorporates
# fields used when referencing the content item (title, authors, volume, journal
# name, etc.)." (https://api.crossref.org/swagger-docs)
#
# Auth: none. The reference documents `mailto` as "The email address to
# identify yourself and access the 'polite pool'"; it is optional for every
# request and is only sent when CROSSREF_MAILTO is set.


def query_crossref(query: str) -> SourceResult:
    params = {"query.bibliographic": query, "rows": str(MAX_RECORDS)}
    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto

    payload, status, error = _fetch_json(CROSSREF_ENDPOINT, params)
    if error:
        return SourceResult("crossref", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("crossref", http_status=status, error="Unexpected Crossref response shape")

    message = payload.get("message") or {}
    items = message.get("items") or []
    records: list[dict[str, Any]] = []
    for item in items[:MAX_RECORDS]:
        if not isinstance(item, dict):
            continue
        titles = item.get("title") or []
        container = item.get("container-title") or []
        authors = []
        for author in item.get("author") or []:
            if not isinstance(author, dict):
                continue
            name = " ".join(part for part in (_clean(author.get("given")), _clean(author.get("family"))) if part)
            if name:
                authors.append(name)
        issued = ((item.get("issued") or {}).get("date-parts") or [[]])[0]
        year = issued[0] if issued else None
        records.append(
            {
                "record_id": _clean(item.get("DOI")),
                "title": _text(titles[0]) if titles else "",
                "doi": _clean(item.get("DOI")),
                "authors": authors,
                "year": year,
                "venue": _text(container[0]) if container else "",
                "url": _clean(item.get("URL")),
                "type": _clean(item.get("type")),
                "publisher": _clean(item.get("publisher")),
                "issued": "-".join(str(part) for part in issued),
                "member": _clean(item.get("member")),
            }
        )

    if not records:
        return SourceResult("crossref", http_status=status)

    total = message.get("total-results")
    total = total if isinstance(total, int) else len(records)
    data = _records_payload(
        "Crossref REST API works",
        CROSSREF_DOCS,
        CROSSREF_ENDPOINT,
        query,
        records,
        total,
    )
    return SourceResult("crossref", data=data, http_status=status)


# -- Semantic Scholar ----------------------------------------------------------
#
# Official reference (Academic Graph API, /paper/search, "Paper relevance
# search") documents the query string verbatim in its example requests:
# https://api.semanticscholar.org/graph/v1/paper/search?query=covid+vaccination&offset=100&limit=3
# The published spec defines no separate parameter table for this operation.
#
# Auth: none required. "If you are using an API key, it must be set in the
# header x-api-key (case-sensitive)." The key is sent only when
# SEMANTIC_SCHOLAR_API_KEY is set and is never echoed in output.


def query_semantic_scholar(query: str) -> SourceResult:
    params = {
        "query": query,
        "limit": str(MAX_RECORDS),
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    headers: dict[str, str] = {}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    payload, status, error = _fetch_json(SEMANTIC_SCHOLAR_ENDPOINT, params, headers)
    if error:
        return SourceResult("semantic-scholar", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("semantic-scholar", http_status=status, error="Unexpected Semantic Scholar response shape")

    records: list[dict[str, Any]] = []
    for paper in (payload.get("data") or [])[:MAX_RECORDS]:
        if not isinstance(paper, dict):
            continue
        external_ids = paper.get("externalIds") or {}
        authors = [
            _clean(author.get("name"))
            for author in (paper.get("authors") or [])
            if isinstance(author, dict)
        ]
        authors = [author for author in authors if author]
        records.append(
            {
                "record_id": _clean(paper.get("paperId")),
                "title": _clean(paper.get("title")),
                "doi": _clean(external_ids.get("DOI")),
                "authors": authors,
                "year": paper.get("year"),
                "venue": _clean(paper.get("venue")),
                "url": _clean(paper.get("url")),
                "type": "paper",
                "publication_date": _clean(paper.get("publicationDate")),
                "citation_count": paper.get("citationCount"),
                "external_ids": {key: _clean(value) for key, value in external_ids.items()},
            }
        )

    if not records:
        return SourceResult("semantic-scholar", http_status=status)

    total = payload.get("total")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(records)
    data = _records_payload(
        "Semantic Scholar Academic Graph paper search",
        SEMANTIC_SCHOLAR_DOCS,
        SEMANTIC_SCHOLAR_ENDPOINT,
        query,
        records,
        total,
    )
    return SourceResult("semantic-scholar", data=data, http_status=status)


# -- arXiv ---------------------------------------------------------------------
#
# Official API user manual documents the endpoint and the parameter verbatim:
# http://export.arxiv.org/api/query?search_query=all:electron
# with the table entries `search_query`, `id_list`, `start`, `max_results`.
#
# Auth: none. "In cases where the API needs to be called multiple times in a
# row, we encourage you to play nice and incorporate a 3 second delay in your
# code." Response format: Atom XML.


def query_arxiv(query: str) -> SourceResult:
    params = {
        "search_query": "all:" + query,
        "start": "0",
        "max_results": str(MAX_RECORDS),
    }
    body, status, error = _fetch_bytes(ARXIV_ENDPOINT, params)
    if error:
        return SourceResult("arxiv", http_status=status, error=error)

    records: list[dict[str, Any]] = []
    try:
        feed = ET.fromstring(body)
        for entry in feed.findall(ARXIV_NAMESPACE + "entry")[:MAX_RECORDS]:
            identifier = _clean(entry.findtext(ARXIV_NAMESPACE + "id"))
            authors = [
                _text(author.findtext(ARXIV_NAMESPACE + "name"))
                for author in entry.findall(ARXIV_NAMESPACE + "author")
            ]
            authors = [author for author in authors if author]
            primary_category = entry.find(ARXIV_EXTRA_NAMESPACE + "primary_category")
            published = _clean(entry.findtext(ARXIV_NAMESPACE + "published"))
            records.append(
                {
                    "record_id": identifier.rsplit("/abs/", 1)[-1],
                    "title": _text(entry.findtext(ARXIV_NAMESPACE + "title")),
                    "doi": _clean(entry.findtext(ARXIV_EXTRA_NAMESPACE + "doi")),
                    "authors": authors,
                    "year": int(published[:4]) if published[:4].isdigit() else None,
                    "venue": "arXiv",
                    "url": identifier,
                    "type": "preprint",
                    "published": published,
                    "updated": _clean(entry.findtext(ARXIV_NAMESPACE + "updated")),
                    "primary_category": primary_category.get("term", "") if primary_category is not None else "",
                    "comment": _text(entry.findtext(ARXIV_EXTRA_NAMESPACE + "comment")),
                }
            )
    except ET.ParseError as exc:
        return SourceResult("arxiv", http_status=status, error="XML parse error: " + str(exc))

    if not records:
        return SourceResult("arxiv", http_status=status)

    total_text = _clean(feed.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults"))
    total = int(total_text) if total_text.isdigit() else len(records)
    data = _records_payload(
        "arXiv API",
        ARXIV_DOCS,
        ARXIV_ENDPOINT,
        query,
        records,
        total,
    )
    return SourceResult("arxiv", data=data, http_status=status)


# -- CORE ----------------------------------------------------------------------
#
# CORE API v3 OpenAPI document defines GET /v3/search/{entityType}/ with the
# required query parameter `q`: "Search query (use specific fields like doi,
# title, authors, etc.)". The same document's field table lists the camelCase
# response fields used below (for example 'yearPublished', 'downloadUrl',
# 'citationCount'); the published schema spells the same properties in
# snake_case, so the reader below accepts either spelling.
#
# Auth: none required. "Access to the CORE API is free and requires no
# authentication." Registered users may send the key as
# `Authorization: Bearer [API_KEY]`; it is only sent when CORE_API_KEY is set
# and is never echoed in output.


def _core_field(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return None


def query_core(query: str) -> SourceResult:
    params = {"q": query, "limit": str(MAX_RECORDS)}
    headers: dict[str, str] = {}
    api_key = os.environ.get("CORE_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = "Bearer " + api_key

    payload, status, error = _fetch_json(CORE_ENDPOINT, params, headers)
    if error:
        return SourceResult("core", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("core", http_status=status, error="Unexpected CORE response shape")

    results = payload.get("results") or []
    records: list[dict[str, Any]] = []
    for work in results[:MAX_RECORDS]:
        if not isinstance(work, dict):
            continue
        authors: list[str] = []
        for author in _core_field(work, "authors", "Authors") or []:
            if isinstance(author, dict):
                name = _clean(_core_field(author, "name", "Name")) or _clean(
                    _core_field(author, "firstName", "first_name")
                )
                if name:
                    authors.append(name)
            elif isinstance(author, str) and author.strip():
                authors.append(author.strip())
        year = _core_field(work, "yearPublished", "year_published")
        records.append(
            {
                "record_id": _clean(_core_field(work, "id", "coreId", "core_id")),
                "title": _clean(_core_field(work, "title", "Title")),
                "doi": _clean(_core_field(work, "doi", "DOI")),
                "authors": authors,
                "year": year,
                "venue": _clean(_core_field(work, "publisher", "Publisher")),
                "url": _clean(_core_field(work, "downloadUrl", "download_url")),
                "type": _clean(_core_field(work, "documentType", "document_type")),
                "publisher": _clean(_core_field(work, "publisher", "Publisher")),
                "download_url": _clean(_core_field(work, "downloadUrl", "download_url")),
                "arxiv_id": _clean(_core_field(work, "arxivId", "arxiv_id")),
            }
        )

    if not records:
        return SourceResult("core", http_status=status)

    total = payload.get("totalHits")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(records)
    data = _records_payload(
        "CORE API v3 works search",
        CORE_DOCS,
        CORE_ENDPOINT,
        query,
        records,
        total,
    )
    return SourceResult("core", data=data, http_status=status)


# -- OpenAIRE ------------------------------------------------------------------
#
# OpenAIRE Graph API V3 OpenAPI document defines GET /v3/research-products with
# the query parameter `search`: "Keyword-based search." It also documents
# `pageSize` ("Number of results per page").
#
# Auth: the published document declares no security scheme, so requests are
# unauthenticated. The terms of use document the limits: "up to 7200 requests
# per hour" authenticated and "up to 60 requests per hour" unauthenticated.


def query_openaire(query: str) -> SourceResult:
    params = {"search": query, "pageSize": str(MAX_RECORDS)}
    payload, status, error = _fetch_json(OPENAIR_E_ENDPOINT, params)
    if error:
        return SourceResult("openaire", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("openaire", http_status=status, error="Unexpected OpenAIRE response shape")

    results = payload.get("results") or []
    records: list[dict[str, Any]] = []
    for product in results[:MAX_RECORDS]:
        if not isinstance(product, dict):
            continue
        authors = [
            _clean(author.get("fullName"))
            for author in (product.get("authors") or [])
            if isinstance(author, dict)
        ]
        authors = [author for author in authors if author]
        doi = ""
        for pid in product.get("pids") or []:
            if isinstance(pid, dict) and _clean(pid.get("scheme")).casefold() == "doi":
                doi = _clean(pid.get("value"))
                break
        publication_date = _clean(product.get("publicationDate"))
        publisher = product.get("publisher")
        if isinstance(publisher, dict):
            publisher = _clean(publisher.get("name"))
        records.append(
            {
                "record_id": _clean(product.get("id")),
                "title": _clean(product.get("mainTitle")),
                "doi": doi,
                "authors": authors,
                "year": int(publication_date[:4]) if publication_date[:4].isdigit() else None,
                "venue": _clean((product.get("container") or {}).get("name"))
                if isinstance(product.get("container"), dict)
                else "",
                "url": _clean(product.get("id")),
                "type": _clean(product.get("type")),
                "publisher": _clean(publisher),
                "publication_date": publication_date,
            }
        )

    if not records:
        return SourceResult("openaire", http_status=status)

    header = payload.get("header") or {}
    total = header.get("numFound")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(records)
    data = _records_payload(
        "OpenAIRE Graph API V3 research products",
        OPENAIR_E_DOCS,
        OPENAIR_E_ENDPOINT,
        query,
        records,
        total,
    )
    return SourceResult("openaire", data=data, http_status=status)


# -- Unpaywall (dropped) -------------------------------------------------------


def query_unpaywall(query: str) -> SourceResult:
    """Never queried: Unpaywall documents no title/keyword/author search.

    Its documented title search (GET /v2/search?query=...) was retired on
    18 September 2026 and now returns 410 Gone, and its only live endpoint is a
    DOI lookup that also requires an email parameter. The documented reason is
    reported so the source is an auditable skip rather than a silent omission.
    """
    return _skip("unpaywall", UNSUPPORTED_SUB_SOURCES["unpaywall"])


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

    # Every candidate sub-source is reported once per run. An unsupported
    # sub-source is reported as a documented skip and is never queried.
    results = [
        query_openalex(value),
        query_crossref(value),
        query_semantic_scholar(value),
        query_arxiv(value),
        query_core(value),
        query_openaire(value),
        query_unpaywall(value),
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
