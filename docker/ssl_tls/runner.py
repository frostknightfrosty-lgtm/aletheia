"""SSL/TLS assessment batch runner.

A composite batch whose sub-sources are mostly local command line tools. One
query per sub-source per run; the runner dispatches by sub-source and invokes a
local tool as a subprocess with an argv list (never a shell string). Every
documented invocation, endpoint, authentication requirement and rate limit is
recorded in RATE_LIMITS.md next to this file, with the official documentation
URL and the source of each version pin. No flag, endpoint or version in this
file was inferred from an example response.

Standard library only (urllib, xml.etree.ElementTree, subprocess, shutil,
tempfile, json, hashlib, os, sys): the image installs the tools and python3, no
third-party Python package.

--health prints exactly "ok" on stdout and returns 0 without any network access
and without starting any subprocess: the tool inventory (which binary is
present, whether the optional SSL Labs credential is configured) is written to
stderr as one JSON line, because the Docker integration smoke case asserts
stdout.strip() == "ok".
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. Four are local command line tools installed in the
# image; one is the Qualys SSL Labs assessment API.
#   qualys-ssl-labs  GET https://api.ssllabs.com/api/v4/analyze?host=<host>
#   testssl          testssl [OPTIONS] <URI>              (testssl --jsonfile-pretty)
#   certgraph        certgraph [OPTION]... HOST...        (certgraph -json)
#   sslscan          sslscan [options] [host:port | host] (sslscan --xml=<file>)
#   tlsx             tlsx -u <host> -json -silent
SUPPORTED_SUB_SOURCES = (
    "qualys-ssl-labs",
    "testssl",
    "certgraph",
    "sslscan",
    "tlsx",
)

# Dropped sub-source. CipherScan is never queried and no URL or version is
# invented for it, so it is reported once per run as an auditable skip.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "cipherscan": (
        "CipherScan publishes no releases and no version tags: the project's own releases list "
        "(https://github.com/mozilla/cipherscan/releases) and tags list "
        "(https://github.com/mozilla/cipherscan/tags) are both empty, so no pinned, verifiable release "
        "artefact exists. Its README additionally documents that it ships its own pre-built OpenSSL "
        "binaries for Linux/64 and Darwin/64 rather than depending on a package-managed OpenSSL, so it "
        "cannot be pinned and installed from the project's own releases page."
    ),
}

# Official documentation of every implemented sub-source, and the exact
# documented endpoint of the one HTTP API.
QUALYS_DOCS = "https://github.com/ssllabs/ssllabs-scan/blob/master/ssllabs-api-docs-v4.md"
QUALYS_ENDPOINT = "https://api.ssllabs.com/api/v4/analyze"
TESTSSL_DOCS = "https://testssl.sh/"
CERTGRAPH_DOCS = "https://github.com/lanrat/certgraph"
SSLSCAN_DOCS = "https://github.com/rbsec/sslscan"
TLSX_DOCS = "https://github.com/projectdiscovery/tlsx"

# The documented invocation of each sub-source, verbatim from its own synopsis.
QUALYS_INVOCATION = "GET https://api.ssllabs.com/api/v4/analyze?host=<host>"
TESTSSL_INVOCATION = "testssl [OPTIONS] <URI>  (JSON: --jsonfile-pretty <file>)"
CERTGRAPH_INVOCATION = "certgraph [OPTION]... HOST...  (JSON: -json)"
SSLSCAN_INVOCATION = "sslscan [options] [host:port | host]  (XML: --xml=<file>)"
TLSX_INVOCATION = "tlsx -u <host> -json -silent"

# Debian bookworm installs the testssl.sh package as /usr/bin/testssl; the
# upstream script is called testssl.sh. Both names are accepted.
TOOL_BINARY_NAMES: dict[str, tuple[str, ...]] = {
    "testssl": ("testssl", "testssl.sh"),
    "certgraph": ("certgraph",),
    "sslscan": ("sslscan",),
    "tlsx": ("tlsx",),
}

# Documented version switches: testssl -v/--version, sslscan --version,
# certgraph -version, tlsx -version.
TOOL_VERSION_FLAG: dict[str, str] = {
    "testssl": "--version",
    "certgraph": "-version",
    "sslscan": "--version",
    "tlsx": "-version",
}

# go install writes to /go/bin in the golang image; apt writes to /usr/bin.
TOOL_SEARCH_PATHS = ("/go/bin", "/usr/local/bin", "/usr/bin", "/bin")

# One run answers a single input. Store at most this many records per sub-source.
MAX_RECORDS = 50

# Cap any single API response so a misbehaving endpoint cannot exhaust memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# Cap the verbatim output excerpt kept as raw evidence for local tools.
MAX_RAW_OUTPUT_CHARS = 2000

# A version probe is expected to return immediately; an assessment is allowed
# to take longer (testssl.sh runs several hundred ciphers).
VERSION_TIMEOUT_SECONDS = 30
TOOL_TIMEOUT_SECONDS = 240
HTTP_TIMEOUT_SECONDS = 45

USER_AGENT = "Aletheia/0.7.1 (ssl-tls)"

# SSL Labs registers a client by email and expects the registered address in
# the documented "email" request header. The value is only ever sent, never
# printed or recorded in the runner output.
SSLLABS_EMAIL_ENV = "SSLLABS_EMAIL"

# sslscan, certgraph and tlsx publish no severity classification, so their
# records are recorded as "info" instead of an invented rating. testssl.sh
# documents OK/INFO/WARN/LOW/MEDIUM/HIGH/CRITICAL and SSL Labs documents letter
# grades; those are normalized instead.
SEVERITY_VALUES = ("ok", "info", "warn", "low", "medium", "high", "critical")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _severity(value: Any) -> str:
    text = _clean(value).lower()
    if text == "warning":
        return "warn"
    if text in SEVERITY_VALUES:
        return text
    return "info"


def _tail(text: str, limit: int = MAX_RAW_OUTPUT_CHARS) -> str:
    return text[-limit:] if len(text) > limit else text


# -- local tool execution ------------------------------------------------------


def _find_tool(name: str) -> str | None:
    """Locate a tool binary on PATH or in the standard install directories."""
    for candidate in TOOL_BINARY_NAMES.get(name, (name,)):
        found = shutil.which(candidate)
        if found:
            return found
        for directory in TOOL_SEARCH_PATHS:
            path = os.path.join(directory, candidate)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def _run_tool(argv: list[str], timeout: int = TOOL_TIMEOUT_SECONDS) -> tuple[str, str, int, str | None]:
    """Run one local tool with an argv list. Returns (stdout, stderr, code, error).

    The argv list is passed directly to subprocess.run: no shell string is ever
    built and no shell is ever used, so a seed value can never be interpreted
    as shell syntax.
    """
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return "", "", 127, "binary not found: " + argv[0]
    except subprocess.TimeoutExpired:
        return "", "", 124, "timed out after " + str(timeout) + "s: " + argv[0]
    except OSError as exc:
        return "", "", 126, type(exc).__name__ + ": " + str(exc)
    return completed.stdout or "", completed.stderr or "", completed.returncode, None


def _tool_version(name: str, binary: str) -> str | None:
    """Read the tool's own version banner. Local only, never a network call."""
    flag = TOOL_VERSION_FLAG.get(name)
    if not flag:
        return None
    stdout, stderr, code, error = _run_tool([binary, flag], timeout=VERSION_TIMEOUT_SECONDS)
    if error:
        return None
    banner = stdout or stderr
    for line in banner.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return None


