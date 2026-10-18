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
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. Five are local command line tools installed in the
# image (CipherScan, which publishes no releases, is checked out at a pinned
# commit); one is the Qualys SSL Labs assessment API.
#   qualys-ssl-labs  GET https://api.ssllabs.com/api/v4/analyze?host=<host>
#   testssl          testssl [OPTIONS] <URI>              (testssl --jsonfile-pretty)
#   certgraph        certgraph [OPTION]... HOST...        (certgraph -json)
#   sslscan          sslscan [options] [host:port | host] (sslscan --xml=<file>)
#   tlsx             tlsx -u <host> -json -silent
#   cipherscan       cipherscan [-j|--json] <target:port>  (port defaults to 443)
SUPPORTED_SUB_SOURCES = (
    "qualys-ssl-labs",
    "testssl",
    "certgraph",
    "sslscan",
    "tlsx",
    "cipherscan",
)

# No candidate of this batch is dropped: every sub-source is implemented. The
# mapping is kept (and reported by the health inventory) so a future candidate
# that cannot be pinned still lands here as an auditable, reasoned skip rather
# than a silent omission; nobody is in it today.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {}

# Official documentation of every implemented sub-source, and the exact
# documented endpoint of the one HTTP API.
QUALYS_DOCS = "https://github.com/ssllabs/ssllabs-scan/blob/master/ssllabs-api-docs-v4.md"
QUALYS_ENDPOINT = "https://api.ssllabs.com/api/v4/analyze"
TESTSSL_DOCS = "https://testssl.sh/"
CERTGRAPH_DOCS = "https://github.com/lanrat/certgraph"
SSLSCAN_DOCS = "https://github.com/rbsec/sslscan"
TLSX_DOCS = "https://github.com/projectdiscovery/tlsx"
# CipherScan publishes no releases and no tags; it is pinned by the exact
# commit the image checks out (verified with git rev-parse at build time).
# cscan.sh -- the "more precise scan" the script runs in its tolerance section
# -- needs tlslite-ng and python-ecdsa, which the image pre-provisions at
# pinned releases (SHAs below) so no scan clones anything at run time.
CIPHERSCAN_DOCS = "https://github.com/mozilla/cipherscan"
CIPHERSCAN_PINNED_COMMIT = "30bd23938853d68b51c2ebe4bcc922cc3113c5e2"
CIPHERSCAN_TLSLITE_NG_PIN = "c93df82603ab4a72c8d65645a3aeee73eeb24b3f (v0.8.2)"
CIPHERSCAN_PYTHON_ECDSA_PIN = "bd66899550d7185939bf27b75713a2ac9325a9d3 (python-ecdsa-0.19.2)"

# The documented invocation of each sub-source, verbatim from its own synopsis.
QUALYS_INVOCATION = "GET https://api.ssllabs.com/api/v4/analyze?host=<host>"
TESTSSL_INVOCATION = "testssl [OPTIONS] <URI>  (JSON: --jsonfile-pretty <file>)"
CERTGRAPH_INVOCATION = "certgraph [OPTION]... HOST...  (JSON: -json)"
SSLSCAN_INVOCATION = "sslscan [options] [host:port | host]  (XML: --xml=<file>)"
TLSX_INVOCATION = "tlsx -u <host> -json -silent"
CIPHERSCAN_INVOCATION = "cipherscan [-j|--json] <target:port>  (port defaults to 443)"

# Debian bookworm installs the testssl.sh package as /usr/bin/testssl; the
# upstream script is called testssl.sh. Both names are accepted.
TOOL_BINARY_NAMES: dict[str, tuple[str, ...]] = {
    "testssl": ("testssl", "testssl.sh"),
    "certgraph": ("certgraph",),
    "sslscan": ("sslscan",),
    "tlsx": ("tlsx",),
    "cipherscan": ("cipherscan",),
}

# Documented version switches: testssl -v/--version, sslscan --version,
# certgraph -version, tlsx -version. CipherScan's usage text documents no
# version switch, so it has no entry here: the version recorded for it is the
# pinned commit the image checked out.
TOOL_VERSION_FLAG: dict[str, str] = {
    "testssl": "--version",
    "certgraph": "-version",
    "sslscan": "--version",
    "tlsx": "-version",
}

