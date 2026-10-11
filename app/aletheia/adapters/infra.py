from __future__ import annotations

import ipaddress
import json
import re
from abc import ABC
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


def _prov(adapter: AdapterDescriptor, request: AdapterRunRequest, *, source_url: str | None,
          confidence: float, raw: bytes | None = None, notes: list[str] | None = None) -> Provenance:
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
        run_id=request.run_id,
        adapter=adapter,
        status="succeeded" if exit_code == 0 else "partial",
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        exit_code=exit_code,
        findings=findings,
        artifacts=artifacts or [],
        stderr_tail=stderr[-4000:],
        stdout_tail=stdout[-4000:],
    )


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


class DomainTextAdapter(Adapter, ABC):
    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self.descriptor.input_types

    def parse_lines(self, request: AdapterRunRequest, stdout: str, stderr: str, exit_code: int,
                    raw_source: bytes | None = None) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        seen: set[str] = set()
        for raw_line in stdout.splitlines():
            value = raw_line.strip().rstrip(".")
            if not value or value.startswith("[") or value.startswith("#"):
                continue
            if self._accept_value(value):
                key = value.lower()
                if key in seen:
                    continue
                seen.add(key)
                entity_type = EntityType.IP if _is_ip(value) else EntityType.HOST
                findings.append(Finding(
                    entity_type=entity_type,
                    value=value,
                    attributes={"seed_domain": request.seed.value},
                    provenance=_prov(
                        self.descriptor,
                        request,
                        source_url=self.descriptor.upstream,
                        confidence=0.80,
                        raw=raw_source if raw_source is not None else stdout.encode(),
                        notes=["Upstream CLI output did not expose an individual source URL; provenance URL is the upstream tool reference."],
                    ),
                ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)

    @staticmethod
    def _accept_value(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            pass
        return bool(re.fullmatch(r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", value))


class AmassAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="amass", license="Apache-2.0", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.IP],
        legal_notes=[
            "Adapter pins Amass passive enumeration only; active discovery is intentionally disabled.",
            "Honor the scope, data-source terms, rate limits, and applicable law.",
        ],
        rate_limit="Conservative single-domain passive run; container timeout bounds execution.",
        invocation="CLI in dedicated Docker container", version_pin="5.1.1",
        upstream="https://github.com/owasp-amass/amass", network_required=True,
        docker_image="aletheia/amass:5.1.1",
        output_schema={"hosts": "string[]", "ips": "string[]"},
        health_check="amass -version",
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["amass", "enum", "-passive", "-d", request.seed.value, "-o", "/work/amass.txt", "-timeout", "1"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        path = workspace / "amass.txt"
        data = path.read_bytes() if path.exists() else stdout.encode()
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else stdout
        result = self.parse_lines(request, text, stderr, exit_code, data)
        result.artifacts = [str(path)] if path.exists() else []
        return result


class SubfinderAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="subfinder", license="MIT", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST],
        legal_notes=["Passive subdomain enumeration only; honor passive-source licenses and provider rate limits."],
        rate_limit="Provider-specific; single-domain enumeration with upstream defaults.",
        invocation="CLI in dedicated Docker container", version_pin="2.17.0",
        upstream="https://github.com/projectdiscovery/subfinder", network_required=True,
        docker_image="aletheia/subfinder:2.17.0",
        output_schema={"hosts": "string[]"}, health_check="subfinder -version",
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["subfinder", "-d", request.seed.value, "-silent", "-o", "/work/subfinder.txt"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        path = workspace / "subfinder.txt"
        data = path.read_bytes() if path.exists() else stdout.encode()
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else stdout
        result = self.parse_lines(request, text, stderr, exit_code, data)
        result.artifacts = [str(path)] if path.exists() else []
        return result


class AssetfinderAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="assetfinder", license="MIT", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST],
        legal_notes=["Uses public/passive sources as implemented upstream. Honor source-specific terms and rate limits."],
        rate_limit="Upstream source-specific; one domain per invocation.",
        invocation="CLI in dedicated Docker container", version_pin="0.1.1",
        upstream="https://github.com/tomnomnom/assetfinder", network_required=True,
        docker_image="aletheia/assetfinder:0.1.1",
        output_schema={"hosts": "string[]"}, health_check="assetfinder --help",
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["assetfinder", "--subs-only", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        return self.parse_lines(request, stdout, stderr, exit_code)


class DnsxAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="dnsx", license="MIT", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.IP, EntityType.URL],
        legal_notes=[
            "Active DNS queries are target-adjacent. A caller must provide an explicit authorization assertion.",
            "This adapter resolves only the seed domain; it does not brute-force names.",
        ],
        rate_limit="Bounded query concurrency; single seed input.",
        invocation="CLI in dedicated Docker container", version_pin="1.3.1",
        upstream="https://github.com/projectdiscovery/dnsx", network_required=True,
        docker_image="aletheia/dnsx:1.3.1", output_schema={"dns_records": "object[]"},
        health_check="dnsx -health-check", requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        (workspace / "input.txt").write_text(request.seed.value + "\n", encoding="utf-8")
        return ["dnsx", "-l", "/work/input.txt", "-recon", "-json", "-silent", "-o", "/work/dnsx.jsonl"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        path = workspace / "dnsx.jsonl"
        raw = path.read_bytes() if path.exists() else stdout.encode()
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else stdout
        findings: list[Finding] = []
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            host = item.get("host")
            if isinstance(host, str):
                findings.append(Finding(entity_type=EntityType.HOST, value=host,
                                        attributes={"dns_record_source": item},
                                        provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                          confidence=0.92, raw=raw,
                                                          notes=["DNS result returned directly by dnsx."])))
            for field in ("a", "aaaa"):
                vals = item.get(field, [])
                if isinstance(vals, str):
                    vals = [vals]
                if isinstance(vals, list):
                    for value in vals:
                        if isinstance(value, str):
                            findings.append(Finding(entity_type=EntityType.IP, value=value,
                                                    attributes={"record_type": field.upper(), "host": host},
                                                    provenance=_prov(self.descriptor, request,
                                                                      source_url=self.descriptor.upstream, confidence=0.95, raw=raw)))
            for field in ("cname", "mx", "ns", "txt", "srv", "soa", "caa"):
                vals = item.get(field, [])
                if isinstance(vals, str):
                    vals = [vals]
                if isinstance(vals, list):
                    for value in vals:
                        if isinstance(value, str):
                            findings.append(Finding(entity_type=EntityType.HOST, value=value,
                                                    attributes={"record_type": field.upper(), "host": host},
                                                    provenance=_prov(self.descriptor, request,
                                                                      source_url=self.descriptor.upstream, confidence=0.90, raw=raw)))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code,
                       [str(path)] if path.exists() else [])


class MassdnsAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="massdns", license="GPL-3.0-only", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.IP],
        legal_notes=[
            "Performs DNS queries against configured recursive resolvers and therefore requires an explicit authorization assertion.",
            "The adapter resolves only the supplied seed domain and does not enable brute-force enumeration.",
            "Use a resolver list that permits your intended use; resolver abuse is prohibited.",
        ],
        rate_limit="Two-resolver conservative lookup; no bulk/brute-force mode.",
        invocation="CLI in dedicated GPL-3-only Docker container", version_pin="1.1.0",
        upstream="https://github.com/blechschmidt/massdns", network_required=True,
        docker_image="aletheia/massdns:1.1.0", output_schema={"dns_answers": "string[]"},
        health_check="massdns --help", requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        (workspace / "input.txt").write_text(request.seed.value + "\n", encoding="utf-8")
        return ["massdns", "-r", "/opt/resolvers.txt", "-t", "A", "-o", "S", "-q", "/work/input.txt"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        question = re.compile(r"^\s*([A-Za-z0-9.-]+\.)\s+IN\s+A\s*$")
        answer = re.compile(r"^\s*([A-Za-z0-9.-]+\.)\s+\d+\s+IN\s+A\s+([0-9.]+)\s*$")
        for line in stdout.splitlines():
            m = question.match(line)
            if m:
                host = m.group(1).rstrip(".")
                findings.append(Finding(entity_type=EntityType.HOST, value=host,
                                        provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                          confidence=0.93, raw=stdout.encode())))
                continue
            m = answer.match(line)
            if m:
                findings.append(Finding(entity_type=EntityType.IP, value=m.group(2),
                                        attributes={"host": m.group(1).rstrip(".")},
                                        provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                          confidence=0.96, raw=stdout.encode())))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class DnsreconAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="dnsrecon", license="GPL-2.0-only", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.IP, EntityType.UNKNOWN],
        legal_notes=[
            "Runs standard DNS and certificate-transparency enumeration only.",
            "Because standard DNS queries target DNS infrastructure, an authorization assertion is required by Aletheia policy.",
            "AXFR, brute-force, cache-snoop, range scans, and other broader modes are intentionally not invoked.",
        ],
        rate_limit="Single-domain standard + certificate-transparency run.",
        invocation="CLI in dedicated GPL container", version_pin="1.6.3",
        upstream="https://github.com/darkoperator/dnsrecon", network_required=True,
        docker_image="aletheia/dnsrecon:1.6.3", output_schema={"records": "object[]"},
        health_check="dnsrecon --help", requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["dnsrecon", "-d", request.seed.value, "-t", "std,crt", "-j", "/work/dnsrecon.json"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        path = workspace / "dnsrecon.json"
        raw = path.read_bytes() if path.exists() else b""
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace")) if raw else []
        except json.JSONDecodeError:
            payload = []
        findings: list[Finding] = []
        records = payload if isinstance(payload, list) else payload.get("records", []) if isinstance(payload, dict) else []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            name = rec.get("name") or rec.get("host") or rec.get("domain")
            address = rec.get("address")
            target = rec.get("target")
            rtype = str(rec.get("type", "UNKNOWN")).upper()
            if isinstance(name, str) and name:
                findings.append(Finding(entity_type=EntityType.HOST, value=name.rstrip("."),
                                        attributes={"record_type": rtype, "record": rec},
                                        provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                          confidence=0.91, raw=raw)))
            if isinstance(address, str) and address:
                findings.append(Finding(entity_type=EntityType.IP, value=address,
                                        attributes={"record_type": rtype, "host": name},
                                        provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                          confidence=0.95, raw=raw)))
            if isinstance(target, str) and target:
                findings.append(Finding(entity_type=EntityType.HOST, value=target.rstrip("."),
                                        attributes={"record_type": rtype, "source_host": name},
                                        provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                          confidence=0.88, raw=raw)))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code,
                       [str(path)] if path.exists() else [])