def _local_tool_error(name: str, code: int, stderr: str) -> str:
    detail = _clean(stderr.splitlines()[-1]) if stderr.strip() else ""
    message = name + " exited with code " + str(code)
    return message + (": " + detail[:300] if detail else "")


# -- payload assembly ----------------------------------------------------------


def _record(
    record_id: str,
    detail: str,
    severity: str = "info",
    **extra: Any,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "record_id": record_id,
        "detail": detail,
        "severity": _severity(severity),
    }
    for key, value in extra.items():
        if value not in (None, "", [], {}):
            record[key] = value
    return record


def _payload(
    *,
    api_source: str,
    api_documentation: str,
    endpoint: str | None,
    invocation: str,
    source_kind: str,
    tool: str,
    tool_version: str | None,
    command: list[str],
    exit_code: int,
    query: str,
    records: list[dict[str, Any]],
    total: int,
    raw_output: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "endpoint": endpoint,
        "invocation": invocation,
        "source_kind": source_kind,
        "tool": tool,
        "tool_version": tool_version,
        "command": command,
        "exit_code": exit_code,
        "query": query,
        "record_count": total,
        "truncated": total > len(records),
    }
    if raw_output is not None:
        data["raw_output_lines"] = len(raw_output.splitlines())
        data["raw_output_tail"] = _tail(raw_output)
    if extra:
        data.update(extra)
    data["records"] = records
    return data


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