# go install writes to /go/bin in the golang image; apt writes to /usr/bin.
# The CipherScan checkout lives at /opt/cipherscan and is invoked from there
# (never through a symlink) so the script resolves its own bundled OpenSSL and
# cscan.sh next to itself.
TOOL_SEARCH_PATHS = ("/go/bin", "/usr/local/bin", "/usr/bin", "/bin", "/opt/cipherscan")

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
        if code != 0:
            # A non-zero exit is a tool failure. Report it directly rather than
            # letting the missing or partial artefact surface as a parse error,
            # which would hide the exit code that identifies the failure.
            return SourceResult("testssl", error=_local_tool_error("testssl", code, stderr))
        records, parse_error = _testssl_records(json_path)
        if not records:
            if parse_error:
                return SourceResult("testssl", error=parse_error)
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
        if code != 0:
            # Same ordering rule as testssl: the tool's exit code is the failure
            # signal and must not be replaced by an artefact parse error.
            return SourceResult("sslscan", error=_local_tool_error("sslscan", code, stderr))
        records, parse_error = _sslscan_records(xml_path)
        if not records:
            if parse_error:
                return SourceResult("sslscan", error=parse_error)
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


# -- CipherScan (local tool) ---------------------------------------------------
#
# CipherScan is a wrapper around "openssl s_client" (its README) whose JSON
# output is documented in the README ("Exporting to JSON with the -j command
# line option") and whose synopsis documents "[-j|--json] [-o|--openssl file]
# [openssl s_client args] <target:port>" with "Port defaults to 443". The
# script ships its own pre-built OpenSSL for Linux/64 and falls back to the
# system one when the bundled binary is not executable.
#
# The JSON object this runner reads is the one the script's own
# display_results_in_json emits: "target", "utctimestamp", "serverside",
# "ciphersuite" (an array of objects with "cipher", "protocols", "pubkey",
# "sigalg", "trusted", "ticket_hint", "ocsp_stapling", "npn", "pfs" and, for
# ECDH ciphers, "curves" and "curves_ordering"), "renegotiation",
# "compression", a "configs" object and, when the tolerance test ran, an
# "intolerancies" array. All values are OpenSSL-style strings ("True"/"False")
# and are recorded verbatim, never converted.
CIPHERSCAN_CIPHER_FIELDS = (
    "protocols",
    "pubkey",
    "sigalg",
    "trusted",
    "ticket_hint",
    "ocsp_stapling",
    "npn",
    "pfs",
    "curves",
    "curves_ordering",
)


def _cipherscan_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    target = _clean(payload.get("target")) or "unknown"
    for entry in payload.get("ciphersuite") or []:
        if not isinstance(entry, dict):
            continue
        cipher = _clean(entry.get("cipher"))
        if not cipher:
            continue
        detail_parts = [cipher]
        protocols = entry.get("protocols")
        if isinstance(protocols, list) and protocols:
            detail_parts.append("protocols=" + ",".join(_clean(part) for part in protocols))
        pfs = _clean(entry.get("pfs"))
        if pfs:
            detail_parts.append("pfs=" + pfs)
        trusted = _clean(entry.get("trusted"))
        if trusted:
            detail_parts.append("trusted=" + trusted)
        extra = {field: entry.get(field) for field in CIPHERSCAN_CIPHER_FIELDS}
        records.append(
            _record(
                target + "/" + cipher,
                " ".join(detail_parts),
                "info",
                **extra,
            )
        )
    return records


