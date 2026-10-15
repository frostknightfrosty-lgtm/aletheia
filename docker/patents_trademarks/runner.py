"""Patent and trademark intelligence batch runner.

A composite batch whose sub-sources are the USPTO Open Data Portal API, the
USPTO Trademark Status and Document Retrieval (TSDR) API and the EPO Open
Patent Services (OPS) API. Every endpoint, query parameter, authentication
requirement, documented rate limit and documentation URL was read from the
sub-source's own official documentation or confirmed against the live
sub-source endpoint, and is recorded in RATE_LIMITS.md next to this file. No
endpoint, parameter name or version was inferred from an example response.

Standard library only (urllib, json, hashlib, base64, os, sys,
xml.etree.ElementTree): the image installs no third-party Python package.

--health prints exactly "ok" on stdout and returns 0 without any network access:
the sub-source inventory (kind, endpoint, whether a required key is configured)
is written to stderr as one JSON line, because the Docker integration smoke case
asserts stdout.strip() == "ok". No secret value is ever printed or recorded.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. All four are HTTPS APIs; each one is queried at most
# once per run.
SUPPORTED_SUB_SOURCES = (
    "uspto-open-data",
    "uspto-patent-assignment",
    "uspto-tsdr",
    "epo-ops",
)

# Dropped candidates. Each is reported once per run as an auditable skip with the
# exact reason below and is never queried; no endpoint is invented for it. These
# strings are duplicated verbatim in app/aletheia/adapters/patents_trademarks.py
# and tests/fixtures/patents_trademarks.json.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "patentsview": (
        "The PatentsView Search API host does not exist: search.patentsview.org returns NXDOMAIN from the "
        "system resolver and from 1.1.1.1 and 8.8.8.8, and the legacy hosts api.patentsview.org and "
        "patentsview.org now serve the USPTO Open Data Portal single-page application instead of any "
        "PatentsView API reference. The legacy PatentsView API was retired and no reachable PatentsView "
        "request contract exists, so no endpoint or parameter is invented for it."
    ),
    "google-patents-bigquery": (
        "The Google Patents public dataset is reachable only through BigQuery, which requires a Google Cloud "
        "project authenticated with Application Default Credentials or a service-account key plus the "
        "google-cloud-bigquery client library; Google documents no unauthenticated or free-key HTTP path to "
        "bigquery-public-data.google_patents. The runner uses the Python standard library only, so the "
        "candidate is dropped rather than adding a third-party dependency."
    ),
    "euipo-esearch-plus": (
        "EUIPO exposes its trademark and design APIs only through the EUIPO API Portal, which requires an "
        "account, a sandbox access request and a separate production-access application under the EUIPO "
        "conditions of use; there is no free-key or unauthenticated search endpoint. The older eSearch "
        "plus/copla endpoints reset the connection (WinError 10054) and the EUIPO API page answered HTTP 403, "
        "so the request contract cannot be verified and the approval path cannot be completed here."
    ),
}

# -- documented endpoints ------------------------------------------------------
#
# Every constant below is the verbatim endpoint from the sub-source's own
# documentation or was confirmed against the live endpoint; the docs URL for each
# one is recorded next to it and in RATE_LIMITS.md.

# USPTO Open Data Portal (ODP) Patent Search API. The documented search call is
# GET https://api.uspto.gov/api/v1/patent/applications/search with the documented
# query parameters q, dateRangeData.startDate, dateRangeData.endDate, start and
# rows, and the mandatory X-API-KEY header. Confirmed live: no key answers HTTP
# 401 {"message":"Unauthorized"} and a bogus X-API-KEY answers HTTP 403
# {"message":"Forbidden"}.
USPTO_ODP_DOCS = "https://data.uspto.gov/apis"
USPTO_ODP_SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"

# USPTO Open Data Portal patent application assignment data. The documented call
# is GET https://api.uspto.gov/api/v1/patent/applications/{applicationNumberText}/assignment
# with the same X-API-KEY header. Confirmed live: HTTP 401 without a key.
USPTO_ODP_ASSIGNMENT_URL = (
    "https://api.uspto.gov/api/v1/patent/applications/{application_number}/assignment"
)

# USPTO TSDR trademark case status. The documented sample URL is
# GET https://tsdrapi.uspto.gov/ts/cd/casestatus/sn<serial>/info.xml with the
# mandatory USPTO-API-KEY header. Confirmed live: HTTP 401 with the message
# "Beginning October 2, you will need to register for an API key ...".
USPTO_TSDR_DOCS = "https://www.uspto.gov/sites/default/files/documents/tm-enterprise-api-user-guide-v2.pdf"
USPTO_TSDR_STATUS_URL = "https://tsdrapi.uspto.gov/ts/cd/casestatus/sn{serial}/info.xml"

# EPO Open Patent Services (OPS). The documented token call is
# POST https://ops.epo.org/3.2/auth/accesstoken with HTTP Basic credentials and
# grant_type=client_credentials, and the documented published-data search call is
# GET https://ops.epo.org/3.2/rest-services/published-data/search?q=<query> with
# an Authorization: Bearer token. Confirmed live: a keyless search answers HTTP
# 403 "violation of Fair Use policy" and a dummy token request answers HTTP 401
# "ClientId is Invalid".
EPO_OPS_DOCS = "https://developers.epo.org/"
EPO_OPS_TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
EPO_OPS_SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"

# This adapter's own environment-variable names. None of these is published by a
# vendor; each one maps to the credential the vendor's own documentation
# requires (the X-API-KEY header, the USPTO-API-KEY header, or OAuth 2.0 client
# credentials). The name is the only thing this adapter chooses; no vendor fact
# is invented.
USPTO_ODP_API_KEY_ENV = "USPTO_ODP_API_KEY"
USPTO_TSDR_API_KEY_ENV = "USPTO_TSDR_API_KEY"
EPO_OPS_CONSUMER_KEY_ENV = "EPO_OPS_CONSUMER_KEY"
EPO_OPS_CONSUMER_SECRET_ENV = "EPO_OPS_CONSUMER_SECRET"

# Documented human-readable invocation of each sub-source.
USPTO_ODP_INVOCATION = "GET https://api.uspto.gov/api/v1/patent/applications/search?q=<query>"
USPTO_ODP_ASSIGNMENT_INVOCATION = (
    "GET https://api.uspto.gov/api/v1/patent/applications/<applicationNumberText>/assignment"
)
USPTO_TSDR_INVOCATION = "GET https://tsdrapi.uspto.gov/ts/cd/casestatus/sn<serial>/info.xml"
EPO_OPS_INVOCATION = "GET https://ops.epo.org/3.2/rest-services/published-data/search?q=<query>"

# Documented skip reasons for the implemented sub-sources. The runner records one
# of these instead of sending a request the documentation says will be rejected.
USPTO_ODP_KEY_SKIP_REASON = (
    "USPTO_ODP_API_KEY is not set. The USPTO Open Data Portal documents a mandatory X-API-KEY header and "
    'answers HTTP 401 {"message":"Unauthorized"} without a key, so the sub-source is not queried.'
)
USPTO_TSDR_KEY_SKIP_REASON = (
    "USPTO_TSDR_API_KEY is not set. The USPTO TSDR API documents a mandatory USPTO-API-KEY header and "
    "answers HTTP 401 without a key, so the sub-source is not queried."
)
EPO_OPS_KEY_SKIP_REASON = (
    "EPO_OPS_CONSUMER_KEY and EPO_OPS_CONSUMER_SECRET are not set. The EPO OPS token endpoint documents "
    'OAuth 2.0 client credentials and answers HTTP 401 {"error":"ClientId is Invalid"} without valid '
    "credentials, so the sub-source is not queried."
)
USPTO_ODP_ASSIGNMENT_INPUT_SKIP_REASON = (
    "The USPTO Open Data Portal assignment route is keyed by application number (GET "
    "/api/v1/patent/applications/<applicationNumberText>/assignment) and the supplied value contains no "
    "digits, so no application number can be formed."
)
USPTO_TSDR_INPUT_SKIP_REASON = (
    "The USPTO TSDR case-status route documents a trademark serial number in the path (GET "
    "/ts/cd/casestatus/sn<serial>/info.xml) and the supplied value contains no digits, so no serial number "
    "can be formed."
)

USER_AGENT = "Aletheia/0.9.0 (patents-trademarks)"

# One run answers a single seed. Store at most this many records per sub-source.
MAX_RECORDS = 25

# Cap any single response so a misbehaving endpoint cannot exhaust memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

HTTP_TIMEOUT_SECONDS = 30


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _digits(value: str) -> str:
    """Return the value as a pure digit string, or "" when it is not numeric.

    Patent application numbers and trademark serial numbers are numeric. A value
    that also carries letters (a publication number or a name) is reported as a
    documented skip for the number-keyed routes instead of being truncated.
    """
    text = _clean(value)
    for separator in ("-", " ", ",", "/", "."):
        text = text.replace(separator, "")
    return text if text.isdigit() else ""


def _local_name(tag: Any) -> str:
    """Strip an XML namespace from a tag and return the local name."""
    return str(tag).split("}")[-1]


def _xml_to_dict(element: ElementTree.Element) -> Any:
    """Convert an XML element into nested dicts of leaf text values."""
    children = list(element)
    if not children:
        return (element.text or "").strip()
    result: dict[str, Any] = {}
    for child in children:
        tag = _local_name(child.tag)
        value = _xml_to_dict(child)
        if tag in result:
            if not isinstance(result[tag], list):
                result[tag] = [result[tag]]
            result[tag].append(value)
        else:
            result[tag] = value
    return result


def _deep_first(value: Any, names: tuple[str, ...]) -> Any:
    """Find the first scalar value for any of names, case-insensitively."""
    lowered = {name.lower() for name in names}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in lowered and isinstance(item, (str, int, float)):
                return item
        for item in value.values():
            found = _deep_first(item, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _deep_first(item, names)
            if found is not None:
                return found
    return None


# -- HTTP ----------------------------------------------------------------------


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[bytes | None, int, str | None, str]:
    """Perform one HTTP request. Returns (body, http_status, error, content_type).

    Any credential is carried inside the request headers by the caller; neither
    the URL nor the headers are ever printed by this runner.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,application/xml,*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            if len(body) > max_bytes:
                return None, status, (
                    "Response exceeded the " + str(max_bytes // (1024 * 1024)) + " MB safety limit"
                ), content_type
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        return None, exc.code, "HTTP " + str(exc.code) + ": " + detail[:500], content_type
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__ + ": " + str(exc), ""
    return body, status, None, content_type


def _fetch_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> tuple[Any, int, str | None]:
    body, status, error, _ = _request(url, method=method, headers=headers, data=data)
    if error:
        return None, status, error
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


def _fetch_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[str | None, int, str | None]:
    body, status, error, _ = _request(url, headers=headers)
    if error:
        return None, status, error
    return body.decode("utf-8", errors="replace"), status, None


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


def _payload(
    *,
    api_source: str,
    api_documentation: str,
    endpoint: str,
    invocation: str,
    query: str,
    records: list[dict[str, Any]],
    total: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "endpoint": endpoint,
        "invocation": invocation,
        "query": query,
        "record_count": total,
        "truncated": total > len(records),
    }
    if extra:
        data.update(extra)
    data["records"] = records
    return data


# -- USPTO Open Data Portal Patent Search --------------------------------------


def query_uspto_open_data(value: str) -> SourceResult:
    api_key = os.environ.get(USPTO_ODP_API_KEY_ENV, "").strip()
    if not api_key:
        return _skip("uspto-open-data", USPTO_ODP_KEY_SKIP_REASON)

    params = {"q": value, "rows": str(MAX_RECORDS), "start": "0"}
    endpoint = USPTO_ODP_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    # The key travels in the X-API-KEY header, never in the recorded URL.
    data, status, error = _fetch_json(endpoint, headers={"X-API-KEY": api_key})
    if error:
        return SourceResult("uspto-open-data", http_status=status, error=error)
    if not isinstance(data, dict):
        return SourceResult(
            "uspto-open-data", http_status=status, error="Unexpected response shape from the USPTO Open Data Portal"
        )

    patents = data.get("patents")
    if not isinstance(patents, list) or not patents:
        return SourceResult("uspto-open-data", http_status=status)

    records: list[dict[str, Any]] = []
    for patent in patents[:MAX_RECORDS]:
        if not isinstance(patent, dict):
            continue
        application_number = _clean(patent.get("applicationNumberText"))
        patent_number = _clean(patent.get("patentNumber"))
        title = _clean(patent.get("inventionTitle"))
        record_id = application_number or patent_number
        inventors = [
            _clean(inv.get("inventorNameText"))
            for inv in (patent.get("inventors") or [])
            if isinstance(inv, dict) and _clean(inv.get("inventorNameText"))
        ]
        applicants = [
            _clean(app.get("applicantNameText"))
            for app in (patent.get("applicants") or [])
            if isinstance(app, dict) and _clean(app.get("applicantNameText"))
        ]
        records.append(
            {
                "record_id": record_id,
                "detail": "USPTO patent application " + (application_number or patent_number or value) + ": " + (title or "no title"),
                "application_number": application_number or None,
                "patent_number": patent_number or None,
                "invention_title": title or None,
                "application_filing_date": patent.get("applicationFilingDate"),
                "grant_date": patent.get("grantDate"),
                "application_status_code": patent.get("applicationStatusCode"),
                "application_status_date": patent.get("applicationStatusDate"),
                "application_type_label_name": patent.get("applicationTypeLabelName"),
                "inventors": inventors,
                "applicants": applicants,
            }
        )
    if not records:
        return SourceResult("uspto-open-data", http_status=status)

    total = data.get("count")
    payload = _payload(
        api_source="USPTO Open Data Portal Patent Search API",
        api_documentation=USPTO_ODP_DOCS,
        endpoint=endpoint,
        invocation=USPTO_ODP_INVOCATION,
        query=value,
        records=records,
        total=total if isinstance(total, int) else len(patents),
    )
    return SourceResult("uspto-open-data", data=payload, http_status=status)


# -- USPTO Open Data Portal Patent Assignment ----------------------------------


def query_uspto_patent_assignment(value: str) -> SourceResult:
    api_key = os.environ.get(USPTO_ODP_API_KEY_ENV, "").strip()
    if not api_key:
        return _skip("uspto-patent-assignment", USPTO_ODP_KEY_SKIP_REASON)

    application_number = _digits(value)
    if not application_number:
        return _skip("uspto-patent-assignment", USPTO_ODP_ASSIGNMENT_INPUT_SKIP_REASON)

    endpoint = USPTO_ODP_ASSIGNMENT_URL.format(
        application_number=urllib.parse.quote(application_number, safe="")
    )
    data, status, error = _fetch_json(endpoint, headers={"X-API-KEY": api_key})
    if error:
        return SourceResult("uspto-patent-assignment", http_status=status, error=error)
    if not isinstance(data, dict) or not data:
        return SourceResult("uspto-patent-assignment", http_status=status)

    # The ODP assignment response schema is documented as an object with no fixed
    # properties, so the whole object is stored verbatim as the assignment record.
    record = {
        "record_id": application_number,
        "detail": "USPTO Open Data Portal patent assignment data for application " + application_number,
        "application_number": application_number,
        "assignment": data,
    }
    payload = _payload(
        api_source="USPTO Open Data Portal Patent Assignment Data",
        api_documentation=USPTO_ODP_DOCS,
        endpoint=endpoint,
        invocation=USPTO_ODP_ASSIGNMENT_INVOCATION,
        query=value,
        records=[record],
        total=1,
        extra={"application_number": application_number},
    )
    return SourceResult("uspto-patent-assignment", data=payload, http_status=status)


# -- USPTO TSDR ----------------------------------------------------------------


def query_uspto_tsdr(value: str) -> SourceResult:
    api_key = os.environ.get(USPTO_TSDR_API_KEY_ENV, "").strip()
    if not api_key:
        return _skip("uspto-tsdr", USPTO_TSDR_KEY_SKIP_REASON)

    serial = _digits(value)
    if not serial:
        return _skip("uspto-tsdr", USPTO_TSDR_INPUT_SKIP_REASON)

    endpoint = USPTO_TSDR_STATUS_URL.format(serial=serial)
    text, status, error = _fetch_text(endpoint, headers={"USPTO-API-KEY": api_key})
    if error:
        return SourceResult("uspto-tsdr", http_status=status, error=error)
    if not text:
        return SourceResult("uspto-tsdr", http_status=status)

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return SourceResult("uspto-tsdr", http_status=status, error="XML decode error: " + str(exc))

    case_status_data = _xml_to_dict(root)
    if not case_status_data:
        return SourceResult("uspto-tsdr", http_status=status)

    application_number = _deep_first(case_status_data, ("ApplicationNumber", "ApplicationNumberText")) or serial
    record = {
        "record_id": _clean(application_number) or serial,
        "detail": "USPTO TSDR trademark case status for serial " + serial,
        "application_number": _clean(application_number) or serial,
        "registration_number": _clean(_deep_first(case_status_data, ("RegistrationNumber",))) or None,
        "mark_verbal_element_text": _clean(
            _deep_first(case_status_data, ("MarkVerbalElementText", "MarkVerbalElementTextFormatted"))
        )
        or None,
        "status_description": _clean(
            _deep_first(
                case_status_data,
                ("MarkCurrentStatusExternalDescriptionText", "MarkCurrentStatusExternalDescription"),
            )
        )
        or None,
        "status_date": _clean(_deep_first(case_status_data, ("StatusDate",))) or None,
        "filing_date": _clean(_deep_first(case_status_data, ("FilingDate",))) or None,
        "case_status_data": case_status_data,
    }
    payload = _payload(
        api_source="USPTO TSDR Trademark Case Status API",
        api_documentation=USPTO_TSDR_DOCS,
        endpoint=endpoint,
        invocation=USPTO_TSDR_INVOCATION,
        query=value,
        records=[record],
        total=1,
    )
    return SourceResult("uspto-tsdr", data=payload, http_status=status)


# -- EPO Open Patent Services --------------------------------------------------


def _epo_ops_token(consumer_key: str, consumer_secret: str) -> tuple[str | None, int, str | None]:
    credentials = base64.b64encode((consumer_key + ":" + consumer_secret).encode("utf-8")).decode("ascii")
    data, status, error = _fetch_json(
        EPO_OPS_TOKEN_URL,
        method="POST",
        headers={
            "Authorization": "Basic " + credentials,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=b"grant_type=client_credentials",
    )
    if error:
        return None, status, error
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        return None, status, "OAuth token response did not contain an access_token"
    return token, status, None


def query_epo_ops(value: str) -> SourceResult:
    consumer_key = os.environ.get(EPO_OPS_CONSUMER_KEY_ENV, "").strip()
    consumer_secret = os.environ.get(EPO_OPS_CONSUMER_SECRET_ENV, "").strip()
    if not consumer_key or not consumer_secret:
        return _skip("epo-ops", EPO_OPS_KEY_SKIP_REASON)

    token, status, error = _epo_ops_token(consumer_key, consumer_secret)
    if error:
        return SourceResult("epo-ops", http_status=status, error=error)

    endpoint = EPO_OPS_SEARCH_URL + "?" + urllib.parse.urlencode({"q": value})
    text, status, error = _fetch_text(
        endpoint, headers={"Authorization": "Bearer " + token, "Accept": "application/xml"}
    )
    if error:
        return SourceResult("epo-ops", http_status=status, error=error)
    if not text:
        return SourceResult("epo-ops", http_status=status)

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return SourceResult("epo-ops", http_status=status, error="XML decode error: " + str(exc))

    total: Any = None
    for element in root.iter():
        if "total-result-count" in element.attrib:
            total = element.attrib.get("total-result-count")
            break

    records: list[dict[str, Any]] = []
    for element in root.iter():
        if _local_name(element.tag) != "document-id":
            continue
        fields = {_local_name(child.tag): (child.text or "").strip() for child in element}
        doc_number = fields.get("doc-number")
        if not doc_number:
            continue
        country = fields.get("country") or ""
        kind = fields.get("kind") or ""
        record_id = (country + doc_number + kind).strip()
        records.append(
            {
                "record_id": record_id,
                "detail": "EPO OPS publication " + record_id,
                "country": country or None,
                "doc_number": doc_number,
                "kind": kind or None,
            }
        )
        if len(records) >= MAX_RECORDS:
            break

    if not records:
        return SourceResult("epo-ops", http_status=status)

    total_int = int(total) if isinstance(total, str) and total.isdigit() else len(records)
    payload = _payload(
        api_source="EPO Open Patent Services (OPS) published-data search",
        api_documentation=EPO_OPS_DOCS,
        endpoint=endpoint,
        invocation=EPO_OPS_INVOCATION,
        query=value,
        records=records,
        total=total_int,
        extra={"total_result_count": total},
    )
    return SourceResult("epo-ops", data=payload, http_status=status)


# -- dropped candidates --------------------------------------------------------


def query_patentsview(value: str) -> SourceResult:
    """Never queried: the PatentsView host no longer resolves. Auditable skip."""
    return _skip("patentsview", UNSUPPORTED_SUB_SOURCES["patentsview"])


def query_google_patents_bigquery(value: str) -> SourceResult:
    """Never queried: BigQuery needs GCP service-account auth. Auditable skip."""
    return _skip("google-patents-bigquery", UNSUPPORTED_SUB_SOURCES["google-patents-bigquery"])


def query_euipo_esearch_plus(value: str) -> SourceResult:
    """Never queried: EUIPO API access needs an approved account. Auditable skip."""
    return _skip("euipo-esearch-plus", UNSUPPORTED_SUB_SOURCES["euipo-esearch-plus"])


# -- health --------------------------------------------------------------------


def _health_inventory() -> dict[str, Any]:
    """Describe sub-source availability without any network call."""
    entries: list[dict[str, Any]] = []
    for name, endpoint, credential_env in (
        ("uspto-open-data", USPTO_ODP_SEARCH_URL, USPTO_ODP_API_KEY_ENV),
        ("uspto-patent-assignment", USPTO_ODP_ASSIGNMENT_URL, USPTO_ODP_API_KEY_ENV),
        ("uspto-tsdr", USPTO_TSDR_STATUS_URL, USPTO_TSDR_API_KEY_ENV),
        ("epo-ops", EPO_OPS_SEARCH_URL, EPO_OPS_CONSUMER_KEY_ENV),
    ):
        entries.append(
            {
                "source": name,
                "kind": "http_api",
                "usable": True,
                "endpoint": endpoint,
                "credential_env": credential_env,
                "credential_configured": (
                    bool(os.environ.get(credential_env, "").strip()) if credential_env else None
                ),
                "detail": "reachability is not tested by --health; no network request is made",
            }
        )
    for name in sorted(UNSUPPORTED_SUB_SOURCES):
        entries.append(
            {
                "source": name,
                "kind": "dropped",
                "usable": False,
                "endpoint": None,
                "credential_env": None,
                "credential_configured": None,
                "detail": UNSUPPORTED_SUB_SOURCES[name],
            }
        )
    return {
        "health": "ok",
        "network_used": False,
        "sub_sources": entries,
        "dropped_sub_sources": sorted(UNSUPPORTED_SUB_SOURCES),
    }


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        # stdout must stay exactly "ok" (the Docker integration case asserts
        # stdout.strip() == "ok"), so the inventory goes to stderr.
        print(json.dumps(_health_inventory(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        print("ok")
        return 0

    if len(sys.argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        print("input_type: intellectual_property", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    valid_types = {"intellectual_property"}
    if input_type not in valid_types:
        print(
            "Invalid input_type: " + input_type + ". Must be one of: " + str(sorted(valid_types)),
            file=sys.stderr,
        )
        return 2

    # Every candidate sub-source is reported once per run. Dropped candidates are
    # reported as documented skips and are never queried.
    results = [
        query_uspto_open_data(value),
        query_uspto_patent_assignment(value),
        query_uspto_tsdr(value),
        query_epo_ops(value),
        query_patentsview(value),
        query_google_patents_bigquery(value),
        query_euipo_esearch_plus(value),
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