# -- Qualys SSL Labs (HTTP API) ------------------------------------------------
#
# Official documentation (SSL Labs API v4): the main API entry point is
# "https://api.ssllabs.com/api/v4/" and the documented call that initiates an
# assessment and reports its progress is "analyze" with the mandatory parameter
# "host" ("Provide hostname"; the Host object documents that the assessment host
# "can be a hostname or an IP address"). The documented response is a single
# Host object whose "status" is DNS, ERROR, IN_PROGRESS or READY and whose
# endpoints carry ipAddress, serverName, statusMessage and grade.
#
# Auth: the v4 documentation introduces a registration API and the analyze call
# documents a mandatory "email" request header holding "the email address
# registered through the registration API"; an unregistered client receives 441.
# No account password, token or paid key is involved. The address is read from
# SSLLABS_EMAIL and sent in the documented header; when it is not configured the
# sub-source is reported as a skip instead of sending a request that the
# documentation says will be rejected.


def _qualys_status_severity(status: str) -> str:
    normalized = _clean(status).upper()
    if normalized == "READY":
        return "ok"
    if normalized == "ERROR":
        return "high"
    return "info"


def query_qualys_ssl_labs(host: str) -> SourceResult:
    email = os.environ.get(SSLLABS_EMAIL_ENV, "").strip()
    url = QUALYS_ENDPOINT + "?" + urllib.parse.urlencode({"host": host})
    if not email:
        return _skip(
            "qualys-ssl-labs",
            "The SSL Labs API v4 analyze call documents a mandatory email request header holding the "
            "address registered through the registration API, and answers 441 for an unregistered client. "
            + SSLLABS_EMAIL_ENV
            + " is not set, so no assessment was requested.",
        )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            # Documented request header; the value is never recorded in output.
            "email": email,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return SourceResult(
            "qualys-ssl-labs",
            http_status=exc.code,
            error="HTTP " + str(exc.code) + ": " + detail[:300],
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SourceResult(
            "qualys-ssl-labs", error=type(exc).__name__ + ": " + str(exc)
        )

    if len(body) > MAX_RESPONSE_BYTES:
        return SourceResult("qualys-ssl-labs", http_status=status, error="Response exceeded the 8 MB safety limit")

    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return SourceResult("qualys-ssl-labs", http_status=status, error="JSON decode error: " + str(exc))
    if not isinstance(payload, dict):
        return SourceResult("qualys-ssl-labs", http_status=status, error="Unexpected SSL Labs response shape")

    assessment_status = _clean(payload.get("status"))
    records: list[dict[str, Any]] = []
    for endpoint in payload.get("endpoints") or []:
        if not isinstance(endpoint, dict):
            continue
        grade = _clean(endpoint.get("grade"))
        status_message = _clean(endpoint.get("statusMessage"))
        address = _clean(endpoint.get("ipAddress")) or "endpoint"
        detail = "grade " + grade if grade else ("status " + status_message if status_message else "endpoint reported")
        records.append(
            _record(
                address,
                detail,
                _qualys_status_severity("READY" if status_message.lower() == "ready" else assessment_status),
                status_message=status_message,
                server_name=_clean(endpoint.get("serverName")),
                grade=grade,
                grade_trust_ignored=_clean(endpoint.get("gradeTrustIgnored")),
                has_warnings=endpoint.get("hasWarnings"),
            )
        )

    if not records:
        # The assessment is queued or still running (or failed): record the
        # documented Host status instead of pretending an endpoint exists.
        records.append(
            _record(
                "assessment",
                "assessment status " + (assessment_status or "UNKNOWN"),
                _qualys_status_severity(assessment_status),
                status=assessment_status,
                host=_clean(payload.get("host")),
                port=_clean(payload.get("port")),
                criteria_version=_clean(payload.get("criteriaVersion")),
                engine_version=_clean(payload.get("engineVersion")),
            )
        )

    data = _payload(
        api_source="Qualys SSL Labs Assessment API v4 (analyze)",
        api_documentation=QUALYS_DOCS,
        endpoint=QUALYS_ENDPOINT,
        invocation=QUALYS_INVOCATION,
        source_kind="http_api",
        tool="api.ssllabs.com",
        tool_version=_clean(payload.get("engineVersion")) or None,
        # The recorded command carries the documented request line only; the
        # credential header is deliberately not recorded.
        command=["GET", url],
        exit_code=0,
        query=host,
        records=records[:MAX_RECORDS],
        total=len(records),
        extra={
            "assessment_status": assessment_status,
            "criteria_version": _clean(payload.get("criteriaVersion")),
            "test_time": payload.get("testTime"),
            "is_public": payload.get("isPublic"),
        },
    )
    return SourceResult("qualys-ssl-labs", data=data, http_status=status)


# -- testssl.sh (local tool) ---------------------------------------------------
#
# Documented synopsis: "testssl.sh [OPTIONS] <URI>". The man page documents the
# JSON file output: "--jsonfile-pretty <jsonfile> ... logs the output in pretty
# JSON format ... The structure contains a header similar to the banner on the
# screen ... Each finding has a key/value pair identifier with the identifier
# for each single check, the severity and the finding." The reader below accepts
# either the flat finding array (--jsonfile) or the structured sections of
# --jsonfile-pretty, and reads only those documented keys.


def _iter_findings(node: Any, depth: int = 0) -> list[dict[str, Any]]:
    """Collect finding objects from a testssl.sh JSON document."""
    if depth > 3:
        return []
    findings: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                if any(key in item for key in ("id", "identifier", "severity", "finding")):
                    findings.append(item)
                else:
                    findings.extend(_iter_findings(item, depth + 1))
    elif isinstance(node, dict):
        for value in node.values():
            if isinstance(value, (list, dict)):
                findings.extend(_iter_findings(value, depth + 1))
    return findings


def _testssl_records(json_path: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        with open(json_path, "r", encoding="utf-8", errors="replace") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [], type(exc).__name__ + ": " + str(exc)

    records: list[dict[str, Any]] = []
    for finding in _iter_findings(payload):
        identifier = _clean(finding.get("id") or finding.get("identifier")) or "finding"
        detail = _clean(finding.get("finding") or finding.get("detail"))
        if not detail:
            continue
        records.append(
            _record(
                identifier,
                detail,
                _severity(finding.get("severity")),
                cve=_clean(finding.get("cve")),
                cwe=_clean(finding.get("cwe")),
                ip=_clean(finding.get("ip")),
                port=_clean(finding.get("port")),
            )
        )
    return records, None


def query_testssl(host: str) -> SourceResult:
    binary = _find_tool("testssl")
    if not binary:
        return SourceResult("testssl", error="testssl binary not found in the image")

    version = _tool_version("testssl", binary)
    workdir = tempfile.mkdtemp(prefix="aletheia-testssl-")
    json_path = os.path.join(workdir, "testssl.json")
    argv = [binary, "--quiet", "--jsonfile-pretty", json_path, host]
    stdout, stderr, code, error = _run_tool(argv)
    try:
        if error:
            return SourceResult("testssl", error=error)
        records, parse_error = _testssl_records(json_path)
        if not records:
            if parse_error or code != 0:
                return SourceResult(
                    "testssl",
                    error=parse_error or _local_tool_error("testssl", code, stderr),
                )
            return SourceResult("testssl")
        data = _payload(
            api_source="testssl.sh",
            api_documentation=TESTSSL_DOCS,
            endpoint=None,
            invocation=TESTSSL_INVOCATION,
            source_kind="local_tool",
            tool="testssl",
            tool_version=version,
            command=argv,
            exit_code=code,
            query=host,
            records=records[:MAX_RECORDS],
            total=len(records),
            raw_output=stdout,
        )
        return SourceResult("testssl", data=data)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# -- CertGraph (local tool) ----------------------------------------------------
#
# Documented usage: "Usage of ./certgraph: [OPTION]... HOST..." with the
# documented flags "-json print the graph as json, can be used for graph in web
# UI", "-depth uint maximum BFS depth to go (default 5)" and "-version print
# version and exit". The JSON document is the graph map (nodes/links/depth/
# numDomains) plus certgraph metadata, with domain nodes serialized as
# {type: domain, id, status, root, depth, related, hasDNS} and certificate nodes
# as {type: certificate, id, found}.

CERTGRAPH_MAX_DEPTH = "1"


def _certgraph_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in payload.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_type = _clean(node.get("type")) or "node"
        node_id = _clean(node.get("id")) or "unknown"
        if node_type == "domain":
            depth = _clean(node.get("depth"))
            status = _clean(node.get("status"))
            detail = "domain node"
            if depth:
                detail += " at depth " + depth
            if status:
                detail += ", status " + status
            records.append(
                _record(
                    "domain:" + node_id,
                    detail,
                    "info",
                    node_type=node_type,
                    depth=depth,
                    status=status,
                    root=_clean(node.get("root")),
                    has_dns=_clean(node.get("hasDNS")),
                    related=_clean(node.get("related")),
                )
            )
        else:
            records.append(
                _record(
                    node_type + ":" + node_id,
                    node_type + " node" + (", found via " + _clean(node.get("found")) if _clean(node.get("found")) else ""),
                    "info",
                    node_type=node_type,
                )
            )
    return records


def query_certgraph(host: str) -> SourceResult:
    binary = _find_tool("certgraph")
    if not binary:
        return SourceResult("certgraph", error="certgraph binary not found in the image")

    version = _tool_version("certgraph", binary)
    argv = [binary, "-json", "-depth", CERTGRAPH_MAX_DEPTH, host]
    stdout, stderr, code, error = _run_tool(argv)
    if error:
        return SourceResult("certgraph", error=error)

    payload: Any = None
    parse_error: str | None = None
    # An empty stdout with a zero exit code is "nothing to report", not a parse
    # failure; a non-empty stdout that is not JSON is an error.
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            parse_error = "JSON decode error: " + str(exc)
    if isinstance(payload, dict):
        records = _certgraph_records(payload)
    else:
        records = []

    if not records:
        if code != 0 or parse_error:
            return SourceResult("certgraph", error=parse_error or _local_tool_error("certgraph", code, stderr))
        return SourceResult("certgraph")

    data = _payload(
        api_source="CertGraph certificate graph crawl",
        api_documentation=CERTGRAPH_DOCS,
        endpoint=None,
        invocation=CERTGRAPH_INVOCATION,
        source_kind="local_tool",
        tool="certgraph",
        tool_version=version,
        command=argv,
        exit_code=code,
        query=host,
        records=records[:MAX_RECORDS],
        total=len(records),
        raw_output=stdout,
        extra={
            "graph_depth": payload.get("depth"),
            "num_domains": payload.get("numDomains"),
        },
    )
    return SourceResult("certgraph", data=data)


# -- sslscan (local tool) ------------------------------------------------------
#
# Documented synopsis: "sslscan [ options ] [host:port | host]" and the
# documented option "--xml=<file> Output results to an XML file. - can be used
# to mean stdout." The element and attribute names read below are exactly the
# ones the project's own sslscan.c writes with printf_xml:
#   <renegotiation supported="%d" secure="%d" />
#   <compression supported="%d" />
#   <fallback supported="0|1" />
#   <heartbleed sslversion="%s" vulnerable="0|1" />
#   <cipher status="accepted|preferred" sslversion="%s" bits="%d" cipher="%s"
#           id="%s" strength="%s" time="%u" />
# sslscan publishes no severity classification, so every record is recorded as
# "info" rather than an invented rating; the tool's own documented attribute
# values are carried instead.


def _sslscan_records(xml_path: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        tree = ET.parse(xml_path)
    except (OSError, ET.ParseError) as exc:
        return [], type(exc).__name__ + ": " + str(exc)

    records: list[dict[str, Any]] = []
    for element in tree.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag == "cipher":
            name = _clean(element.get("cipher")) or "unknown"
            status = _clean(element.get("status"))
            records.append(
                _record(
                    "cipher:" + name,
                    name + (" " + status if status else ""),
                    "info",
                    cipher=name,
                    status=status,
                    tls_version=_clean(element.get("sslversion")),
                    bits=_clean(element.get("bits")),
                    cipher_id=_clean(element.get("id")),
                    strength=_clean(element.get("strength")),
                )
            )
        elif tag == "heartbleed":
            version = _clean(element.get("sslversion"))
            vulnerable = _clean(element.get("vulnerable"))
            records.append(
                _record(
                    "heartbleed:" + (version or "unknown"),
                    "heartbleed vulnerable=" + (vulnerable or "unknown"),
                    "info",
                    tls_version=version,
                    vulnerable=vulnerable,
                )
            )
        elif tag == "renegotiation":
            supported = _clean(element.get("supported"))
            secure = _clean(element.get("secure"))
            records.append(
                _record(
                    "renegotiation",
                    "renegotiation supported=" + (supported or "unknown") + " secure=" + (secure or "unknown"),
                    "info",
                    supported=supported,
                    secure=secure,
                )
            )
        elif tag == "compression":
            supported = _clean(element.get("supported"))
            records.append(
                _record(
                    "compression",
                    "compression supported=" + (supported or "unknown"),
                    "info",
                    supported=supported,
                )
            )
        elif tag == "fallback":
            supported = _clean(element.get("supported"))
            records.append(
                _record(
                    "fallback",
                    "fallback supported=" + (supported or "unknown"),
                    "info",
                    supported=supported,
                )
            )
    return records, None


def query_sslscan(host: str) -> SourceResult:
    binary = _find_tool("sslscan")
    if not binary:
        return SourceResult("sslscan", error="sslscan binary not found in the image")

    version = _tool_version("sslscan", binary)
    workdir = tempfile.mkdtemp(prefix="aletheia-sslscan-")
    xml_path = os.path.join(workdir, "sslscan.xml")
    argv = [binary, "--no-colour", "--xml=" + xml_path, host]
    stdout, stderr, code, error = _run_tool(argv)
    try:
        if error:
            return SourceResult("sslscan", error=error)
        records, parse_error = _sslscan_records(xml_path)
        if not records:
            if parse_error or code != 0:
                return SourceResult("sslscan", error=parse_error or _local_tool_error("sslscan", code, stderr))
            return SourceResult("sslscan")
        data = _payload(
            api_source="sslscan SSL/TLS scanner",
            api_documentation=SSLSCAN_DOCS,
            endpoint=None,
            invocation=SSLSCAN_INVOCATION,
            source_kind="local_tool",
            tool="sslscan",
            tool_version=version,
            command=argv,
            exit_code=code,
            query=host,
            records=records[:MAX_RECORDS],
            total=len(records),
            raw_output=stdout,
        )
        return SourceResult("sslscan", data=data)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# -- tlsx (local tool) ---------------------------------------------------------
#
# Documented installation and usage: "go install
# github.com/projectdiscovery/tlsx/cmd/tlsx@latest" and the documented JSON
# output ("-j, -json display output in jsonline format"), documented host input
# ("-u, -host string[] target host to scan") and the documented update-check
# switch ("-duc, -disable-update-check"). The documented JSON example lists the
# field names read below: timestamp, host, ip, port, probe_status, tls_version,
# cipher, not_before, not_after, subject_dn, subject_cn, subject_org, sni.

TLSX_FIELDS = (
    "host",
    "ip",
    "port",
    "probe_status",
    "tls_version",
    "cipher",
    "not_before",
    "not_after",
    "subject_cn",
    "subject_org",
    "sni",
)


def _tlsx_records(stdout: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        host = _clean(entry.get("host")) or "unknown"
        port = _clean(entry.get("port"))
        detail_parts = [part for part in (_clean(entry.get("tls_version")), _clean(entry.get("cipher"))) if part]
        if entry.get("probe_status") is False:
            detail_parts.append("probe failed")
        detail = " ".join(detail_parts) or "tls record"
        extra = {field: entry.get(field) for field in TLSX_FIELDS if field not in ("host", "port")}
        records.append(
            _record(
                host + (":" + port if port else ""),
                detail,
                "info",
                **extra,
            )
        )
    return records


def query_tlsx(host: str) -> SourceResult:
    binary = _find_tool("tlsx")
    if not binary:
        return SourceResult("tlsx", error="tlsx binary not found in the image")

    version = _tool_version("tlsx", binary)
    # -duc disables the tool's automatic update check so an assessment does not
    # contact the project's own release endpoint.
    argv = [binary, "-u", host, "-json", "-silent", "-duc"]
    stdout, stderr, code, error = _run_tool(argv)
    if error:
        return SourceResult("tlsx", error=error)

    records = _tlsx_records(stdout)
    if not records:
        if code != 0:
            return SourceResult("tlsx", error=_local_tool_error("tlsx", code, stderr))
        return SourceResult("tlsx")

    data = _payload(
        api_source="tlsx TLS grabber",
        api_documentation=TLSX_DOCS,
        endpoint=None,
        invocation=TLSX_INVOCATION,
        source_kind="local_tool",
        tool="tlsx",
        tool_version=version,
        command=argv,
        exit_code=code,
        query=host,
        records=records[:MAX_RECORDS],
        total=len(records),
        raw_output=stdout,
    )
    return SourceResult("tlsx", data=data)


# -- CipherScan (dropped) ------------------------------------------------------


def query_cipherscan(host: str) -> SourceResult:
    """Never queried: CipherScan publishes no release or tag to pin.

    The runner reports the documented reason so the source is an auditable skip
    rather than a silent omission, and no URL or version is invented for it.
    """
    return _skip("cipherscan", UNSUPPORTED_SUB_SOURCES["cipherscan"])


# -- health --------------------------------------------------------------------


def _health_inventory() -> dict[str, Any]:
    """Describe sub-source availability without any network call or subprocess."""
    entries: list[dict[str, Any]] = []
    for name, kind in (
        ("qualys-ssl-labs", "http_api"),
        ("testssl", "local_tool"),
        ("certgraph", "local_tool"),
        ("sslscan", "local_tool"),
        ("tlsx", "local_tool"),
    ):
        if kind == "http_api":
            entries.append(
                {
                    "source": name,
                    "kind": kind,
                    "usable": True,
                    "endpoint": QUALYS_ENDPOINT,
                    "credential_env": SSLLABS_EMAIL_ENV,
                    "credential_configured": bool(os.environ.get(SSLLABS_EMAIL_ENV, "").strip()),
                    "detail": "reachability is not tested by --health; no network request is made",
                }
            )
        else:
            binary = _find_tool(name)
            entries.append(
                {
                    "source": name,
                    "kind": kind,
                    "usable": binary is not None,
                    "binary": binary,
                    "detail": "binary present in the image" if binary else "binary missing from the image",
                }
            )
    return {
        "health": "ok",
        "network_used": False,
        "subprocesses_started": False,
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
        print("input_type: domain, ip", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    valid_types = {"domain", "ip"}
    if input_type not in valid_types:
        print(
            "Invalid input_type: " + input_type + ". Must be one of: " + str(sorted(valid_types)),
            file=sys.stderr,
        )
        return 2

    # Every candidate sub-source is reported once per run. The dropped
    # sub-source is reported as a documented skip and is never queried.
    results = [
        query_qualys_ssl_labs(value),
        query_testssl(value),
        query_certgraph(value),
        query_sslscan(value),
        query_tlsx(value),
        query_cipherscan(value),
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
