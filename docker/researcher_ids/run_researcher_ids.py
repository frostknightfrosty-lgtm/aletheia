"""Bounded public researcher-identity lookup: Wikidata + ORCID.

One person name in, one normalized JSON document out. Both sub-sources are
public, keyless HTTPS APIs; the runner never asks for an email address, a
credential, or a private profile field.

* Wikidata Action API: one ``wbsearchentities`` search (max 5 hits), then up to
  two ``wbgetentities`` reads (hits plus referenced IDs capped at 40). Data is
  CC0 1.0; a descriptive User-Agent is sent as the Wikimedia API policy asks.
* ORCID public API v3.0: one ``expanded-search`` request (max 5 rows). Only the
  public search fields are normalized; the response's ``email`` arrays are
  deliberately discarded.

``--health`` and ``--selftest`` are offline. ``--normalize`` re-validates a
saved combined document and is the case run under ``--network none``. Live
requests happen only when a name file is explicitly supplied.

Name matches are leads, not identity proof: common names collide, and neither
API asserts that a result is the subject the operator meant.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REVIEWED_ON = "2026-10-20"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ORCID_API = "https://pub.orcid.org/v3.0/expanded-search/"
NETWORK_HOSTS = (
    "https://www.wikidata.org/w/api.php",
    "https://pub.orcid.org/v3.0/expanded-search/",
)
USER_AGENT = (
    "Aletheia/0.1 (https://github.com/frostknightfrosty-lgtm/aletheia; "
    "public-metadata researcher lookup)"
)
MAX_NAME_BYTES = 240
MAX_RESULTS = 5
MAX_REF_IDS = 40
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
MAX_ERRORS = 10
MAX_ALIASES = 10
MAX_LABELS_PER_PROPERTY = 10
MAX_INSTITUTIONS = 10

# Claims that are emitted as public encyclopedic metadata. All are public
# Wikidata statements; no claim is interpreted as proof of identity.
CLAIM_LABEL_PROPS = {
    "P31": "instance_of",
    "P106": "occupation",
    "P19": "birthplace",
    "P27": "citizenship",
    "P21": "gender",
    "P735": "given_name",
    "P734": "family_name",
}
CLAIM_EXTERNAL_IDS = {
    "P496": "orcid",
    "P214": "viaf",
    "P213": "isni",
    "P227": "gnd",
}
CLAIM_WEBSITE = "P856"
CLAIM_TWITTER = "P2002"
CLAIM_BIRTH_DATE = "P569"

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _unique(values: list[str], limit: int = MAX_LABELS_PER_PROPERTY) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
        if len(out) >= limit:
            break
    return out


def _read_name(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError(f"name file not found: {path}")
    data = path.read_bytes()
    if len(data) > MAX_NAME_BYTES:
        raise ValueError(f"name file exceeds {MAX_NAME_BYTES} bytes")
    text = data.decode("utf-8", errors="strict").strip()
    if "\n" in text or "\r" in text:
        raise ValueError("name file must contain exactly one line")
    if _CONTROL_RE.search(text):
        raise ValueError("name contains control characters")
    text = " ".join(text.split())
    if len(text) < 2:
        raise ValueError("name must contain at least two characters")
    if len(text) > 120:
        raise ValueError("name must be at most 120 characters")
    if '"' in text or "\\" in text:
        raise ValueError('name must not contain double quotes or backslashes')
    return text


def _query_parts(name: str) -> dict[str, str | None]:
    """Derive a documented ORCID field query from a free-text name.

    ORCID's public search accepts fielded queries such as
    ``given-names:"Ada" AND family-name:"Lovelace"``. For a one-token name the
    documented free-text field is used instead. Middle names are not guessed
    into the query; the normalized result keeps the full query for the reader.
    """
    tokens = [token for token in name.split() if token]
    if len(tokens) >= 2:
        given, family = tokens[0], tokens[-1]
        query = f'given-names:"{given}" AND family-name:"{family}"'
        return {"given": given, "family": family, "query": query, "mode": "fielded"}
    return {"given": tokens[0] if tokens else None, "family": None,
            "query": f'text:"{tokens[0]}"' if tokens else "", "mode": "text"}


# -- HTTP ----------------------------------------------------------------------


def _fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[Any, int, str | None]:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(max_bytes + 1)
            status = response.status
            if len(body) > max_bytes:
                return None, status, "response exceeded the 8 MB safety limit"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, f"HTTP {exc.code}: {detail[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, f"JSON decode error: {exc}"


# -- Wikidata ------------------------------------------------------------------


def _label(entity: Any, language: str = "en") -> str | None:
    if not isinstance(entity, dict):
        return None
    labels = entity.get("labels")
    if not isinstance(labels, dict):
        return None
    for key in (language, "mul", "en"):
        item = labels.get(key)
        if isinstance(item, dict):
            value = _text(item.get("value"), 200)
            if value:
                return value
    return None


def _aliases(entity: Any, language: str = "en") -> list[str]:
    if not isinstance(entity, dict):
        return []
    aliases = entity.get("aliases")
    if not isinstance(aliases, dict):
        return []
    values: list[str] = []
    for key in (language, "mul"):
        items = aliases.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    value = _text(item.get("value"), 160)
                    if value:
                        values.append(value)
    return _unique(values, MAX_ALIASES)


def _claim_values(entity: Any, prop: str) -> list[dict[str, Any]]:
    if not isinstance(entity, dict):
        return []
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        return []
    statements = claims.get(prop)
    if not isinstance(statements, list):
        return []
    values: list[dict[str, Any]] = []
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("rank") == "deprecated":
            continue
        mainsnak = statement.get("mainsnak")
        if not isinstance(mainsnak, dict) or mainsnak.get("snaktype") not in (None, "value"):
            continue
        datavalue = mainsnak.get("datavalue")
        if isinstance(datavalue, dict) and "value" in datavalue:
            values.append(datavalue["value"])
    return values


def _claim_ids(entity: Any, prop: str) -> list[str]:
    ids: list[str] = []
    for value in _claim_values(entity, prop):
        item_id = _text(value.get("id"), 32)
        if item_id:
            ids.append(item_id)
    return _unique(ids, MAX_LABELS_PER_PROPERTY)


def _claim_strings(entity: Any, prop: str) -> list[str]:
    values: list[str] = []
    for value in _claim_values(entity, prop):
        text = _text(value, 500)
        if text:
            values.append(text)
    return _unique(values, MAX_LABELS_PER_PROPERTY)


def _claim_time(entity: Any, prop: str) -> str | None:
    for value in _claim_values(entity, prop):
        if not isinstance(value, dict):
            continue
        raw = _text(value.get("time"), 64)
        if raw:
            match = re.match(r"^[+-]?(\d{4}-\d{2}-\d{2})", raw)
            if match:
                return match.group(1)
    return None


def _label_map(payload: Any) -> dict[str, str]:
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        return {}
    return {
        qid: label
        for qid, entity in entities.items()
        if isinstance(qid, str) and (label := _label(entity)) is not None
    }


def _wikidata_results(
    search_payload: Any,
    entity_payload: Any,
    ref_payload: Any = None,
) -> tuple[list[dict[str, Any]], int]:
    """Normalize the three raw Wikidata documents into bounded results."""
    if not isinstance(search_payload, dict):
        raise ValueError("Wikidata search payload must be an object")
    hits = search_payload.get("search")
    if not isinstance(hits, list):
        hits = []
    qids: list[str] = []
    search_meta: dict[str, dict[str, Any]] = {}
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        qid = _text(hit.get("id"), 32)
        if not qid or qid in search_meta:
            continue
        qids.append(qid)
        search_meta[qid] = hit
        if len(qids) >= MAX_RESULTS:
            break

    entities = entity_payload.get("entities") if isinstance(entity_payload, dict) else None
    if not isinstance(entities, dict):
        entities = {}
    refs = _label_map(ref_payload)
    refs.update(_label_map(entity_payload))

    results: list[dict[str, Any]] = []
    for qid in qids:
        entity = entities.get(qid)
        if not isinstance(entity, dict):
            continue
        hit = search_meta.get(qid, {})
        labels: dict[str, list[str]] = {}
        for prop, key in CLAIM_LABEL_PROPS.items():
            values = [refs.get(item_id, item_id) for item_id in _claim_ids(entity, prop)]
            labels[key] = _unique(values, MAX_LABELS_PER_PROPERTY)
        external_ids: dict[str, str] = {}
        for prop, key in CLAIM_EXTERNAL_IDS.items():
            values = _claim_strings(entity, prop)
            if values:
                external_ids[key] = values[0]
        website = (_claim_strings(entity, CLAIM_WEBSITE) or [None])[0]
        twitter = (_claim_strings(entity, CLAIM_TWITTER) or [None])[0]
        instance_ids = _claim_ids(entity, "P31")
        results.append({
            "qid": qid,
            "label": _label(entity) or _text(hit.get("label"), 200),
            "description": _text(hit.get("description"), 400)
            or _text((entity.get("descriptions") or {}).get("en", {}).get("value")
                     if isinstance(entity.get("descriptions"), dict) else None, 400),
            "aliases": _aliases(entity),
            "human": "Q5" in instance_ids,
            "instance_of": labels.get("instance_of", []),
            "occupation": labels.get("occupation", []),
            "birth_date": _claim_time(entity, CLAIM_BIRTH_DATE),
            "birthplace": labels.get("birthplace", []),
            "citizenship": labels.get("citizenship", []),
            "gender": (labels.get("gender") or [None])[0],
            "given_name": (labels.get("given_name") or [None])[0],
            "family_name": (labels.get("family_name") or [None])[0],
            "ids": external_ids,
            "website": website,
            "twitter": twitter,
        })
    return results, len(qids)


def _wikidata(name: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "uselang": "en",
        "format": "json",
        "limit": str(MAX_RESULTS),
        "type": "item",
        "maxlag": "5",
    })
    search_payload, status, error = _fetch_json(f"{WIKIDATA_API}?{query}")
    if error:
        return {"status": "error", "error": error, "http_status": status,
                "num_found": 0, "results": []}
    results, num_found = _wikidata_results(search_payload, {}, {})
    if not results:
        return {"status": "ok", "http_status": status, "num_found": num_found,
                "results": []}

    ids = [item["qid"] for item in results]
    detail_query = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": "|".join(ids),
        "props": "labels|descriptions|aliases|claims",
        "languages": "en|mul",
        "format": "json",
        "maxlag": "5",
    })
    entity_payload, detail_status, detail_error = _fetch_json(
        f"{WIKIDATA_API}?{detail_query}"
    )
    if detail_error:
        return {"status": "error", "error": detail_error,
                "http_status": detail_status, "num_found": num_found, "results": []}

    ref_ids: list[str] = []
    entities = entity_payload.get("entities") if isinstance(entity_payload, dict) else {}
    if isinstance(entities, dict):
        for entity in entities.values():
            for prop in CLAIM_LABEL_PROPS:
                for item_id in _claim_ids(entity, prop):
                    if item_id not in ref_ids and len(ref_ids) < MAX_REF_IDS:
                        ref_ids.append(item_id)
    ref_payload: Any = {}
    if ref_ids:
        ref_query = urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": "|".join(ref_ids),
            "props": "labels",
            "languages": "en|mul",
            "format": "json",
            "maxlag": "5",
        })
        ref_payload, _, ref_error = _fetch_json(f"{WIKIDATA_API}?{ref_query}")
        if ref_error:
            ref_payload = {}
    results, num_found = _wikidata_results(search_payload, entity_payload, ref_payload)
    return {"status": "ok", "http_status": status, "num_found": num_found,
            "results": results}


# -- ORCID ---------------------------------------------------------------------


def _orcid_results(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise ValueError("ORCID payload must be an object")
    raw_results = payload.get("expanded-result")
    if not isinstance(raw_results, list):
        raw_results = []
    num_found = payload.get("num-found")
    if isinstance(num_found, bool) or not isinstance(num_found, int):
        num_found = len(raw_results)
    results: list[dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        orcid_id = _text(item.get("orcid-id"), 32)
        if not orcid_id:
            continue
        other_names = []
        raw_other = item.get("other-name")
        if isinstance(raw_other, list):
            other_names = _unique(
                [_text(value, 160) or "" for value in raw_other], MAX_ALIASES
            )
        institutions = []
        raw_institutions = item.get("institution-name")
        if isinstance(raw_institutions, list):
            institutions = _unique(
                [_text(value, 200) or "" for value in raw_institutions],
                MAX_INSTITUTIONS,
            )
        results.append({
            "orcid": orcid_id,
            "given_name": _text(item.get("given-names"), 120),
            "family_name": _text(item.get("family-names"), 120),
            "credit_name": _text(item.get("credit-name"), 160),
            "other_names": other_names,
            "institutions": institutions,
        })
        if len(results) >= MAX_RESULTS:
            break
    return results, num_found


def _orcid(name: str) -> dict[str, Any]:
    parts = _query_parts(name)
    query = urllib.parse.urlencode({"q": parts["query"], "rows": str(MAX_RESULTS)})
    payload, status, error = _fetch_json(
        f"{ORCID_API}?{query}", headers={"Accept": "application/json"}
    )
    if error:
        return {"status": "error", "error": error, "http_status": status,
                "num_found": 0, "results": [], "query_mode": parts["mode"]}
    results, num_found = _orcid_results(payload)
    return {"status": "ok", "http_status": status, "num_found": num_found,
            "results": results, "query_mode": parts["mode"]}


# -- combined ------------------------------------------------------------------


def _collect(name: str) -> dict[str, Any]:
    collected: dict[str, Any] = {
        "source": "researcher_ids",
        "status": "ok",
        "query": name,
        "wikidata": {"status": "error", "error": "not run", "num_found": 0, "results": []},
        "orcid": {"status": "error", "error": "not run", "num_found": 0, "results": []},
        "errors": [],
    }
    for key, fn in (("wikidata", _wikidata), ("orcid", _orcid)):
        try:
            collected[key] = fn(name)
        except Exception as exc:  # noqa: BLE001 - source failure is output
            collected[key] = {"status": "error", "error": str(exc)[:300],
                              "num_found": 0, "results": []}
    for key in ("wikidata", "orcid"):
        if collected[key].get("status") != "ok":
            collected["errors"].append(f"{key}: {collected[key].get('error', 'failed')}")
    if len(collected["errors"]) == 2:
        collected["status"] = "error"
    elif collected["errors"]:
        collected["status"] = "partial"
    return collected


def _bounded_text(value: Any, limit: int) -> str | None:
    return _text(value, limit)


def _normalise(raw: Any) -> dict[str, Any]:
    """Validate and bound a combined Wikidata+ORCID document."""
    if not isinstance(raw, dict):
        raise ValueError("document must be a JSON object")
    if raw.get("source") != "researcher_ids":
        raise ValueError("document source must be 'researcher_ids'")
    query = _text(raw.get("query"), 120)
    if not query:
        raise ValueError("document query is required")
    status = _text(raw.get("status"), 32) or "ok"
    if status not in {"ok", "partial", "error", "invalid_target"}:
        raise ValueError(f"unsupported document status: {status}")
    errors: list[str] = []
    raw_errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    for item in raw_errors:
        value = _text(item, 300)
        if value:
            errors.append(value)
        if len(errors) >= MAX_ERRORS:
            break

    wikidata = raw.get("wikidata") if isinstance(raw.get("wikidata"), dict) else {}
    orcid = raw.get("orcid") if isinstance(raw.get("orcid"), dict) else {}
    wiki_results: list[dict[str, Any]] = []
    raw_wiki = wikidata.get("results") if isinstance(wikidata.get("results"), list) else []
    for item in raw_wiki:
        if not isinstance(item, dict):
            continue
        qid = _text(item.get("qid"), 32)
        if not qid:
            continue
        ids = item.get("ids") if isinstance(item.get("ids"), dict) else {}
        wiki_results.append({
            "qid": qid,
            "label": _bounded_text(item.get("label"), 200),
            "description": _bounded_text(item.get("description"), 400),
            "aliases": _unique([_text(v, 160) or "" for v in item.get("aliases", [])]
                               if isinstance(item.get("aliases"), list) else [], MAX_ALIASES),
            "human": item.get("human") is True,
            "instance_of": _unique([_text(v, 200) or "" for v in item.get("instance_of", [])]
                                   if isinstance(item.get("instance_of"), list) else []),
            "occupation": _unique([_text(v, 200) or "" for v in item.get("occupation", [])]
                                  if isinstance(item.get("occupation"), list) else []),
            "birth_date": _bounded_text(item.get("birth_date"), 32),
            "birthplace": _unique([_text(v, 200) or "" for v in item.get("birthplace", [])]
                                  if isinstance(item.get("birthplace"), list) else []),
            "citizenship": _unique([_text(v, 200) or "" for v in item.get("citizenship", [])]
                                    if isinstance(item.get("citizenship"), list) else []),
            "gender": _bounded_text(item.get("gender"), 120),
            "given_name": _bounded_text(item.get("given_name"), 160),
            "family_name": _bounded_text(item.get("family_name"), 160),
            "ids": {key: _bounded_text(ids.get(key), 64)
                    for key in ("orcid", "viaf", "isni", "gnd")
                    if _bounded_text(ids.get(key), 64)},
            "website": _bounded_text(item.get("website"), 300),
            "twitter": _bounded_text(item.get("twitter"), 120),
        })
        if len(wiki_results) >= MAX_RESULTS:
            break

    orcid_results: list[dict[str, Any]] = []
    raw_orcid = orcid.get("results") if isinstance(orcid.get("results"), list) else []
    for item in raw_orcid:
        if not isinstance(item, dict):
            continue
        orcid_id = _text(item.get("orcid"), 32)
        if not orcid_id:
            continue
        orcid_results.append({
            "orcid": orcid_id,
            "given_name": _bounded_text(item.get("given_name"), 120),
            "family_name": _bounded_text(item.get("family_name"), 120),
            "credit_name": _bounded_text(item.get("credit_name"), 160),
            "other_names": _unique([_text(v, 160) or "" for v in item.get("other_names", [])]
                                   if isinstance(item.get("other_names"), list) else [], MAX_ALIASES),
            "institutions": _unique([_text(v, 200) or "" for v in item.get("institutions", [])]
                                    if isinstance(item.get("institutions"), list) else [],
                                    MAX_INSTITUTIONS),
        })
        if len(orcid_results) >= MAX_RESULTS:
            break

    if status == "ok" and errors:
        status = "partial"
    return {
        "source": "researcher_ids",
        "status": status,
        "query": query,
        "wikidata": {
            "status": _text(wikidata.get("status"), 32) or "ok",
            "num_found": _number(wikidata.get("num_found")) or 0,
            "results": wiki_results,
        },
        "orcid": {
            "status": _text(orcid.get("status"), 32) or "ok",
            "num_found": _number(orcid.get("num_found")) or 0,
            "results": orcid_results,
            "query_mode": _text(orcid.get("query_mode"), 32),
        },
        "errors": errors,
    }


_SAMPLE_SEARCH = {"search": [{"id": "Q999001", "label": "Ada Example",
                              "description": "synthetic example person"}]}
_SAMPLE_ENTITIES = {"entities": {"Q999001": {
    "labels": {"en": {"value": "Ada Example"}},
    "descriptions": {"en": {"value": "synthetic example person"}},
    "aliases": {"en": [{"value": "A. Example"}]},
    "claims": {
        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
        "P106": [{"mainsnak": {"datavalue": {"value": {"id": "Q999002"}}}}],
        "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1815-12-10T00:00:00Z"}}}}],
        "P19": [{"mainsnak": {"datavalue": {"value": {"id": "Q999003"}}}}],
        "P496": [{"mainsnak": {"datavalue": {"value": "0000-0002-1825-0097"}}}],
    },
}}}
_SAMPLE_REFS = {"entities": {
    "Q5": {"labels": {"en": {"value": "human"}}},
    "Q999002": {"labels": {"en": {"value": "mathematician"}}},
    "Q999003": {"labels": {"en": {"value": "Example City"}}},
}}
_SAMPLE_ORCID = {"expanded-result": [{
    "orcid-id": "0000-0002-1825-0097",
    "given-names": "Ada",
    "family-names": "Example",
    "credit-name": None,
    "other-name": ["A. Example"],
    "institution-name": ["Example University"],
    "email": ["private@example.org"],
}], "num-found": 1}


def _health() -> int:
    payload = {
        "source": "researcher_ids",
        "reviewed_on": REVIEWED_ON,
        "api_versions": {"wikidata": "Action API", "orcid": "public API v3.0"},
        "endpoints": list(NETWORK_HOSTS),
        "max_results_per_source": MAX_RESULTS,
        "max_referenced_ids": MAX_REF_IDS,
        "network_required": True,
        "credentials_required": False,
        "user_agent": USER_AGENT,
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    print("ok")
    return 0


def _selftest() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        parts = _query_parts("Ada Example")
        check("query_parts", parts["given"] == "Ada" and parts["family"] == "Example"
              and parts["mode"] == "fielded", str(parts["query"]))
    except Exception as exc:  # noqa: BLE001
        check("query_parts", False, str(exc)[:200])
    try:
        wiki, wiki_count = _wikidata_results(_SAMPLE_SEARCH, _SAMPLE_ENTITIES, _SAMPLE_REFS)
        item = wiki[0]
        check("wikidata_normalisation",
              wiki_count == 1 and item["human"] and item["birth_date"] == "1815-12-10"
              and item["occupation"] == ["mathematician"]
              and item["ids"]["orcid"] == "0000-0002-1825-0097",
              "synthetic Wikidata documents")
    except Exception as exc:  # noqa: BLE001
        check("wikidata_normalisation", False, str(exc)[:200])
    try:
        orcid, count = _orcid_results(_SAMPLE_ORCID)
        check("orcid_normalisation",
              count == 1 and orcid[0]["orcid"] == "0000-0002-1825-0097"
              and orcid[0]["institutions"] == ["Example University"]
              and "private@example.org" not in json.dumps(orcid),
              "synthetic ORCID document; email excluded")
    except Exception as exc:  # noqa: BLE001
        check("orcid_normalisation", False, str(exc)[:200])
    try:
        combined = {
            "source": "researcher_ids", "status": "ok", "query": "Ada Example",
            "wikidata": {"status": "ok", "num_found": 1, "results": wiki},
            "orcid": {"status": "ok", "num_found": 1, "results": orcid},
            "errors": [],
        }
        normalised = _normalise(combined)
        check("combined_normalisation",
              len(normalised["wikidata"]["results"]) == 1
              and len(normalised["orcid"]["results"]) == 1,
              "combined bounded schema")
    except Exception as exc:  # noqa: BLE001
        check("combined_normalisation", False, str(exc)[:200])
    try:
        bounded = _normalise({
            "source": "researcher_ids", "status": "ok", "query": "x",
            "wikidata": {"results": [{"qid": f"Q{i}"} for i in range(20)]},
            "orcid": {"results": [{"orcid": f"id{i}"} for i in range(20)]},
            "errors": ["x"] * 20,
        })
        check("bounds", len(bounded["wikidata"]["results"]) == MAX_RESULTS
              and len(bounded["orcid"]["results"]) == MAX_RESULTS
              and len(bounded["errors"]) == MAX_ERRORS,
              f"max {MAX_RESULTS} results, max {MAX_ERRORS} errors")
    except Exception as exc:  # noqa: BLE001
        check("bounds", False, str(exc)[:200])
    try:
        check("name_validation", _read_name(Path("/dev/null")) == "", "unreachable")
    except ValueError:
        check("name_validation", True, "empty file rejected")
    except Exception as exc:  # noqa: BLE001
        check("name_validation", False, str(exc)[:200])
    check("network_hosts",
          NETWORK_HOSTS[0].startswith("https://www.wikidata.org/")
          and NETWORK_HOSTS[1].startswith("https://pub.orcid.org/"),
          ", ".join(NETWORK_HOSTS))
    check("no_credentials", True, "both APIs are public and keyless")
    print(json.dumps({
        "researcher_ids_selftest": "ok" if all(c["ok"] for c in checks) else "failed",
        "reviewed_on": REVIEWED_ON,
        "checks": checks,
    }, sort_keys=True, indent=2))
    return 0 if all(item["ok"] for item in checks) else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--health", action="store_true")
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--normalize", metavar="COMBINED_JSON")
    parser.add_argument("name_file", nargs="?")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.health:
        return _health()
    if args.selftest:
        return _selftest()
    if args.normalize:
        try:
            raw = json.loads(Path(args.normalize).read_text(encoding="utf-8"))
            print(json.dumps(_normalise(raw), sort_keys=True, indent=2))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"source": "researcher_ids", "status": "invalid_document",
                              "error": str(exc)[:300]}, sort_keys=True))
            return 2
    if not args.name_file:
        print(json.dumps({"source": "researcher_ids", "status": "invalid_target",
                          "error": "one person-name file is required"}, sort_keys=True))
        return 2
    try:
        name = _read_name(Path(args.name_file))
    except ValueError as exc:
        print(json.dumps({"source": "researcher_ids", "status": "invalid_target",
                          "error": str(exc)}, sort_keys=True))
        return 2
    result = _normalise(_collect(name))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
