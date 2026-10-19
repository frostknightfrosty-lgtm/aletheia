from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

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
        command = [
            request.seed.value,
            # The runtime mounts the container root read-only (core.execution);
            # the database autoupdate check would create ~/.maigret and crash
            # with "Read-only file system" (live run 39125383530). With the
            # check disabled maigret uses the database bundled in the image.
            "--no-autoupdate",
            "--no-progressbar",
            "--no-color",
            # Docker's embedded DNS is reached through the OS resolver more
            # reliably than through c-ares inside the internal network; upstream
            # recommends 'threaded' for "Could not contact DNS servers".
            "--dns-resolver", "threaded",
            "--json", "ndjson",
            "--folderoutput", "/work/results",
        ]
        # The egress proxy arrives via HTTP_PROXY/HTTPS_PROXY in the container
        # environment (core.execution); no --proxy flag on purpose. Passing
        # --proxy as well made maigret 0.6.6 double-hop: its
        # SimpleAiohttpChecker combines an aiohttp_socks ProxyConnector built
        # from --proxy with ClientSession(trust_env=True), so aiohttp tunnelled
        # through the connector *to the environment proxy address* and the
        # proxy dialled itself (live run 39135219248: 455 self-CONNECTs, 46% of
        # checks failed as "Proxy" errors). Both transports - aiohttp with
        # trust_env and curl_cffi via libcurl - honour the environment proxies
        # (verified against docker/egress_proxy/proxy.py in local repros).
        return command

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
        return [request.seed.value]

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


_ALLOWED_ACCOUNT_URL_HOSTS = {
    "github.com", "www.github.com",
    "flickr.com", "www.flickr.com",
    "gravatar.com", "www.gravatar.com",
}


