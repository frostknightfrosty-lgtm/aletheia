from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    EntityType,
    Finding,
    Provenance,
    Seed,
    SeedType,
)


class IPIntelligenceFinding(Finding):
    """Normalized IP intelligence finding from any sub-source."""

    def __init__(
        self,
        *,
        ip: str,
        source: str,
        geolocation: dict[str, Any] | None = None,
        asn: dict[str, Any] | None = None,
        reputation: dict[str, Any] | None = None,
        reverse_dns: str | None = None,
        open_ports: list[int] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes = {"source": source}
        if geolocation:
            attributes["geolocation"] = geolocation
        if asn:
            attributes["asn"] = asn
        if reputation:
            attributes["reputation"] = reputation
        if reverse_dns:
            attributes["reverse_dns"] = reverse_dns
        if open_ports:
            attributes["open_ports"] = open_ports
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="ip_intelligence",
                source_url=f"sub-source:{source}",
                confidence=0.75,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        super().__init__(
            entity_type=EntityType.IP,
            value=ip,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )


def _ip_intel_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="ip_intelligence",
        source_url=f"sub-source:{source}",
        confidence=0.75,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _extract_geolocation(data: dict, source: str) -> dict[str, Any] | None:
    """Extract geolocation fields from various source formats."""
    geo = {}
    # IPinfo
    if source == "ipinfo":
        for field in ("country", "region", "city", "postal", "timezone"):
            if data.get(field):
                geo[field] = data[field]
        loc = data.get("loc")
        if isinstance(loc, str):
            parts = loc.split(",")
            if len(parts) == 2:
                try:
                    geo["latitude"] = float(parts[0])
                    geo["longitude"] = float(parts[1])
                except ValueError:
                    pass
    # IP-API
    elif source == "ip-api":
        for field in ("country", "countryCode", "region", "regionName", "city", "zip", "lat", "lon", "timezone"):
            if data.get(field) is not None:
                geo[field] = data[field]
    # ipapi.co
    elif source == "ipapi-co":
        for field in ("country_name", "country_code", "region", "region_code", "city", "postal_code", "latitude", "longitude", "timezone"):
            if data.get(field) is not None:
                geo[field] = data[field]
    # IPGeolocation.io
    elif source == "ipgeolocation":
        for field in ("country_name", "country_code2", "state_prov", "city", "zipcode", "latitude", "longitude", "timezone"):
            if data.get(field) is not None:
                geo[field] = data[field]
    # Netlas
    elif source == "netlas":
        if isinstance(data.get("data"), list) and data["data"]:
            item = data["data"][0]
            for field in ("country", "city", "coordinates"):
                if item.get(field):
                    geo[field] = item[field]
    # FullHunt
    elif source == "fullhunt":
        if isinstance(data.get("geolocation"), dict):
            geo = data["geolocation"]
    return geo or None


def _extract_asn(data: dict, source: str) -> dict[str, Any] | None:
    """Extract ASN fields from various source formats."""
    asn = {}
    # IPinfo
    if source == "ipinfo":
        org = data.get("org")
        if isinstance(org, str) and org.startswith("AS"):
            parts = org.split(" ", 1)
            if parts[0].startswith("AS"):
                try:
                    asn["number"] = int(parts[0][2:])
                except ValueError:
                    pass
                if len(parts) > 1:
                    asn["name"] = parts[1]
        elif data.get("asn"):
            asn_data = data["asn"]
            if isinstance(asn_data, dict):
                asn.update(asn_data)
    # IP-API
    elif source == "ip-api":
        if data.get("as"):
            as_str = data["as"]
            parts = as_str.split(" ", 1)
            if parts[0].startswith("AS"):
                try:
                    asn["number"] = int(parts[0][2:])
                except ValueError:
                    pass
                if len(parts) > 1:
                    asn["name"] = parts[1]
    # ipapi.co
    elif source == "ipapi-co":
        if data.get("asn"):
            try:
                asn["number"] = int(data["asn"])
            except ValueError:
                pass
        if data.get("org"):
            asn["name"] = data["org"]
    # IPGeolocation.io
    elif source == "ipgeolocation":
        if data.get("asn"):
            try:
                asn["number"] = int(data["asn"])
            except ValueError:
                pass
        if data.get("isp"):
            asn["name"] = data["isp"]
    # HackerTarget
    elif source == "hackertarget":
        if isinstance(data.get("hostsearch"), str):
            lines = data["hostsearch"].strip().split("\n")
            for line in lines:
                if "," in line:
                    parts = line.split(",")
                    if len(parts) >= 2 and parts[1].startswith("AS"):
                        try:
                            asn["number"] = int(parts[1][2:])
                            asn["name"] = parts[0]
                        except ValueError:
                            pass
    # ipinfo.app ASN
    elif source == "ipinfo-app-asn":
        announced = data.get("announcedBy")
        if isinstance(announced, dict):
            if announced.get("number"):
                asn["number"] = announced["number"]
            if announced.get("description"):
                asn["name"] = announced["description"]
    return asn or None


def _extract_reputation(data: dict, source: str) -> dict[str, Any] | None:
    """Extract reputation fields from various source formats."""
    rep = {}
    # AbuseIPDB
    if source == "abuseipdb":
        if isinstance(data.get("data"), dict):
            d = data["data"]
            if d.get("abuseConfidenceScore") is not None:
                rep["abuse_score"] = d["abuseConfidenceScore"]
            if d.get("isWhitelisted") is not None:
                rep["whitelisted"] = d["isWhitelisted"]
            if d.get("totalReports") is not None:
                rep["total_reports"] = d["totalReports"]
            if d.get("countryCode"):
                rep["country_code"] = d["countryCode"]
    # GreyNoise
    elif source == "greynoise":
        if data.get("noise") is not None:
            rep["noise"] = data["noise"]
        if data.get("riot") is not None:
            rep["riot"] = data["riot"]
        if data.get("classification"):
            rep["classification"] = data["classification"]
        if data.get("name"):
            rep["actor"] = data["name"]
        if data.get("link"):
            rep["link"] = data["link"]
    # VirusTotal
    elif source == "virustotal":
        if isinstance(data.get("data"), dict):
            attrs = data["data"].get("attributes", {})
            if attrs.get("last_analysis_stats"):
                rep["last_analysis_stats"] = attrs["last_analysis_stats"]
            if attrs.get("reputation") is not None:
                rep["reputation"] = attrs["reputation"]
            if attrs.get("asn"):
                rep["asn"] = attrs["asn"]
            if attrs.get("as_owner"):
                rep["as_owner"] = attrs["as_owner"]
    # URLhaus
    elif source == "urlhaus":
        if data.get("query_status") == "ok":
            rep["urlhaus_status"] = "malicious"
            if isinstance(data.get("urls"), list):
                rep["url_count"] = len(data["urls"])
    # ThreatFox
    elif source == "threatfox":
        if isinstance(data.get("data"), list):
            rep["ioc_count"] = len(data["data"])
            for ioc in data["data"][:5]:
                if ioc.get("malware"):
                    rep.setdefault("malware_families", []).append(ioc["malware"])
                if ioc.get("threat_type"):
                    rep.setdefault("threat_types", []).append(ioc["threat_type"])
    # MalwareBazaar
    elif source == "malwarebazaar":
        if data.get("query_status") == "ok" and isinstance(data.get("data"), list):
            rep["sample_count"] = len(data["data"])
            for sample in data["data"][:3]:
                if sample.get("signature"):
                    rep.setdefault("signatures", []).append(sample["signature"])
    # PhishTank
    elif source == "phishtank":
        if isinstance(data.get("results"), dict):
            r = data["results"]
            if r.get("in_database"):
                rep["in_database"] = True
                if r.get("verified"):
                    rep["verified"] = True
                if r.get("valid") is not None:
                    rep["valid"] = r["valid"]
    # Netlas
    elif source == "netlas":
        if isinstance(data.get("data"), list):
            rep["netlas_host_count"] = len(data["data"])
    # FullHunt
    elif source == "fullhunt":
        if data.get("vulnerabilities"):
            rep["vulnerability_count"] = len(data["vulnerabilities"])
        if data.get("technologies"):
            rep["technologies"] = [t.get("name") for t in data["technologies"][:10] if t.get("name")]
    return rep or None


def _extract_reverse_dns(data: dict, source: str) -> str | None:
    if source == "ipinfo":
        return data.get("hostname")
    if source == "ip-api":
        return data.get("reverse")
    if source == "ipapi-co":
        return data.get("hostname")
    if source == "ipgeolocation":
        return data.get("hostname")
    return None


def _extract_open_ports(data: dict, source: str) -> list[int] | None:
    if source == "fullhunt" and isinstance(data.get("open_ports"), list):
        ports = []
        for p in data["open_ports"]:
            if isinstance(p, dict) and p.get("port"):
                ports.append(p["port"])
            elif isinstance(p, int):
                ports.append(p)
        return ports or None
    return None


class IPIntelligenceAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="ip_intelligence",
        license="Composite adapter; sub-sources have individual licenses",
        input_types=[SeedType.IP],
        output_types=[EntityType.IP],
        legal_notes=[
            "Composite adapter querying 15 IP intelligence sub-sources via their public APIs.",
            "Sub-sources requiring free API keys (IPinfo, IPGeolocation, AbuseIPDB, GreyNoise, VirusTotal, URLhaus, ThreatFox, MalwareBazaar, Netlas, FullHunt) will be skipped if the corresponding environment variable is not set. Skip reasons are recorded in output.",
            "Tier 1 sub-sources (IP-API, ipapi.co, HackerTarget, ipinfo.app ASN) run without keys.",
            "All sub-sources are public REST APIs; no unauthorized access, CAPTCHA bypass, or credential use against third-party accounts.",
            "Rate limits are per-sub-source; the adapter queries each once per run. Respect provider quotas and 429 responses.",
        ],
        rate_limit="One query per sub-source per run; 15 sub-sources total. Individual limits documented in docker/ip_intelligence/RATE_LIMITS.md",
        invocation="HTTPS APIs via dedicated Docker runner (aletheia/ip-intelligence:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/ip_intelligence",
        network_required=True,
        docker_image="aletheia/ip-intelligence:v1",
        output_schema={"finding_type": "IPIntelligenceFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "IPINFO_TOKEN",
            "IPGEOLOCATION_KEY",
            "ABUSEIPDB_KEY",
            "GREYNOISE_KEY",
            "VIRUSTOTAL_KEY",
            "URLHAUS_AUTH_KEY",
            "THREATFOX_AUTH_KEY",
            "MALWAREBAZAAR_AUTH_KEY",
            "NETLAS_KEY",
            "FULLHUNT_KEY",
            "IPAPI_CO_KEY",
            "PHISHTANK_APP_KEY",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.IP

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        return [request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Any, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8")
        findings: list[Finding] = []

        if exit_code != 0:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="failed",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=exit_code,
                findings=[],
                stderr_tail=stderr[-4000:],
                stdout_tail=stdout[-4000:],
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="partial",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=1,
                findings=[],
                stderr_tail="Runner output was not valid JSON",
                stdout_tail=stdout[-4000:],
            )

        target_ip = payload.get("target", "").split("/")[0]
        sources = payload.get("sources", [])

        for src in sources:
            source_name = src.get("source", "unknown")
            skipped = src.get("skipped", False)
            skip_reason = src.get("skip_reason")
            data = src.get("data")
            http_status = src.get("http_status", 0)
            error = src.get("error")
            raw_hash = src.get("raw_hash")
            timestamp = src.get("timestamp")

            if skipped:
                findings.append(IPIntelligenceFinding(
                    ip=target_ip,
                    source=source_name,
                    geolocation=None,
                    asn=None,
                    reputation={"skipped": True, "reason": skip_reason},
                    reverse_dns=None,
                    open_ports=None,
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_ip_intel_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(IPIntelligenceFinding(
                    ip=target_ip,
                    source=source_name,
                    geolocation=None,
                    asn=None,
                    reputation={"error": error, "http_status": http_status},
                    reverse_dns=None,
                    open_ports=None,
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_ip_intel_provenance(source_name, json.dumps({"error": error}).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            geolocation = self._extract_geolocation(data, source_name)
            asn = self._extract_asn(data, source_name)
            reputation = self._extract_reputation(data, source_name)
            reverse_dns = self._extract_reverse_dns(data, source_name)
            open_ports = self._extract_open_ports(data, source_name)

            finding = IPIntelligenceFinding(
                ip=target_ip,
                source=source_name,
                geolocation=geolocation,
                asn=asn,
                reputation=reputation,
                reverse_dns=reverse_dns,
                open_ports=open_ports,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_ip_intel_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
            )
            findings.append(finding)

        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )

    def _extract_geolocation(self, data: dict, source: str) -> dict[str, Any] | None:
        """Extract geolocation fields from various source formats."""
        geo = {}
        if source == "ipinfo":
            for field in ("country", "region", "city", "postal", "timezone"):
                if data.get(field):
                    geo[field] = data[field]
            loc = data.get("loc")
            if isinstance(loc, str):
                parts = loc.split(",")
                if len(parts) == 2:
                    try:
                        geo["latitude"] = float(parts[0])
                        geo["longitude"] = float(parts[1])
                    except ValueError:
                        pass
        elif source == "ip-api":
            for field in ("country", "countryCode", "region", "regionName", "city", "zip", "lat", "lon", "timezone"):
                if data.get(field) is not None:
                    geo[field] = data[field]
        elif source == "ipapi-co":
            for field in ("country_name", "country_code", "region", "region_code", "city", "postal_code", "latitude", "longitude", "timezone"):
                if data.get(field) is not None:
                    geo[field] = data[field]
        elif source == "ipgeolocation":
            for field in ("country_name", "country_code2", "state_prov", "city", "zipcode", "latitude", "longitude", "timezone"):
                if data.get(field) is not None:
                    geo[field] = data[field]
        elif source == "netlas":
            if isinstance(data.get("data"), list) and data["data"]:
                item = data["data"][0]
                for field in ("country", "city", "coordinates"):
                    if item.get(field):
                        geo[field] = item[field]
        elif source == "fullhunt":
            if isinstance(data.get("geolocation"), dict):
                geo = data["geolocation"]
        return geo or None

    def _extract_asn(self, data: dict, source: str) -> dict[str, Any] | None:
        """Extract ASN fields from various source formats."""
        asn = {}
        if source == "ipinfo":
            org = data.get("org")
            if isinstance(org, str) and org.startswith("AS"):
                parts = org.split(" ", 1)
                if parts[0].startswith("AS"):
                    try:
                        asn["number"] = int(parts[0][2:])
                    except ValueError:
                        pass
                    if len(parts) > 1:
                        asn["name"] = parts[1]
            elif data.get("asn"):
                asn_data = data["asn"]
                if isinstance(asn_data, dict):
                    asn.update(asn_data)
        elif source == "ip-api":
            if data.get("as"):
                as_str = data["as"]
                parts = as_str.split(" ", 1)
                if parts[0].startswith("AS"):
                    try:
                        asn["number"] = int(parts[0][2:])
                    except ValueError:
                        pass
                    if len(parts) > 1:
                        asn["name"] = parts[1]
        elif source == "ipapi-co":
            if data.get("asn"):
                try:
                    asn["number"] = int(data["asn"])
                except ValueError:
                    pass
            if data.get("org"):
                asn["name"] = data["org"]
        elif source == "ipgeolocation":
            if data.get("asn"):
                try:
                    asn["number"] = int(data["asn"])
                except ValueError:
                    pass
            if data.get("isp"):
                asn["name"] = data["isp"]
        elif source == "hackertarget":
            if isinstance(data.get("hostsearch"), str):
                lines = data["hostsearch"].strip().split("\n")
                for line in lines:
                    if "," in line:
                        parts = line.split(",")
                        if len(parts) >= 2 and parts[1].startswith("AS"):
                            try:
                                asn["number"] = int(parts[1][2:])
                                asn["name"] = parts[0]
                            except ValueError:
                                pass
        elif source == "ipinfo-app-asn":
            announced = data.get("announcedBy")
            if isinstance(announced, dict):
                if announced.get("number"):
                    asn["number"] = announced["number"]
                if announced.get("description"):
                    asn["name"] = announced["description"]
        return asn or None

    def _extract_reputation(self, data: dict, source: str) -> dict[str, Any] | None:
        """Extract reputation fields from various source formats."""
        rep = {}
        if source == "abuseipdb":
            if isinstance(data.get("data"), dict):
                d = data["data"]
                if d.get("abuseConfidenceScore") is not None:
                    rep["abuse_score"] = d["abuseConfidenceScore"]
                if d.get("isWhitelisted") is not None:
                    rep["whitelisted"] = d["isWhitelisted"]
                if d.get("totalReports") is not None:
                    rep["total_reports"] = d["totalReports"]
                if d.get("countryCode"):
                    rep["country_code"] = d["countryCode"]
        elif source == "greynoise":
            if data.get("noise") is not None:
                rep["noise"] = data["noise"]
            if data.get("riot") is not None:
                rep["riot"] = data["riot"]
            if data.get("classification"):
                rep["classification"] = data["classification"]
            if data.get("name"):
                rep["actor"] = data["name"]
            if data.get("link"):
                rep["link"] = data["link"]
        elif source == "virustotal":
            if isinstance(data.get("data"), dict):
                attrs = data["data"].get("attributes", {})
                if attrs.get("last_analysis_stats"):
                    rep["last_analysis_stats"] = attrs["last_analysis_stats"]
                if attrs.get("reputation") is not None:
                    rep["reputation"] = attrs["reputation"]
                if attrs.get("asn"):
                    rep["asn"] = attrs["asn"]
                if attrs.get("as_owner"):
                    rep["as_owner"] = attrs["as_owner"]
        elif source == "urlhaus":
            if data.get("query_status") == "ok":
                rep["urlhaus_status"] = "malicious"
                if isinstance(data.get("urls"), list):
                    rep["url_count"] = len(data["urls"])
        elif source == "threatfox":
            if isinstance(data.get("data"), list):
                rep["ioc_count"] = len(data["data"])
                for ioc in data["data"][:5]:
                    if ioc.get("malware"):
                        rep.setdefault("malware_families", []).append(ioc["malware"])
                    if ioc.get("threat_type"):
                        rep.setdefault("threat_types", []).append(ioc["threat_type"])
        elif source == "malwarebazaar":
            if data.get("query_status") == "ok" and isinstance(data.get("data"), list):
                rep["sample_count"] = len(data["data"])
                for sample in data["data"][:3]:
                    if sample.get("signature"):
                        rep.setdefault("signatures", []).append(sample["signature"])
        elif source == "phishtank":
            if isinstance(data.get("results"), dict):
                r = data["results"]
                if r.get("in_database"):
                    rep["in_database"] = True
                    if r.get("verified"):
                        rep["verified"] = True
                    if r.get("valid") is not None:
                        rep["valid"] = r["valid"]
        elif source == "netlas":
            if isinstance(data.get("data"), list):
                rep["netlas_host_count"] = len(data["data"])
        elif source == "fullhunt":
            if data.get("vulnerabilities"):
                rep["vulnerability_count"] = len(data["vulnerabilities"])
            if data.get("technologies"):
                rep["technologies"] = [t.get("name") for t in data["technologies"][:10] if t.get("name")]
        return rep or None

    def _extract_reverse_dns(self, data: dict, source: str) -> str | None:
        if source == "ipinfo":
            return data.get("hostname")
        if source == "ip-api":
            return data.get("reverse")
        if source == "ipapi-co":
            return data.get("hostname")
        if source == "ipgeolocation":
            return data.get("hostname")
        return None

    def _extract_open_ports(self, data: dict, source: str) -> list[int] | None:
        if source == "fullhunt" and isinstance(data.get("open_ports"), list):
            ports = []
            for p in data["open_ports"]:
                if isinstance(p, dict) and p.get("port"):
                    ports.append(p["port"])
                elif isinstance(p, int):
                    ports.append(p)
            return ports or None
        return None


# Auto-register if this module is loaded
def __getattr__(name: str):
    if name == "IPIntelligenceAdapter":
        return IPIntelligenceAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")