class FierceAdapter(DomainTextAdapter):
    descriptor = AdapterDescriptor(
        name="fierce", license="GPL-3.0-only", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.IP],
        legal_notes=[
            "Fierce performs DNS reconnaissance and can become active; Aletheia requires explicit authorization.",
            "This wrapper invokes only the domain mode without range scanning, custom DNS servers, wide mode, or explicit connect mode.",
        ],
        rate_limit="Single-domain invocation; upstream defaults; no wide/range scan.",
        invocation="CLI in dedicated GPL-3 container", version_pin="1.6.0",
        upstream="https://github.com/mschwager/fierce", network_required=True,
        docker_image="aletheia/fierce:1.6.0", output_schema={"hosts": "string[]", "ips": "string[]"},
        health_check="fierce --help", requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["fierce", "--domain", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        ips = set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", stdout))
        hosts = set(re.findall(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}\b", stdout))
        for value in sorted(hosts | ips):
            et = EntityType.IP if value in ips else EntityType.HOST
            findings.append(Finding(entity_type=et, value=value,
                                    provenance=_prov(self.descriptor, request, source_url=self.descriptor.upstream,
                                                      confidence=0.78, raw=stdout.encode(),
                                                      notes=["Fierce text output parsed heuristically; preserve raw artifact for review."])))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class ShodanAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="shodan", license="MIT (official Python library)", input_types=[SeedType.DOMAIN, SeedType.IP],
        output_types=[EntityType.HOST, EntityType.IP, EntityType.URL, EntityType.DOMAIN],
        legal_notes=[
            "Uses the licensed Shodan API/library; credentials must belong to an account authorized to use the API.",
            "This adapter performs read-only API lookups and never requests Shodan network scans.",
        ],
        rate_limit="Shodan plan/account limits; domain lookup consumes query credits according to API documentation.",
        invocation="Official Python Shodan library via dedicated Docker container", version_pin="1.31.0",
        upstream="https://developer.shodan.io/api", network_required=True,
        docker_image="aletheia/shodan:1.31.0", output_schema={"api_response": "object"},
        health_check="python /opt/runner.py --health", secret_env=["SHODAN_API_KEY"],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self.descriptor.input_types

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["python", "/opt/runner.py", request.seed.type.value, request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        path = workspace / "shodan.json"
        path.write_text(stdout, encoding="utf-8")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"raw": stdout}
        findings: list[Finding] = []
        if isinstance(payload, dict):
            if request.seed.type == SeedType.IP:
                findings.append(Finding(entity_type=EntityType.IP, value=request.seed.value,
                                        attributes={"shodan": payload},
                                        provenance=_prov(self.descriptor, request, source_url="https://api.shodan.io/shodan/host/" + request.seed.value,
                                                          confidence=1.0, raw=stdout.encode(), notes=["Seed lookup in Shodan API."]),
                                        source_kind="seed"))
                for host in payload.get("hostnames", []) or []:
                    if isinstance(host, str):
                        findings.append(Finding(entity_type=EntityType.HOST, value=host,
                                                attributes={"ip": request.seed.value},
                                                provenance=_prov(self.descriptor, request,
                                                                  source_url="https://api.shodan.io/shodan/host/" + request.seed.value,
                                                                  confidence=0.90, raw=stdout.encode())))
            else:
                findings.append(Finding(entity_type=EntityType.DOMAIN, value=request.seed.value,
                                        attributes={"shodan": payload},
                                        provenance=_prov(self.descriptor, request,
                                                          source_url="https://api.shodan.io/dns/domain/" + request.seed.value,
                                                          confidence=1.0, raw=stdout.encode()), source_kind="seed"))
                for rec in payload.get("data", []) or []:
                    if not isinstance(rec, dict):
                        continue
                    sub = rec.get("subdomain")
                    value = rec.get("value")
                    if isinstance(sub, str) and sub:
                        host = f"{sub}.{request.seed.value}".rstrip(".")
                        findings.append(Finding(entity_type=EntityType.HOST, value=host,
                                                attributes={"record_type": rec.get("type"), "record": rec},
                                                provenance=_prov(self.descriptor, request,
                                                                  source_url="https://api.shodan.io/dns/domain/" + request.seed.value,
                                                                  confidence=0.93, raw=stdout.encode())))
                    if isinstance(value, str) and value:
                        try:
                            ipaddress.ip_address(value)
                        except ValueError:
                            continue
                        findings.append(Finding(entity_type=EntityType.IP, value=value,
                                                attributes={"record_type": rec.get("type"), "domain": request.seed.value},
                                                provenance=_prov(self.descriptor, request,
                                                                  source_url="https://api.shodan.io/dns/domain/" + request.seed.value,
                                                                  confidence=0.95, raw=stdout.encode())))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code, [str(path)])


class CrtshAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="crt.sh", license="Service endpoint; no software license claimed", input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.DOMAIN],
        legal_notes=[
            "Uses the public certificate-transparency search endpoint at crt.sh.",
            "No account, authentication bypass, or target-side probing is performed.",
            "Respect the service's acceptable-use expectations and retrieve only the requested domain scope.",
        ],
        rate_limit="One certificate-transparency query per seed; caller/container timeout bounds retrieval.",
        invocation="HTTP API-compatible JSON endpoint in dedicated Docker container", version_pin="public endpoint (2026-10-08)",
        upstream="https://crt.sh/", network_required=True, docker_image="aletheia/crtsh:public-json",
        output_schema={"certificates": "object[]", "names": "string[]"}, health_check="python /opt/runner.py --health",
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.DOMAIN

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["python", "/opt/runner.py", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        path = workspace / "crtsh.json"
        path.write_text(stdout, encoding="utf-8")
        raw = stdout.encode()
        try:
            payload = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            payload = []
        findings: list[Finding] = []
        source_url = f"https://crt.sh/?q=%25.{request.seed.value}&output=json"
        seen: set[str] = set()
        rows = payload if isinstance(payload, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            names = row.get("name_value", "")
            if not isinstance(names, str):
                continue
            for name in names.splitlines():
                name = name.strip().lstrip("*.").rstrip(".")
                if not name or name.lower() in seen:
                    continue
                if not (name == request.seed.value or name.endswith("." + request.seed.value)):
                    continue
                seen.add(name.lower())
                findings.append(Finding(
                    entity_type=EntityType.DOMAIN if name == request.seed.value else EntityType.HOST,
                    value=name,
                    attributes={
                        "certificate_id": row.get("id"),
                        "issuer_name": row.get("issuer_name"),
                        "not_before": row.get("not_before"),
                        "not_after": row.get("not_after"),
                    },
                    provenance=_prov(self.descriptor, request, source_url=source_url,
                                      confidence=0.97, raw=raw,
                                      notes=["Name observed in a certificate-transparency record returned by crt.sh."]),
                ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code, [str(path)])