def _public_account_url(value: str) -> bool:
    """Accept only https profile URLs on hosts the pinned modules print."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname:
        return False
    if parts.username or parts.password:
        return False
    if parts.hostname not in _ALLOWED_ACCOUNT_URL_HOSTS:
        return False
    return bool(parts.path and parts.path != "/")


class ZehefAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="zehef", license="GPL-3.0-only", input_types=[SeedType.EMAIL],
        output_types=[EntityType.SERVICE, EntityType.URL],
        legal_notes=[
            "Checks public account-registration signals reported by the pinned upstream modules (17 services); this wrapper completes no login, no password reset, and no CAPTCHA or anti-bot challenge.",
            "The upstream paste scraper (Google search scraping), the HudsonRock stealer-log module, and the random email-combination generator are never invoked; see docker/zehef/RATE_LIMITS.md.",
            "Only run against an email address you are authorized to investigate; honor provider terms and rate limits."
        ],
        rate_limit="One email per container invocation; each of the 17 account checks is requested once, sequentially, with no retries.",
        invocation="CLI in dedicated Docker container",
        version_pin="2.2.1 (commit 5b0c120efe846eae944dfea9410f925ca3036103)",
        upstream="https://github.com/N0rz3/Zehef", network_required=True,
        docker_image="aletheia/zehef:v1",
        output_schema={"registered_services": "object[]", "account_urls": "string[]"},
        health_check="--health", requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return [request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        notes: list[str] = []
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        modules = payload.get("modules") if isinstance(payload, dict) else None
        if isinstance(modules, list):
            for module in modules:
                if not isinstance(module, dict):
                    continue
                service = module.get("service")
                status = module.get("status")
                if not isinstance(service, str) or not service:
                    continue
                if status == "error":
                    notes.append(f"{service}: error ({module.get('error') or 'unknown'})")
                    continue
                if status != "registered":
                    continue
                details = module.get("details") if isinstance(module.get("details"), dict) else {}
                raw = json.dumps(module, ensure_ascii=False, sort_keys=True).encode()
                attributes = {"email": request.seed.value, "account_status": "registered_signal"}
                for key, attribute in (
                    ("username", "username"), ("name", "name"),
                    ("created_on", "account_created"), ("updated_on", "account_updated"),
                ):
                    value = details.get(key)
                    if isinstance(value, str) and value.strip():
                        attributes[attribute] = value.strip()
                findings.append(Finding(
                    entity_type=EntityType.SERVICE, value=service, attributes=attributes,
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.78, raw=raw,
                                     notes=["Parsed only positive/registered signals; negative and error states are excluded."]),
                ))
                account = details.get("account")
                if isinstance(account, str) and _public_account_url(account.strip()):
                    url = account.strip()
                    url_attributes = {"service": service, "email": request.seed.value}
                    if "username" in attributes:
                        url_attributes["username"] = attributes["username"]
                    findings.append(Finding(
                        entity_type=EntityType.URL, value=url, attributes=url_attributes,
                        provenance=_prov(self.descriptor, source_url=url, confidence=0.85, raw=raw,
                                         notes=["Public account URL printed by the pinned upstream module."]),
                    ))
        if notes:
            stderr = ((stderr + "\n") if stderr else "") + "; ".join(notes)
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class VenomAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="venom", license="MIT",
        input_types=[SeedType.EMAIL, SeedType.USERNAME, SeedType.DOMAIN],
        output_types=[
            EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.EMAIL, EntityType.DOMAIN,
            EntityType.IP, EntityType.BREACH, EntityType.UNKNOWN,
        ],
        legal_notes=[
            "Runs only the reviewed keyless module set of the pinned checkout (5 email / 12 username / 13 domain modules, one query each). Keyed services, borrowed third-party keys, the Dehashed scrape, raw-socket certificate/RBL checks, the login-form auth probes (Holehe/Google), the DuckDuckGo scrape, the AI agent, and the web UI are never imported; see docker/venom/RATE_LIMITS.md.",
            "Two documented fail-closed deviations from upstream: rotating browser user agents are replaced with a fixed honest Aletheia user agent, and upstream's hardcoded ssl=False is overridden by a session that forces certificate verification.",
            "Every finding is a public-source observation: profile existence or public profile fields, RDAP registry rows, certificate-transparency rows, paste-index hits for the exact target string (paste bodies are never fetched), and provider threat/risk metadata. None of it confirms identity by itself.",
            "Only run against a target you are authorized to investigate; honor provider terms and rate limits."
        ],
        rate_limit="One target per container invocation; per-run request bounds: email <= 5, username <= 54 (36-platform sweep + GitHub profile/org/commit reads + 8 single calls), domain <= 16; one query per module per run and no added retries.",
        invocation="CLI in dedicated Docker container",
        version_pin="7.0 (commit 6fa3a483abc9cb0a1d96567e33b2919be59522c6)",
        upstream="https://github.com/ghostport-sudo/VENOM", network_required=True,
        docker_image="aletheia/venom:v1",
        output_schema={
            "social_accounts": "object[]", "account_urls": "string[]", "emails": "string[]",
            "domains": "string[]", "ips": "string[]", "paste_index_hits": "object[]",
            "module_assessments": "object[]",
        },
        health_check="--health", requires_authorization_assertion=True,
    )

    _SEED_TYPES = {SeedType.EMAIL: "email", SeedType.USERNAME: "username", SeedType.DOMAIN: "domain"}
    _ERROR_STATUS_PREFIXES = ("Protected", "Timeout", "Connection", "Failed", "Error")
    _ASSESSMENTS = {
        "whois": "domain registry (RDAP) summary",
        "wayback": "Wayback Machine snapshot summary",
        "otx_domain": "AlienVault OTX domain reputation",
        "otx_ip": "AlienVault OTX address reputation",
        "pulsedive": "Pulsedive indicator assessment",
        "proxycheck": "ProxyCheck proxy/VPN/Tor assessment",
    }

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        if not self.supports(request.seed.type):
            raise ValueError(f"Unsupported seed type for venom: {request.seed.type}")
        return ["--type", self._SEED_TYPES[request.seed.type], request.seed.value]

    # -- parse helpers -----------------------------------------------------------------

    def _module_error(self, result: object) -> dict | None:
        """Describe an upstream error-shaped module result, else None."""
        if not isinstance(result, dict):
            return None
        status = result.get("Status")
        if isinstance(status, str) and status.startswith(self._ERROR_STATUS_PREFIXES):
            detail = result.get("details") or result.get("body") or ""
            kind = "blocked" if status.startswith("Protected") else "error"
            return {"kind": kind, "detail": f"{status}: {detail}"[:300] if detail else status}
        error = result.get("error")
        if isinstance(error, str) and error:
            detail = result.get("details")
            detail = detail if isinstance(detail, str) and detail else ""
            return {"kind": "error", "detail": f"{error}: {detail}"[:300] if detail else error}
        return None

    @staticmethod
    def _trim_value(value: object, depth: int = 0) -> object:
        if isinstance(value, str):
            return value[:300]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, list):
            return [VenomAdapter._trim_value(item, depth + 1) for item in value[:10]]
        if isinstance(value, dict) and depth < 3:
            return {
                str(key)[:60]: VenomAdapter._trim_value(item, depth + 1)
                for key, item in list(value.items())[:20]
            }
        return str(value)[:300]

    @staticmethod
    def _looks_like_domain(value: object) -> bool:
        return (
            isinstance(value, str) and 3 <= len(value) <= 253
            and "." in value and " " not in value and "@" not in value
        )

    def _marker(self, findings: list[Finding], raw: bytes, suffix: str, attributes: dict, note: str,
                confidence: float = 1.0) -> None:
        findings.append(Finding(
            entity_type=EntityType.UNKNOWN, value=f"venom:{suffix}",
            attributes=attributes,
            provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=confidence,
                             raw=raw, notes=[note]),
        ))

    def _parse_social(self, seed, result, findings, raw, notes):
        found = result.get("found") if isinstance(result.get("found"), list) else []
        not_found = result.get("not_found") if isinstance(result.get("not_found"), list) else []
        errors = result.get("errors") if isinstance(result.get("errors"), list) else []
        notes.append(f"social sweep: {len(found)} found / {len(not_found)} not found / {len(errors)} inconclusive")
        for entry in found[:60]:
            if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
                continue
            platform, url = entry
            if not (isinstance(platform, str) and platform):
                continue
            if not (isinstance(url, str) and url.startswith("https://")):
                continue
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT, value=f"{platform}:{seed}",
                attributes={"source": "venom-social", "platform": platform, "username": seed, "profile_url": url},
                provenance=_prov(self.descriptor, source_url=url, confidence=0.7, raw=raw,
                                 notes=["Platform-appropriate existence check by the pinned module (status code, API JSON, or pinned body markers); a found platform is a profile-existence signal, not identity confirmation."]),
            ))

    def _parse_github_user(self, seed, result, findings, raw, notes):
        if not result.get("found"):
            return
        profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
        url = profile.get("url")
        attributes: dict = {"source": "venom-github", "platform": "github", "username": seed}
        for key, attribute in (
            ("name", "name"), ("bio", "bio"), ("company", "company"),
            ("location", "location"), ("blog", "blog"), ("created", "account_created"),
        ):
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                attributes[attribute] = value.strip()[:200]
        for key, attribute in (("followers", "followers"), ("repos", "public_repos")):
            value = profile.get(key)
            if isinstance(value, (int, float)):
                attributes[attribute] = value
        if isinstance(url, str) and url.startswith("https://"):
            attributes["profile_url"] = url
        repos = result.get("repos") if isinstance(result.get("repos"), list) else []
        repo_names = [repo.get("name") for repo in repos[:8] if isinstance(repo, dict) and isinstance(repo.get("name"), str)]
        if repo_names:
            attributes["recent_repos"] = repo_names
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"github:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) and url.startswith("https://") else self.descriptor.upstream,
                             confidence=0.85, raw=raw,
                             notes=["Public GitHub profile returned by the pinned module."]),
        ))
        email = profile.get("email")
        if isinstance(email, str) and "@" in email and len(email) <= 254 and "noreply" not in email:
            findings.append(Finding(
                entity_type=EntityType.EMAIL, value=email,
                attributes={"source": "venom-github-profile", "username": seed,
                            "note": "public profile email field"},
                provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) else self.descriptor.upstream,
                                 confidence=0.75, raw=raw,
                                 notes=["Email published on the account's public GitHub profile."]),
            ))
        gists = result.get("gists") if isinstance(result.get("gists"), list) else []
        for gist in gists[:5]:
            if not isinstance(gist, dict):
                continue
            gist_url = gist.get("url")
            if not (isinstance(gist_url, str) and gist_url.startswith("https://gist.github.com/")):
                continue
            gist_attributes = {"source": "venom-github", "username": seed}
            if isinstance(gist.get("description"), str) and gist["description"]:
                gist_attributes["description"] = gist["description"][:120]
            if isinstance(gist.get("created"), str) and gist["created"]:
                gist_attributes["created"] = gist["created"]
            findings.append(Finding(
                entity_type=EntityType.URL, value=gist_url, attributes=gist_attributes,
                provenance=_prov(self.descriptor, source_url=gist_url, confidence=0.75, raw=raw),
            ))

    def _parse_github_orgs(self, seed, result, findings, raw, notes):
        organizations = result.get("organizations") if isinstance(result.get("organizations"), list) else []
        for org in organizations[:20]:
            if not isinstance(org, dict):
                continue
            login = org.get("login")
            if not (isinstance(login, str) and login):
                continue
            attributes = {"source": "venom-github-orgs", "kind": "organization_membership",
                          "username": seed, "login": login}
            url = org.get("url")
            if isinstance(url, str) and url.startswith("https://"):
                attributes["organization_url"] = url
            description = org.get("description")
            if isinstance(description, str) and description:
                attributes["description"] = description[:120]
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT, value=f"github:{login}", attributes=attributes,
                provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) and url.startswith("https://") else self.descriptor.upstream,
                                 confidence=0.7, raw=raw,
                                 notes=["Organization listed as a public membership of the account; the organization is an entity of its own."]),
            ))

    def _parse_github_commit_emails(self, seed, result, findings, raw, notes):
        emails = result.get("emails") if isinstance(result.get("emails"), list) else []
        for email in emails[:20]:
            if not (isinstance(email, str) and "@" in email and 3 <= len(email) <= 254):
                continue
            findings.append(Finding(
                entity_type=EntityType.EMAIL, value=email,
                attributes={"source": "venom-github-commits", "username": seed,
                            "note": "author email from public commit metadata (noreply addresses excluded upstream)"},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.7, raw=raw,
                                 notes=["Commit author email harvested by the pinned module from public commit history."]),
            ))

    def _parse_github_commits(self, seed, result, findings, raw, notes):
        commits = result.get("commits") if isinstance(result.get("commits"), list) else []
        for commit in commits[:5]:
            if not isinstance(commit, dict):
                continue
            url = commit.get("url")
            if not (isinstance(url, str) and url.startswith("https://github.com/")):
                continue
            attributes = {"source": "venom-github-commit-search", "email": seed}
            if isinstance(commit.get("repo"), str) and commit["repo"]:
                attributes["repo"] = commit["repo"]
            if isinstance(commit.get("date"), str) and commit["date"]:
                attributes["date"] = commit["date"]
            if isinstance(commit.get("message"), str) and commit["message"]:
                attributes["message_excerpt"] = commit["message"][:120]
            findings.append(Finding(
                entity_type=EntityType.URL, value=url, attributes=attributes,
                provenance=_prov(self.descriptor, source_url=url, confidence=0.65, raw=raw,
                                 notes=["Commit matched the exact seed email string in GitHub's public commit search."]),
            ))

    def _parse_psbdmp(self, seed, result, findings, raw, notes):
        pastes = result.get("pastes") if isinstance(result.get("pastes"), list) else []
        count = result.get("count")
        for paste in pastes[:10]:
            if not isinstance(paste, dict):
                continue
            url = paste.get("url")
            if not (isinstance(url, str) and url.startswith("https://pastebin.com/")):
                continue
            paste_id = paste.get("id") if isinstance(paste.get("id"), str) and paste.get("id") else url.rsplit("/", 1)[-1]
            findings.append(Finding(
                entity_type=EntityType.BREACH, value=f"PSBDMP:{paste_id}",
                attributes={"source": "psbdmp", "record_type": "paste_index_hit", "target": seed,
                            "url": url, "paste_time": str(paste.get("time") or "")[:40], "index_count": count},
                provenance=_prov(self.descriptor, source_url=url, confidence=0.75, raw=raw,
                                 notes=["Paste-index hit for the exact target string; the paste body was not downloaded or opened."]),
            ))

    def _parse_otx_email(self, seed, result, findings, raw, notes):
        results = result.get("results") if isinstance(result.get("results"), list) else []
        pulses = []
        for pulse in results[:5]:
            if not isinstance(pulse, dict):
                continue
            pulses.append({
                "name": str(pulse.get("name") or "")[:80],
                "author": str(pulse.get("author") or "")[:60],
                "date": str(pulse.get("date") or "")[:20],
            })
        self._marker(findings, raw, "otx_email", {
            "source": "venom-otx-email", "target": seed,
            "pulse_count": result.get("count"), "pulses": pulses,
        }, "OTX pulse search for the exact address; presence in security-research pulses is context, not an incident claim.",
            confidence=0.7)

    def _parse_emailrep(self, seed, result, findings, raw, notes):
        if result.get("_rate_limited"):
            self._marker(findings, raw, "emailrep:rate_limited",
                         {"source": "venom-emailrep", "email": seed},
                         "EmailRep public tier asked the client to slow down (HTTP 429); the request is not retried.",
                         confidence=0.95)
            return
        if result.get("_bad_key"):
            self._marker(findings, raw, "emailrep:bad_key",
                         {"source": "venom-emailrep", "email": seed},
                         "EmailRep rejected the request; no key is sent by this adapter, so this is unexpected and reported verbatim.",
                         confidence=0.95)
            return
        attributes: dict = {"source": "venom-emailrep", "email": seed}
        for key in ("reputation", "suspicious", "references"):
            if key in result and isinstance(result.get(key), (str, bool, int, float)):
                attributes[key] = result[key]
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        for key in (
            "blacklisted", "malicious_activity", "credentials_leaked", "data_breach",
            "first_seen", "last_seen", "disposable", "free_provider", "spoofable",
            "spf_strict", "dmarc_enforced", "valid_mx",
        ):
            if key in details and isinstance(details.get(key), (str, bool, int, float, type(None))):
                attributes[key] = details[key]
        profiles = details.get("profiles") if isinstance(details.get("profiles"), list) else []
        for profile in profiles[:10]:
            if not isinstance(profile, dict):
                continue
            domain = profile.get("domain")
            username = profile.get("username")
            if not (isinstance(domain, str) and domain and isinstance(username, str) and username):
                continue
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT, value=f"{domain}:{username}",
                attributes={"source": "venom-emailrep", "kind": "profile_reference", "email": seed},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.65, raw=raw,
                                 notes=["Profile reference reported by EmailRep; not independently confirmed by this adapter."]),
            ))
        self._marker(findings, raw, "emailrep", attributes,
                     "EmailRep reputation assessment for the exact address.", confidence=0.7)

    def _parse_crtsh_email(self, seed, result, findings, raw, notes):
        domains = result.get("domains") if isinstance(result.get("domains"), list) else []
        for item in domains[:60]:
            if not isinstance(item, dict):
                continue
            name = item.get("domain")
            attributes = {"source": "venom-crtsh-email", "issued": str(item.get("issued") or "")[:20],
                          "issuer": str(item.get("issuer") or "")[:120]}
            if isinstance(name, str) and "@" in name and len(name) <= 254:
                findings.append(Finding(
                    entity_type=EntityType.EMAIL, value=name, attributes=attributes,
                    provenance=_prov(self.descriptor, source_url=f"https://crt.sh/?q={quote(seed)}", confidence=0.7, raw=raw,
                                     notes=["Certificate-transparency record carrying the seed string as an email name."]),
                ))
            elif self._looks_like_domain(name):
                findings.append(Finding(
                    entity_type=EntityType.DOMAIN, value=name.lower(), attributes=attributes,
                    provenance=_prov(self.descriptor, source_url=f"https://crt.sh/?q={quote(seed)}", confidence=0.7, raw=raw,
                                     notes=["Certificate-transparency record carrying the seed string in a name entry."]),
                ))

    def _parse_dns(self, seed, result, findings, raw, notes):
        a_records = result.get("a") if isinstance(result.get("a"), list) else []
        for record in a_records[:5]:
            try:
                ipaddress.ip_address(str(record))
            except ValueError:
                continue
            findings.append(Finding(
                entity_type=EntityType.IP, value=str(record),
                attributes={"record": "A", "domain": seed, "source": "venom-dns"},
                provenance=_prov(self.descriptor, source_url="https://dns.google/resolve", confidence=0.8, raw=raw,
                                 notes=["A record observed through Google DNS-over-HTTPS."]),
            ))
        self._marker(findings, raw, "dns", {
            "source": "venom-dns", "domain": seed, "provider": result.get("provider"),
            "a": self._trim_value(a_records), "mx": self._trim_value(result.get("mx")),
            "ns": self._trim_value(result.get("ns")), "txt": self._trim_value(result.get("txt")),
        }, "DNS record summary (A/MX/NS/TXT) from Google DNS-over-HTTPS.", confidence=0.8)

    def _parse_ip(self, seed, result, findings, raw, notes):
        address = result.get("ip")
        address_ok = False
        if isinstance(address, str):
            try:
                ipaddress.ip_address(address)
                address_ok = True
            except ValueError:
                address_ok = False
        if address_ok:
            geo = result.get("geo") if isinstance(result.get("geo"), dict) else {}
            attributes = {"source": "venom-ip", "domain": seed}
            hostname = result.get("hostname")
            if isinstance(hostname, str) and hostname:
                attributes["hostname"] = hostname[:253]
            for key in ("org", "city", "region", "country", "timezone"):
                value = geo.get(key)
                if isinstance(value, str) and value:
                    attributes[key] = value[:120]
            findings.append(Finding(
                entity_type=EntityType.IP, value=address, attributes=attributes,
                provenance=_prov(self.descriptor, source_url=f"https://ipinfo.io/{address}/json", confidence=0.8, raw=raw,
                                 notes=["Resolved via the container resolver; geolocation from ipinfo.io."]),
            ))
        hostname = result.get("hostname")
        if self._looks_like_domain(hostname) and hostname != seed:
            findings.append(Finding(
                entity_type=EntityType.DOMAIN, value=hostname.lower(),
                attributes={"source": "venom-ip", "record": "PTR", "ip": address if address_ok else ""},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.7, raw=raw,
                                 notes=["Reverse-DNS name observed by the container resolver."]),
            ))

    def _parse_crt_subs(self, seed, result, findings, raw, notes):
        subdomains = result.get("subdomains") if isinstance(result.get("subdomains"), list) else []
        for item in subdomains[:100]:
            if not isinstance(item, dict):
                continue
            name = item.get("subdomain")
            if not self._looks_like_domain(name):
                continue
            findings.append(Finding(
                entity_type=EntityType.DOMAIN, value=name.lower(),
                attributes={"source": "venom-crtsh-subdomains", "issued": str(item.get("issued") or "")[:20],
                            "issuer": str(item.get("issuer") or "")[:120]},
                provenance=_prov(self.descriptor, source_url=f"https://crt.sh/?q=%25.{quote(seed)}", confidence=0.8, raw=raw,
                                 notes=["Certificate-transparency subdomain row (wildcards stripped upstream)."]),
            ))

    def _parse_urlscan(self, seed, result, findings, raw, notes):
        results = result.get("results") if isinstance(result.get("results"), list) else []
        for hit in results[:10]:
            if not isinstance(hit, dict):
                continue
            url = hit.get("url")
            scan_id = hit.get("scan_id") if isinstance(hit.get("scan_id"), str) else ""
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                attributes = {"source": "venom-urlscan", "domain": seed}
                for key in ("ip", "country", "server", "date"):
                    value = hit.get(key)
                    if isinstance(value, str) and value:
                        attributes[key] = value[:120]
                for key in ("score", "malicious"):
                    if isinstance(hit.get(key), (int, float, bool)):
                        attributes[key] = hit[key]
                tags = hit.get("tags")
                if isinstance(tags, list):
                    attributes["tags"] = [str(tag)[:40] for tag in tags[:5]]
                if scan_id:
                    attributes["scan_id"] = scan_id
                findings.append(Finding(
                    entity_type=EntityType.URL, value=url, attributes=attributes,
                    provenance=_prov(self.descriptor, source_url=f"https://urlscan.io/result/{scan_id}/" if scan_id else self.descriptor.upstream,
                                     confidence=0.75, raw=raw,
                                     notes=["Public URLScan search hit; the scan was not submitted by this adapter."]),
                ))
            ip_value = hit.get("ip")
            if isinstance(ip_value, str) and ip_value:
                try:
                    ipaddress.ip_address(ip_value)
                except ValueError:
                    continue
                findings.append(Finding(
                    entity_type=EntityType.IP, value=ip_value,
                    attributes={"source": "venom-urlscan", "scan_id": scan_id, "domain": seed},
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.7, raw=raw),
                ))

    def _parse_ht_dns(self, seed, result, findings, raw, notes):
        results = result.get("results") if isinstance(result.get("results"), list) else []
        for item in results[:100]:
            if not isinstance(item, dict):
                continue
            hostname = item.get("hostname")
            if not self._looks_like_domain(hostname):
                continue
            attributes = {"source": "venom-hackertarget-passive-dns", "domain": seed}
            ip_value = item.get("ip")
            if isinstance(ip_value, str) and ip_value:
                attributes["ip"] = ip_value[:64]
            findings.append(Finding(
                entity_type=EntityType.DOMAIN, value=hostname.lower(), attributes=attributes,
                provenance=_prov(self.descriptor, source_url="https://api.hackertarget.com/hostsearch/", confidence=0.75, raw=raw,
                                 notes=["HackerTarget passive-DNS row (keyless tier)."]),
            ))

    def _parse_ht_rev(self, seed, result, findings, raw, notes):
        results = result.get("results") if isinstance(result.get("results"), list) else []
        for hostname in results[:100]:
            if not self._looks_like_domain(hostname):
                continue
            findings.append(Finding(
                entity_type=EntityType.DOMAIN, value=hostname.lower(),
                attributes={"source": "venom-hackertarget-reverse-ip", "ip": seed},
                provenance=_prov(self.descriptor, source_url="https://api.hackertarget.com/reverseiplookup/", confidence=0.7, raw=raw,
                                 notes=["HackerTarget reverse-IP row for the resolved address (keyless tier)."]),
            ))

    def _parse_internetdb(self, seed, result, findings, raw, notes):
        hostnames = result.get("hostnames") if isinstance(result.get("hostnames"), list) else []
        for hostname in hostnames[:5]:
            if not self._looks_like_domain(hostname):
                continue
            findings.append(Finding(
                entity_type=EntityType.DOMAIN, value=hostname.lower(),
                attributes={"source": "venom-internetdb", "ip": seed},
                provenance=_prov(self.descriptor, source_url=f"https://internetdb.shodan.io/{quote(seed)}", confidence=0.7, raw=raw,
                                 notes=["Hostname reported by Shodan InternetDB for the resolved address."]),
            ))
        self._marker(findings, raw, "internetdb", {
            "source": "venom-internetdb", "ip": seed,
            "ports": self._trim_value(result.get("ports")), "vulns": self._trim_value(result.get("vulns")),
            "tags": self._trim_value(result.get("tags")), "cpes": self._trim_value(result.get("cpes")),
        }, "Shodan InternetDB exposure summary for the resolved address (keyless endpoint).", confidence=0.7)

    def _parse_gitlab(self, seed, result, findings, raw, notes):
        if not result.get("exists"):
            return
        profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
        url = profile.get("web_url")
        attributes = {"source": "venom-gitlab", "platform": "gitlab", "username": seed}
        for key, attribute in (("name", "name"), ("state", "state")):
            value = profile.get(key)
            if isinstance(value, str) and value:
                attributes[attribute] = value[:120]
        if isinstance(url, str) and url.startswith("https://"):
            attributes["profile_url"] = url
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"gitlab:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) and url.startswith("https://") else self.descriptor.upstream,
                             confidence=0.8, raw=raw,
                             notes=["Public GitLab users endpoint returned a profile for the handle."]),
        ))

    def _parse_npm(self, seed, result, findings, raw, notes):
        if not result.get("exists"):
            return
        profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
        attributes = {"source": "venom-npm", "platform": "npm", "username": seed}
        name = profile.get("name")
        if isinstance(name, str) and name:
            attributes["name"] = name[:120]
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"npm:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=f"https://www.npmjs.com/~{quote(seed)}", confidence=0.8, raw=raw,
                             notes=["Public npm registry user document for the handle."]),
        ))
        email = profile.get("email")
        if isinstance(email, str) and "@" in email and len(email) <= 254:
            findings.append(Finding(
                entity_type=EntityType.EMAIL, value=email,
                attributes={"source": "venom-npm", "username": seed},
                provenance=_prov(self.descriptor, source_url=f"https://www.npmjs.com/~{quote(seed)}", confidence=0.7, raw=raw,
                                 notes=["Email present in the public npm registry user document."]),
            ))

    def _parse_pypi(self, seed, result, findings, raw, notes):
        if not result.get("exists"):
            return
        url = result.get("url")
        attributes = {"source": "venom-pypi", "platform": "pypi", "username": seed}
        packages = result.get("packages")
        if isinstance(packages, int):
            attributes["package_count"] = packages
        if isinstance(url, str) and url.startswith("https://"):
            attributes["profile_url"] = url
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"pypi:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) else self.descriptor.upstream,
                             confidence=0.8, raw=raw,
                             notes=["Public PyPI user profile page; only the package count is derived."]),
        ))

    def _parse_keybase(self, seed, result, findings, raw, notes):
        if not result.get("exists"):
            return
        attributes = {"source": "venom-keybase", "platform": "keybase", "username": seed}
        username = result.get("username")
        if isinstance(username, str) and username:
            attributes["keybase_username"] = username
        for key, attribute in (("full_name", "full_name"), ("bio", "bio"), ("location", "location")):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                attributes[attribute] = value.strip()[:200]
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"keybase:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=f"https://keybase.io/{quote(seed)}", confidence=0.85, raw=raw,
                             notes=["Public Keybase lookup for the handle."]),
        ))
        seen: set[tuple[str, str]] = set()
        proofs = result.get("proofs") if isinstance(result.get("proofs"), list) else []
        for proof in proofs[:20]:
            if not isinstance(proof, dict):
                continue
            service = str(proof.get("service") or "").strip().lower()
            name = str(proof.get("name") or "").strip()
            if not service or not name:
                continue
            key = (service, name.casefold())
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT, value=f"{service}:{name}",
                attributes={"source": "venom-keybase-proof", "kind": "keybase_proof", "keybase_username": seed},
                provenance=_prov(self.descriptor, source_url=f"https://keybase.io/{quote(seed)}", confidence=0.88, raw=raw,
                                 notes=["Cryptographically verified Keybase proof linking the handle to the named account."]),
            ))
        for service in ("twitter", "github", "reddit", "hackernews"):
            name = result.get(service)
            if isinstance(name, str) and name.strip():
                key = (service, name.strip().casefold())
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(
                    entity_type=EntityType.SOCIAL_ACCOUNT, value=f"{service}:{name.strip()}",
                    attributes={"source": "venom-keybase", "kind": "profile_link", "keybase_username": seed},
                    provenance=_prov(self.descriptor, source_url=f"https://keybase.io/{quote(seed)}", confidence=0.8, raw=raw,
                                     notes=["Account name from the public Keybase profile."]),
                ))

    def _parse_twitter(self, seed, result, findings, raw, notes):
        if not result.get("confirmed"):
            return
        attributes = {"source": "venom-twitter-oembed", "platform": "twitter", "username": seed}
        author_name = result.get("author_name")
        if isinstance(author_name, str) and author_name.strip():
            attributes["display_name"] = author_name.strip()[:120]
        author_url = result.get("author_url")
        if isinstance(author_url, str) and author_url.startswith("https://"):
            attributes["profile_url"] = author_url
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"twitter:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=author_url if isinstance(author_url, str) and author_url.startswith("https://") else self.descriptor.upstream,
                             confidence=0.75, raw=raw,
                             notes=["X's own oEmbed endpoint resolved author metadata for the handle."]),
        ))

    def _parse_telegram(self, seed, result, findings, raw, notes):
        if not result.get("exists"):
            return
        attributes = {"source": "venom-telegram", "platform": "telegram", "username": seed}
        url = result.get("url")
        if isinstance(url, str) and url.startswith("https://"):
            attributes["profile_url"] = url
        display = result.get("display_name")
        if isinstance(display, str) and display.strip():
            attributes["display_name"] = display.strip()[:120]
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"telegram:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) else self.descriptor.upstream,
                             confidence=0.7, raw=raw,
                             notes=["Public t.me preview page rendered the handle; display name from og:title."]),
        ))

    def _parse_steam(self, seed, result, findings, raw, notes):
        if not result.get("exists"):
            return
        attributes = {"source": "venom-steam", "platform": "steam", "username": seed}
        for key, attribute in (
            ("steam_id", "steam_id"), ("display", "display_name"), ("state", "state"),
            ("location", "location"), ("joined", "member_since"), ("summary", "summary"),
        ):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                attributes[attribute] = value.strip()[:200]
        url = result.get("url")
        if isinstance(url, str) and url.startswith("https://"):
            attributes["profile_url"] = url
        findings.append(Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT, value=f"steam:{seed}", attributes=attributes,
            provenance=_prov(self.descriptor, source_url=url if isinstance(url, str) and url.startswith("https://") else self.descriptor.upstream,
                             confidence=0.8, raw=raw,
                             notes=["Public Steam community XML profile for the handle."]),
        ))

    def _parse_assessment(self, key, seed, result, findings, raw, notes):
        if not result:
            self._marker(findings, raw, f"{key}:empty",
                         {"source": f"venom-{key}", "target": seed, "status": "no_data"},
                         "Module returned no data (empty or error-suppressed upstream normalization).", confidence=0.9)
            return
        attributes = {"source": f"venom-{key}", "assessment": self._ASSESSMENTS[key], "target": seed}
        for name, value in list(result.items())[:20]:
            attributes[str(name)[:60]] = self._trim_value(value)
        self._marker(findings, raw, key, attributes,
                     "Aggregated provider assessment reproduced from the pinned module's normalization; treat as context, not a verdict.",
                     confidence=0.7)

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        notes: list[str] = []
        raw = stdout.encode()
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        modules = payload.get("modules") if isinstance(payload.get("modules"), dict) else {}
        seed = request.seed.value

        run_status = payload.get("status")
        if isinstance(run_status, str) and run_status in {"invalid_target", "blocked", "error"}:
            error = payload.get("error")
            self._marker(findings, raw, f"run:{run_status}", {
                "source": "venom", "status": run_status,
                "target_type": str(payload.get("target_type") or ""),
                "error": error[:300] if isinstance(error, str) else "",
            }, "Driver-level status marker; nothing was retried or fabricated.")

        handlers = {
            "social": self._parse_social,
            "github_user": self._parse_github_user,
            "github_orgs": self._parse_github_orgs,
            "github_commit_emails": self._parse_github_commit_emails,
            "github_commits": self._parse_github_commits,
            "psbdmp": self._parse_psbdmp,
            "psbdmp_u": self._parse_psbdmp,
            "otx_email": self._parse_otx_email,
            "emailrep": self._parse_emailrep,
            "crtsh_email": self._parse_crtsh_email,
            "dns": self._parse_dns,
            "ip": self._parse_ip,
            "crt_subs": self._parse_crt_subs,
            "urlscan": self._parse_urlscan,
            "ht_dns": self._parse_ht_dns,
            "ht_rev": self._parse_ht_rev,
            "internetdb": self._parse_internetdb,
            "gitlab": self._parse_gitlab,
            "npm": self._parse_npm,
            "pypi": self._parse_pypi,
            "keybase": self._parse_keybase,
            "twitter": self._parse_twitter,
            "telegram": self._parse_telegram,
            "steam": self._parse_steam,
        }
        for key in sorted(modules):
            result = modules[key]
            if isinstance(result, dict) and result.get("status") == "skipped":
                reason = str(result.get("reason") or "driver skipped the module")
                notes.append(f"{key}: skipped ({reason})")
                self._marker(findings, raw, f"{key}:skipped",
                             {"source": "venom", "module": key, "status": "skipped", "reason": reason[:200]},
                             "Driver skip marker; the module was not queried.")
                continue
            error = self._module_error(result)
            if error:
                notes.append(f"{key}: {error['detail']}")
                self._marker(findings, raw, f"{key}:error", {
                    "source": "venom", "module": key, "status": error["kind"], "detail": error["detail"],
                }, "Module error marker so an empty report is never indistinguishable from a real search.")
                continue
            if key in self._ASSESSMENTS:
                self._parse_assessment(key, seed, result, findings, raw, notes)
                continue
            handler = handlers.get(key)
            if handler is None:
                findings.append(Finding(
                    entity_type=EntityType.UNKNOWN, value=f"venom:{key}",
                    attributes={"source": "venom", "module": key, "result": self._trim_value(result)},
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.5, raw=raw,
                                     notes=["Unmapped module result reproduced for transparency."]),
                ))
                continue
            handler(seed, result, findings, raw, notes)

        if notes:
            stderr = ((stderr + "\n") if stderr else "") + "; ".join(notes)
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
        return ["-t", request.seed.value, "-j", "/work/h8mail.json", "-sk", "--hide"]

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
        return ["email", request.seed.value]

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


class XposedOrNotAdapter(IdentityAdapter):
    descriptor = AdapterDescriptor(
        name="xposedornot", license="XposedOrNot API terms",
        input_types=[SeedType.EMAIL], output_types=[EntityType.BREACH],
        legal_notes=[
            "Uses only the free community check-email endpoint with detailed results disabled; parses breach names only and never retrieves passwords or breach records.",
            "Query only an email address you are authorized to investigate. This is a personal, low-volume API: obey its published limits and do not bulk collect or redistribute breach data.",
        ],
        rate_limit="One request per email; 2 requests/second, 25/hour, and 100/day per IP according to the upstream community API limits.",
        invocation="HTTPS API via dedicated Docker runner", version_pin="API v1",
        upstream="https://xposedornot.com/api_doc", network_required=True,
        docker_image="aletheia/xposedornot:api-v1",
        output_schema={"breach_names": "string[]"}, health_check="--health",
        requires_authorization_assertion=True,
    )

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["email", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        raw = stdout.encode()
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}

        response_email = payload.get("email") if isinstance(payload, dict) else None
        email_matches = (
            isinstance(response_email, str)
            and response_email.casefold() == request.seed.value.casefold()
        )
        if email_matches and "Error" not in payload and payload.get("status", "success") == "success":
            groups = payload.get("breaches", [])
            if isinstance(groups, list):
                names = [name for group in groups for name in (group if isinstance(group, list) else [group])
                         if isinstance(name, str) and name.strip()]
                source = "https://api.xposedornot.com/v1/check-email/" + quote(request.seed.value, safe="")
                for name in dict.fromkeys(names):
                    findings.append(Finding(
                        entity_type=EntityType.BREACH, value=name,
                        attributes={"email": request.seed.value},
                        provenance=_prov(
                            self.descriptor, source_url=source, confidence=0.90, raw=raw,
                            notes=["Non-detailed XposedOrNot response; breach name only, not underlying breach data or credentials."],
                        ),
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
        return ["scan", "-n", request.seed.value]

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
        return [request.seed.value]

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