def query_cipherscan(host: str) -> SourceResult:
    binary = _find_tool("cipherscan")
    if not binary:
        return SourceResult("cipherscan", error="cipherscan binary not found in the image")

    # CipherScan documents no version switch, so the recorded version is the
    # pinned commit the image checked out and verified at build time.
    argv = [binary, "-j", host]
    stdout, stderr, code, error = _run_tool(argv)
    if error:
        return SourceResult("cipherscan", error=error)

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        if code != 0:
            return SourceResult("cipherscan", error=_local_tool_error("cipherscan", code, stderr))
        return SourceResult("cipherscan", error="cipherscan did not print JSON output")
    if not isinstance(payload, dict):
        return SourceResult("cipherscan", error="cipherscan JSON output is not an object")

    records = _cipherscan_records(payload)
    if not records:
        if code != 0:
            return SourceResult("cipherscan", error=_local_tool_error("cipherscan", code, stderr))
        return SourceResult("cipherscan")

    extra = {
        "target": _clean(payload.get("target")),
        "utctimestamp": _clean(payload.get("utctimestamp")),
        "serverside": _clean(payload.get("serverside")),
        "renegotiation": _clean(payload.get("renegotiation")),
        "compression": _clean(payload.get("compression")),
        "configs_tested": len(payload.get("configs") or {}),
        "intolerancies_present": bool(payload.get("intolerancies")),
        "pinned_commit": CIPHERSCAN_PINNED_COMMIT,
    }
    extra = {key: value for key, value in extra.items() if value not in (None, "", [], {})}
    data = _payload(
        api_source="CipherScan (openssl s_client wrapper)",
        api_documentation=CIPHERSCAN_DOCS,
        endpoint=None,
        invocation=CIPHERSCAN_INVOCATION,
        source_kind="local_tool",
        tool="cipherscan",
        tool_version=CIPHERSCAN_PINNED_COMMIT,
        command=argv,
        exit_code=code,
        query=host,
        records=records[:MAX_RECORDS],
        total=len(records),
        raw_output=stdout,
        extra=extra,
    )
    return SourceResult("cipherscan", data=data)


def _cipherscan_selftest() -> dict[str, Any]:
    """Boot a loopback TLS server, scan it with the pinned checkout, stop it.

    This is the capture case for the sub-source: a self-signed certificate is
    generated in a temporary directory with the system openssl, a local
    "openssl s_server" answers on 127.0.0.1, the very same query_cipherscan
    runs against it, and the server is stopped again. It exercises the pinned
    checkout end to end -- including the pre-provisioned tolerance-test
    dependencies -- without touching any host outside the container.
    """
    report: dict[str, Any] = {
        "cipherscan_selftest": "failed",
        "pinned_commit": CIPHERSCAN_PINNED_COMMIT,
    }
    binary = _find_tool("cipherscan")
    if not binary:
        report["error"] = "cipherscan binary not found in the image"
        return report
    openssl = shutil.which("openssl")
    if not openssl:
        report["error"] = "system openssl binary not found in the image"
        return report

    with tempfile.TemporaryDirectory() as tmp:
        cert = os.path.join(tmp, "cert.pem")
        key = os.path.join(tmp, "key.pem")
        generated = subprocess.run(
            [
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", key, "-out", cert, "-days", "1",
                "-subj", "/CN=aletheia-selftest",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if generated.returncode != 0:
            report["error"] = "self-signed certificate generation failed"
            return report

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        target = "127.0.0.1:" + str(port)
        server = subprocess.Popen(
            [openssl, "s_server", "-accept", target, "-cert", cert, "-key", key, "-www"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            ready = False
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.2)
            if not ready:
                report["error"] = "loopback TLS server did not become ready"
                return report
            result = query_cipherscan(target)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)

    if result.error:
        report["error"] = result.error
        return report
    data = result.data or {}
    report["cipherscan_selftest"] = "ok"
    report["target"] = target
    report["ciphers_found"] = data.get("record_count", 0)
    report["tool_version"] = data.get("tool_version")
    report["renegotiation"] = data.get("renegotiation")
    report["configs_tested"] = data.get("configs_tested")
    return report


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
        ("cipherscan", "local_tool"),
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

    if sys.argv[1:] == ["--selftest-cipherscan"]:
        report = _cipherscan_selftest()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report.get("cipherscan_selftest") == "ok" else 1

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

    # Every candidate sub-source of the batch is implemented and queried; the
    # results list keeps one entry per candidate.
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
