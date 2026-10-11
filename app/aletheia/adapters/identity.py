from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    EntityType,
    Finding,
    Provenance,
    SeedType,
)


def _prov(adapter: AdapterDescriptor, *, source_url: str | None, confidence: float, raw: bytes | None = None,
          notes: list[str] | None = None) -> Provenance:
    import hashlib
    return Provenance(
        tool=adapter.name,
        source_url=source_url,
        confidence=confidence,
        adapter_version=adapter.version_pin,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
        notes=notes or [],
    )


def _result(request: AdapterRunRequest, adapter: AdapterDescriptor, started: datetime,
            findings: list[Finding], stdout: str, stderr: str, exit_code: int,
            artifacts: list[str] | None = None) -> AdapterRunResult:
    return AdapterRunResult(
        run_id=request.run_id, adapter=adapter,
        status="succeeded" if exit_code == 0 else "partial",
        started_at=started, finished_at=datetime.now(timezone.utc), exit_code=exit_code,
        findings=findings, artifacts=artifacts or [], stderr_tail=stderr[-4000:], stdout_tail=stdout[-4000:],
    )


class IdentityAdapter(Adapter):
    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self.descriptor.input_types


class MaigretAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="maigret", license="MIT", input_types=[SeedType.USERNAME], output_types=[EntityType.URL, EntityType.SERVICE],
        legal_notes=[
            "Public username checks only; no authentication, CAPTCHA solving, Cloudflare bypass, Tor, I2P, or recursive identifier search is enabled by this wrapper.",
            "Honor site terms, robots/policy, rate limits, and applicable law."
        ],
        rate_limit="One username per container invocation; upstream site checks enforce their own timing.",
        invocation="CLI in dedicated Docker container", version_pin="0.6.6",
        upstream="https://github.com/soxoj/maigret", network_required=True,
        docker_image="aletheia/maigret:0.6.6",
        output_schema={"claimed_accounts": "object[]"}, health_check="maigret --version",
        requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["maigret", request.seed.value, "--json", "ndjson", "--folderoutput", "/work/results"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        raw_parts: list[bytes] = [stdout.encode()]
        files = sorted((workspace / "results").glob("*.json")) if (workspace / "results").exists() else []
        files += sorted((workspace / "results").glob("*.ndjson")) if (workspace / "results").exists() else []
        for path in files:
            raw_parts.append(path.read_bytes())
        payloads: list[object] = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError:
                    try:
                        payloads.append(json.loads(text))
                        break
                    except json.JSONDecodeError:
                        continue
        if not payloads and stdout.strip():
            for line in stdout.splitlines():
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        raw = b"\n".join(raw_parts)
        seen: set[str] = set()
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            site_name = payload.get("site") or payload.get("site_name") or payload.get("name")
            status = payload.get("status")
            claimed = False
            if isinstance(status, dict):
                claimed = str(status.get("status", "")).lower() == "claimed"
            else:
                claimed = str(status).lower() == "claimed"
            # Newer Maigret result objects expose `url_user` and a QueryStatus-like `status`.
            url_user = payload.get("url_user")
            if claimed and isinstance(url_user, str) and url_user.startswith(("http://", "https://")):
                key = url_user.casefold()
                if key not in seen:
                    seen.add(key)
                    findings.append(Finding(
                        entity_type=EntityType.URL, value=url_user,
                        attributes={"service": site_name, "username": request.seed.value, "account_status": "claimed"},
                        provenance=_prov(self.descriptor, source_url=url_user, confidence=0.88, raw=raw,
                                         notes=["Account claim is the upstream Maigret classification; anti-bot or provider errors are not treated as claims."]),
                    ))
                    if isinstance(site_name, str) and site_name:
                        findings.append(Finding(
                            entity_type=EntityType.SERVICE, value=site_name,
                            attributes={"username": request.seed.value, "account_status": "claimed"},
                            provenance=_prov(self.descriptor, source_url=url_user, confidence=0.86, raw=raw),
                        ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code,
                       [str(p) for p in files])


class HoleheAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="holehe", license="GPL-3.0-only", input_types=[SeedType.EMAIL], output_types=[EntityType.SERVICE],
        legal_notes=[
            "Checks public account-registration signals reported by the upstream modules; this wrapper performs no login or password-reset completion.",
            "Only run against an email address you are authorized to investigate; honor provider terms and rate limits."
        ],
        rate_limit="Single email per invocation; upstream modules enforce provider-specific timing.",
        invocation="CLI in dedicated Docker container", version_pin="1.61",
        upstream="https://github.com/megadose/holehe", network_required=True,
        docker_image="aletheia/holehe:1.61", output_schema={"registered_services": "object[]"}, health_check="holehe --help",
        requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["holehe", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        raw = stdout.encode()
        seen: set[str] = set()
        # Holehe's documented output exposes module/service names and whether the email exists.
        for line in stdout.splitlines():
            m = re.search(r"(?:\[\+\]|\[\x1b[^m]*\+[^m]*m\])\s*([^:]+)\s*[:=-]?\s*(.*)$", line)
            if not m:
                m = re.search(r"\[\+\]\s*([^:]+)", line)
            if not m:
                continue
            service = m.group(1).strip()
            if not service or service.casefold() in seen:
                continue
            seen.add(service.casefold())
            findings.append(Finding(
                entity_type=EntityType.SERVICE, value=service,
                attributes={"email": request.seed.value, "account_status": "registered_signal"},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.78, raw=raw,
                                 notes=["Parsed only positive/registered signals; negative, rate-limited, and error states are excluded."]),
            ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class H8mailAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="h8mail", license="BSD-3-Clause", input_types=[SeedType.EMAIL], output_types=[EntityType.BREACH, EntityType.SERVICE, EntityType.EMAIL],
        legal_notes=[
            "Wrapper uses h8mail's non-premium mode with default reconnaissance providers skipped and password output hidden.",
            "Local breach files, premium services, custom queries, chasing, and password/hash retrieval are not exposed by this adapter."
        ],
        rate_limit="Single target per invocation; provider-specific.", invocation="CLI in dedicated Docker container", version_pin="2.5.6",
        upstream="https://github.com/khast3x/h8mail", network_required=True,
        docker_image="aletheia/h8mail:2.5.6", output_schema={"breach_observations": "object[]"}, health_check="h8mail --help",
        requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["h8mail", "-t", request.seed.value, "-j", "/work/h8mail.json", "-sk", "--hide"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        path = workspace / "h8mail.json"
        raw = path.read_bytes() if path.exists() else stdout.encode()
        data_text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else stdout
        try:
            payload = json.loads(data_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
            items = payload["results"]
        elif isinstance(payload, dict):
            items = [payload]
        else:
            items = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            for service_key in ("service", "source", "method", "module", "name"):
                service = item.get(service_key)
                if isinstance(service, str) and service.strip():
                    key = ("service", service.casefold())
                    if key not in seen:
                        seen.add(key)
                        findings.append(Finding(
                            entity_type=EntityType.SERVICE, value=service.strip(),
                            attributes={"email": request.seed.value, "source_record": item},
                            provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.72, raw=raw,
                                             notes=["h8mail source record; passwords and local breach files are intentionally not exposed."]),
                        ))
            for breach_key in ("breach", "breach_name"):
                breach = item.get(breach_key)
                if isinstance(breach, str) and breach.strip():
                    key = ("breach", breach.casefold())
                    if key not in seen:
                        seen.add(key)
                        findings.append(Finding(
                            entity_type=EntityType.BREACH, value=breach.strip(),
                            attributes={"email": request.seed.value, "source_record": item},
                            provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.72, raw=raw),
                        ))
            if item.get("email") and isinstance(item["email"], str):
                findings.append(Finding(
                    entity_type=EntityType.EMAIL, value=item["email"],
                    attributes={"related_to_seed": request.seed.value},
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.65, raw=raw),
                ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code,
                       [str(path)] if path.exists() else [])


class HIBPAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="hibp", license="Service API terms", input_types=[SeedType.EMAIL], output_types=[EntityType.BREACH],
        legal_notes=[
            "Authenticated Have I Been Pwned account-breach API only; API key and identifying User-Agent are required.",
            "The adapter does not retrieve passwords. Use only with an authorized basis to query the address and respect HIBP subscription/acceptable-use terms."
        ],
        rate_limit="Provider/account quota controlled; adapter retries are bounded by orchestrator.",
        invocation="HTTPS API via dedicated Docker runner", version_pin="API v3",
        upstream="https://haveibeenpwned.com/API/V3", network_required=True,
        docker_image="aletheia/hibp:api-v3", output_schema={"breaches": "object[]"}, health_check="runner.py --health",
        requires_authorization_assertion=True, secret_env=["HIBP_API_KEY"],
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["runner.py", "email", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode()
        findings: list[Finding] = []
        try:
            payload = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("Name") or item.get("Title") or item.get("name")
                if not isinstance(name, str) or not name:
                    continue
                domain = item.get("Domain")
                source = f"https://haveibeenpwned.com/api/v3/breach/{quote(name)}"
                findings.append(Finding(
                    entity_type=EntityType.BREACH, value=name,
                    attributes={"email": request.seed.value, "domain": domain, "breach_record": item},
                    provenance=_prov(self.descriptor, source_url=source, confidence=0.98, raw=raw,
                                     notes=["Authenticated HIBP v3 breach-account response."]),
                ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class PhoneInfogaAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="phoneinfoga", license="GPL-3.0-only", input_types=[SeedType.PHONE], output_types=[EntityType.PHONE, EntityType.UNKNOWN, EntityType.SERVICE],
        legal_notes=[
            "Phone number scan is limited to the upstream scan command; no Google/Selenium browser workflow, login, or account access is enabled.",
            "Run only for an authorized number and honor external provider terms/rate limits."
        ],
        rate_limit="Single number per invocation; unconfigured upstream scanners do not run.",
        invocation="CLI in dedicated Docker container", version_pin="2.11.0",
        upstream="https://github.com/sundowndev/phoneinfoga", network_required=True,
        docker_image="aletheia/phoneinfoga:2.11.0", output_schema={"phone_observations": "object[]"}, health_check="phoneinfoga version",
        requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["phoneinfoga", "scan", "-n", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        raw = stdout.encode()
        phones = sorted(set(re.findall(r"\+\d{7,15}", stdout)))
        for phone in phones:
            findings.append(Finding(
                entity_type=EntityType.PHONE, value=phone,
                attributes={"seed_phone": request.seed.value},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.90, raw=raw),
            ))
        for line in stdout.splitlines():
            m = re.match(r"\s*(?:Carrier|Country|Line Type|Location|Service)\s*[:=-]\s*(.+?)\s*$", line, re.I)
            if m:
                label = line.split(":", 1)[0].strip().casefold()
                value = m.group(1).strip()
                findings.append(Finding(
                    entity_type=EntityType.SERVICE if label in {"carrier", "service"} else EntityType.UNKNOWN,
                    value=value,
                    attributes={"field": label, "seed_phone": request.seed.value},
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.76, raw=raw),
                ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class LibPhoneNumberAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="libphonenumber", license="Apache-2.0", input_types=[SeedType.PHONE], output_types=[EntityType.PHONE, EntityType.UNKNOWN],
        legal_notes=["Offline parsing/validation only. No network calls and no reverse-lookup or owner identification."],
        rate_limit="Local CPU only; no network.", invocation="Python runner in dedicated Docker container", version_pin="9.0.40",
        upstream="https://pypi.org/project/phonenumbers/", network_required=False,
        docker_image="aletheia/libphonenumber:9.0.40", output_schema={"phone": "object"}, health_check="python /opt/runner.py --health",
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["python", "/opt/runner.py", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode()
        findings: list[Finding] = []
        try:
            item = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            item = {}
        if isinstance(item, dict):
            e164 = item.get("e164")
            if isinstance(e164, str) and e164:
                findings.append(Finding(
                    entity_type=EntityType.PHONE, value=e164,
                    attributes={k: v for k, v in item.items() if k != "e164"},
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.99, raw=raw,
                                     notes=["Offline libphonenumber parse/validation; no ownership inference."]),
                ))
            for key in ("region", "carrier", "timezone", "number_type", "valid", "possible"):
                if key in item:
                    findings.append(Finding(
                        entity_type=EntityType.UNKNOWN, value=str(item[key]),
                        attributes={"field": key, "phone": e164 or request.seed.value},
                        provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.99, raw=raw),
                    ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)
