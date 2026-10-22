from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType, Finding,
    Provenance, SeedType,
)


def _prov(adapter: AdapterDescriptor, *, source_url: str | None, confidence: float, raw: bytes, notes: list[str] | None = None) -> Provenance:
    import hashlib
    return Provenance(
        tool=adapter.name,
        source_url=source_url,
        observed_at=datetime.now(timezone.utc),
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes or [],
    )


def _result(request: AdapterRunRequest, adapter: AdapterDescriptor, started: datetime, findings: list[Finding], stdout: str, stderr: str, exit_code: int, artifacts: list[str] | None = None) -> AdapterRunResult:
    status = "succeeded" if exit_code == 0 else "partial"
    return AdapterRunResult(
        run_id=request.run_id,
        adapter=adapter,
        status=status,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        exit_code=exit_code,
        findings=findings,
        artifacts=artifacts or [],
        stderr_tail=stderr[-4000:],
        stdout_tail=stdout[-4000:],
    )


def _credential_skip(adapter: AdapterDescriptor, stderr: str) -> Finding:
    """Record a runner-declared missing-credentials skip (exit code 5 convention).

    Run 39120709419 showed why this must be a first-class record: without it a
    key-gated adapter that never queried anything is indistinguishable in the
    report from one that searched and found nothing. The reason is copied from
    the runner's own stderr, never inferred.
    """
    reason = next((line.strip() for line in stderr.splitlines() if line.strip()),
                  "runner reported missing credentials (exit code 5)")
    return Finding(
        entity_type=EntityType.UNKNOWN,
        value=f"{adapter.name}:skipped",
        attributes={"skipped": True, "source": adapter.name, "reason": reason},
        provenance=_prov(adapter, source_url=adapter.upstream, confidence=1.0,
                         raw=reason.encode(), notes=[f"Skipped: {reason}"]),
    )


def _stage_image(request: AdapterRunRequest, workspace: Path) -> Path:
    src = Path(request.seed.value).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"image evidence file not found: {src}")
    suffix = src.suffix.lower() if src.suffix else ".bin"
    workspace.mkdir(parents=True, exist_ok=True)
    dest = workspace / f"input{suffix}"
    shutil.copy2(src, dest)
    return dest


class Phase5Adapter(Adapter):
    pass


class InstaloaderAdapter(Phase5Adapter):
    descriptor = AdapterDescriptor(
        name="instaloader", license="MIT", input_types=[SeedType.USERNAME], output_types=[EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.UNKNOWN],
        legal_notes=[
            "Unauthenticated public-profile metadata only. Login, cookies, private profiles, saved media, stories, and account actions are not exposed.",
            "Honor Instagram/Instaloader terms, robots/policy, rate limits, and applicable law.",
        ],
        rate_limit="One public profile lookup per invocation; provider throttling may apply.",
        invocation="Python module in dedicated Docker container", version_pin="4.15.3",
        upstream="https://github.com/instaloader/instaloader", network_required=True,
        docker_image="aletheia/instaloader:4.15.3", output_schema={"profile": "object"}, health_check="runner.py --health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.USERNAME

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return [request.seed.value]

    def parse(self, request, workspace, stdout, stderr, exit_code):
        started = datetime.now(timezone.utc); raw = stdout.encode(); findings = []
        try: data = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: data = {}
        if isinstance(data, dict):
            username = data.get("username")
            profile_url = data.get("profile_url")
            attrs = {k: v for k, v in data.items() if k not in {"username", "profile_url"}}
            if isinstance(profile_url, str):
                findings.append(Finding(entity_type=EntityType.URL, value=profile_url, attributes={"platform": "instagram", "username": username}, provenance=_prov(self.descriptor, source_url=profile_url, confidence=0.93, raw=raw)))
                findings.append(Finding(entity_type=EntityType.SOCIAL_ACCOUNT, value=profile_url, attributes={"platform": "instagram", **attrs}, provenance=_prov(self.descriptor, source_url=profile_url, confidence=0.92, raw=raw, notes=["Public-profile metadata only; no authentication was used."])))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class RedditAPIAdapter(Phase5Adapter):
    descriptor = AdapterDescriptor(
        name="reddit-api", license="Reddit API terms", input_types=[SeedType.USERNAME], output_types=[EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.UNKNOWN],
        legal_notes=["Official Reddit OAuth API only; public user overview metadata is requested. No login as the target user and no private data.", "Use only with credentials and an authorized investigative basis; respect Reddit API terms and quotas."],
        rate_limit="Provider quota; one profile lookup per invocation.", invocation="HTTPS API via dedicated Docker runner", version_pin="Data API v1",
        upstream="https://www.reddit.com/dev/api/", network_required=True, docker_image="aletheia/reddit-api:v1",
        output_schema={"user": "object"}, health_check="runner.py --health", requires_authorization_assertion=True,
        secret_env=["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
    )
    def supports(self, seed_type): return seed_type == SeedType.USERNAME
    def build_command(self, request, workspace): return [request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); findings=[]
        try: data=json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: data={}
        if isinstance(data, dict):
            user=data.get("data", data)
            name=(user.get("name") or user.get("username")) if isinstance(user, dict) else None
            # Run 39120709419: with no payload this used to fall back to the seed
            # and emit a profile URL backed by the SHA-256 of the empty string.
            # Claiming an account requires the payload to carry the username.
            if isinstance(name, str) and name:
                url=f"https://www.reddit.com/user/{name}/"
                findings.append(Finding(entity_type=EntityType.URL,value=url,attributes={"platform":"reddit","username":name},provenance=_prov(self.descriptor,source_url=url,confidence=0.96,raw=raw)))
                findings.append(Finding(entity_type=EntityType.SOCIAL_ACCOUNT,value=url,attributes={k:v for k,v in user.items() if k not in {"password","access_token"}},provenance=_prov(self.descriptor,source_url="https://www.reddit.com/dev/api/",confidence=0.95,raw=raw)))
        if exit_code == 5 and not stdout.strip():
            findings.append(_credential_skip(self.descriptor, stderr))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class YouTubeAPIAdapter(Phase5Adapter):
    descriptor=AdapterDescriptor(
        name="youtube-api", license="Google YouTube API terms", input_types=[SeedType.USERNAME], output_types=[EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.UNKNOWN],
        legal_notes=["Official YouTube Data API v3 only. Read-only channel discovery via API key; no channel-account modification.", "API key and quota are operator-controlled; honor YouTube API Terms of Service and quotas."],
        rate_limit="Google API quota; one or two requests per username depending on handle resolution.", invocation="HTTPS API via dedicated Docker runner", version_pin="Data API v3",
        upstream="https://developers.google.com/youtube/v3", network_required=True, docker_image="aletheia/youtube-api:v3", output_schema={"channels":"object[]"}, health_check="runner.py --health",
        requires_authorization_assertion=True, secret_env=["YOUTUBE_API_KEY"],
    )
    def supports(self, seed_type): return seed_type == SeedType.USERNAME
    def build_command(self, request, workspace): return [request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); findings=[]
        try: data=json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: data={}
        items=data.get("items",[]) if isinstance(data,dict) else []
        for item in items:
            if not isinstance(item,dict): continue
            cid=item.get("id")
            snip=item.get("snippet",{}) or {}; stats=item.get("statistics",{}) or {}
            if not cid: continue
            url=f"https://www.youtube.com/channel/{cid}"
            thumbs = snip.get("thumbnails") if isinstance(snip.get("thumbnails"), dict) else {}
            avatar = None
            for size in ("high", "medium", "default"):
                thumb = thumbs.get(size) if isinstance(thumbs.get(size), dict) else {}
                if isinstance(thumb.get("url"), str):
                    avatar = thumb["url"]
                    break
            attrs={"platform":"youtube","title":snip.get("title"),"description":snip.get("description"),"custom_url":snip.get("customUrl"),"country":snip.get("country"),"statistics":stats,"avatar_url":avatar}
            findings.append(Finding(entity_type=EntityType.URL,value=url,attributes={"platform":"youtube","channel_id":cid,"username_query":request.seed.value},provenance=_prov(self.descriptor,source_url=url,confidence=0.95,raw=raw)))
            findings.append(Finding(entity_type=EntityType.SOCIAL_ACCOUNT,value=url,attributes=attrs,provenance=_prov(self.descriptor,source_url="https://developers.google.com/youtube/v3",confidence=0.94,raw=raw)))
        if exit_code == 5 and not stdout.strip():
            findings.append(_credential_skip(self.descriptor, stderr))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


_TIKTOK_POST_RE = re.compile(r"^https://www\.tiktok\.com/@[A-Za-z0-9_.]{1,32}/video/[0-9]{5,25}$")
_TIKTOK_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.]{1,32}$")


def _tiktok_post_url(value: str) -> bool:
    """Only the exact public post shape (https, www host) is accepted."""
    return bool(_TIKTOK_POST_RE.match(value))


class TiktokHashtagAdapter(Phase5Adapter):
    descriptor = AdapterDescriptor(
        name="tiktok-hashtag-analysis", license="MIT",
        input_types=[SeedType.HASHTAG],
        output_types=[EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.UNKNOWN],
        legal_notes=[
            "Public hashtag search via the pinned bellingcat library (logged out, headless only): no login, cookies, ms_tokens, media downloads, or platform actions.",
            "The driver disables the TikTokApi browser-stealth patching before any session starts, and the upstream headed retry is structurally unreachable (see docker/tiktok_hashtag/RATE_LIMITS.md); bot-detection responses are recorded as an honest blocked status, never retried, challenged, or evaded.",
            "Only run against hashtags you are authorized to investigate; honor TikTok's terms and rate limits.",
        ],
        rate_limit="One hashtag per container invocation; one anonymous browser session, a bounded post sample (default 40), and no retries beyond the pinned client's bounded transient-error retry.",
        invocation="CLI in dedicated Docker container",
        version_pin="commit 2a4af674efc4af7c7d592053ec3f475555f37694 (TikTokApi 6.2.2; Playwright 1.42.0)",
        upstream="https://github.com/bellingcat/tiktok-hashtag-analysis", network_required=True,
        docker_image="aletheia/tiktok-hashtag:v1",
        output_schema={"hashtag": "string", "posts": "object[]", "cohashtag_counts": "object"},
        health_check="--health", requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.HASHTAG

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return [request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc); raw = stdout.encode(); findings = []
        try: payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: payload = {}
        hashtag = request.seed.value
        status = None
        posts: list = []
        if isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(payload.get("hashtag"), str) and payload["hashtag"]:
                hashtag = payload["hashtag"]
            if isinstance(payload.get("posts"), list):
                posts = payload["posts"]
        authors: dict[str, dict] = {}
        for post in posts:
            if not isinstance(post, dict):
                continue
            url = post.get("url")
            if not (isinstance(url, str) and _tiktok_post_url(url)):
                continue
            attrs = {"platform": "tiktok", "hashtag": hashtag}
            if isinstance(post.get("id"), str) and post["id"]:
                attrs["post_id"] = post["id"]
            cohashtags = post.get("cohashtags")
            clean = [c for c in cohashtags if isinstance(c, str) and c] if isinstance(cohashtags, list) else []
            if clean:
                attrs["cohashtags"] = clean[:20]
            findings.append(Finding(
                entity_type=EntityType.URL, value=url, attributes=attrs,
                provenance=_prov(self.descriptor, source_url=url, confidence=0.6, raw=raw,
                                 notes=["Public hashtag-search hit; the author handle is a same-handle candidate, not a verified identity."]),
            ))
            author = post.get("author")
            if isinstance(author, str) and _TIKTOK_HANDLE_RE.match(author):
                entry = authors.setdefault(author, {"posts": 0, "example_url": url})
                entry["posts"] += 1
        for handle, meta in authors.items():
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT, value=handle,
                attributes={"platform": "tiktok", "hashtag": hashtag, "posts_in_sample": meta["posts"], "example_post_url": meta["example_url"]},
                provenance=_prov(self.descriptor, source_url=meta["example_url"], confidence=0.6, raw=raw,
                                 notes=["Handle observed as the author of a public post under the queried hashtag."]),
            ))
        if not posts and isinstance(status, str) and status in {"blocked", "error", "invalid_hashtag"}:
            reason = payload.get("error") if isinstance(payload.get("error"), str) else status
            findings.append(Finding(
                entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:{status}",
                attributes={"source": self.descriptor.name, "status": status, "hashtag": hashtag, "reason": reason},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=1.0, raw=raw,
                                 notes=[f"Driver recorded status '{status}' with no posts; nothing was retried or fabricated."]),
            ))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


def _picimagesearch_item_urls(engine_name: str, item: dict) -> list[tuple[str, str]]:
    """(https URL, note) pairs carried by one normalized engine item."""
    if engine_name in ("iqdb", "iqdb3d"):
        note = f"Reverse-image match page reported by {engine_name}."
        candidates = [item.get("page_url")]
        for source in item.get("other_sources") if isinstance(item.get("other_sources"), list) else []:
            if isinstance(source, dict):
                candidates.append(source.get("url"))
    elif engine_name == "ascii2d":
        note = "Reverse-image match page reported by ascii2d."
        candidates = [item.get("page_url")]
        for related in item.get("urls") if isinstance(item.get("urls"), list) else []:
            if isinstance(related, dict):
                candidates.append(related.get("href"))
    elif engine_name == "tracemoe":
        note = "TraceMoe scene-match preview media."
        candidates = [item.get("image"), item.get("video")]
    elif engine_name == "sauce_nao":
        note = "SauceNAO match page or external source link."
        candidates = [item.get("page_url")]
        ext_urls = item.get("ext_urls")
        if isinstance(ext_urls, list):
            candidates.extend(ext_urls)
    else:
        return []
    urls: list[tuple[str, str]] = []
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith("https://") and all(candidate != seen for seen, _ in urls):
            urls.append((candidate, note))
    return urls


def _picimagesearch_item_attributes(engine_name: str, item: dict) -> dict:
    """JSON-safe attribute subset for one normalized engine item."""
    attributes: dict = {}
    for key in ("size", "title", "author", "author_url", "source", "match_list", "index_name", "filename", "format", "hash"):
        value = item.get(key)
        if isinstance(value, str) and value:
            attributes[key] = value
    for key in ("similarity", "episode", "from", "to"):
        value = item.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            attributes[key] = value
    for key in ("title_romaji", "title_english", "title_native"):
        value = item.get(key)
        if isinstance(value, str) and value:
            attributes[key] = value
    if item.get("is_adult") is True:
        attributes["is_adult"] = True
    return attributes


class PicImageSearchAdapter(Phase5Adapter):
    descriptor = AdapterDescriptor(
        name="picimagesearch", license="MIT",
        input_types=[SeedType.IMAGE, SeedType.FILE_PATH, SeedType.URL],
        output_types=[EntityType.URL, EntityType.UNKNOWN],
        legal_notes=[
            "Keyless public reverse-image-search endpoints only (IQDB, 3D IQDB, Ascii2D colour search, TraceMoe, AnimeTrace), one request each, plus the official SauceNAO JSON API when SAUCENAO_API_KEY is set (recorded skip otherwise); no pagination and no retries. The consumer-web scrapers (Google, Google Lens, Yandex, Bing, Baidu), the token-refresh Copyseeker scraper, the Turnstile-blocked Lenso client, the TinEye web-app scrape, and the adult-gallery EHentai engine are never imported; see docker/picimagesearch/RATE_LIMITS.md.",
            "The package's hardcoded browser user agent is replaced with an honest Aletheia agent and TLS verification is never disabled; the driver re-checks both before every run and fails closed.",
            "Explicit authorization is required for every target image: it (or its URL) is transmitted to up to five third-party engines.",
        ],
        rate_limit="One image per container invocation; five keyless engine requests plus one optional SauceNAO request; no pagination or retries.",
        invocation="Docker / CLI", version_pin="commit 784713e546273a09aae4b247a8b6f798825efafa (httpx2 2.13.1; lxml 6.1.3; pyquery 2.1.0)",
        upstream="https://github.com/kitUIN/PicImageSearch", network_required=True,
        docker_image="aletheia/picimagesearch:v1",
        output_schema={"engines": "object", "status": "string"},
        health_check="--health", requires_authorization_assertion=True,
        secret_env=["SAUCENAO_API_KEY"],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.IMAGE, SeedType.FILE_PATH, SeedType.URL}

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        if request.seed.type == SeedType.URL:
            return ["--url", request.seed.value]
        image = _stage_image(request, workspace)
        return ["--file", f"/work/{image.name}"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc); raw = stdout.encode(); findings = []
        try: payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: payload = {}
        if not isinstance(payload, dict):
            payload = {}
        target = request.seed.value
        engines = payload.get("engines") if isinstance(payload.get("engines"), dict) else {}
        for engine_name in sorted(engines):
            entry = engines[engine_name] if isinstance(engines[engine_name], dict) else {}
            status = entry.get("status") if isinstance(entry.get("status"), str) else "error"
            count = entry.get("count") if isinstance(entry.get("count"), int) and not isinstance(entry.get("count"), bool) else 0
            result_url = entry.get("result_url") if isinstance(entry.get("result_url"), str) else ""
            if status == "ok":
                items = entry.get("items") if isinstance(entry.get("items"), list) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for url, note in _picimagesearch_item_urls(engine_name, item):
                        attributes = {"engine": engine_name, "target": target}
                        attributes.update(_picimagesearch_item_attributes(engine_name, item))
                        findings.append(Finding(
                            entity_type=EntityType.URL, value=url, attributes=attributes,
                            provenance=_prov(self.descriptor, source_url=result_url or self.descriptor.upstream, confidence=0.6, raw=raw,
                                             notes=[note]),
                        ))
                    if engine_name == "animetrace":
                        characters = item.get("characters") if isinstance(item.get("characters"), list) else []
                        for character in characters:
                            if not isinstance(character, dict):
                                continue
                            name = character.get("name") if isinstance(character.get("name"), str) else ""
                            work = character.get("work") if isinstance(character.get("work"), str) else ""
                            if not name and not work:
                                continue
                            label = f"{name} [{work}]" if work else name
                            findings.append(Finding(
                                entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:animetrace:character:{label}",
                                attributes={"engine": "animetrace", "work": work, "target": target},
                                provenance=_prov(self.descriptor, source_url=result_url or self.descriptor.upstream, confidence=0.5, raw=raw,
                                                 notes=["AnimeTrace character identification; a scene match, not an identity claim."]),
                            ))
            else:
                reason = entry.get("reason") if isinstance(entry.get("reason"), str) else entry.get("error")
                if not isinstance(reason, str) or not reason:
                    reason = status
                attributes = {"source": self.descriptor.name, "engine": engine_name, "status": status, "target": target, "reason": reason}
                if count:
                    attributes["count"] = count
                findings.append(Finding(
                    entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:{engine_name}:{status}",
                    attributes=attributes,
                    provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.3, raw=raw,
                                     notes=[f"Driver recorded engine status '{status}'; nothing was retried or fabricated."]),
                ))
        run_status = payload.get("status") if isinstance(payload.get("status"), str) else ""
        if payload.get("deadline_exceeded") is True:
            run_status = "deadline_exceeded"
        if run_status in {"invalid_target", "blocked", "error", "deadline_exceeded"}:
            reason = payload.get("error") if isinstance(payload.get("error"), str) else run_status
            findings.append(Finding(
                entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:run:{run_status}",
                attributes={"status": run_status, "target": target, "reason": reason},
                provenance=_prov(self.descriptor, source_url=self.descriptor.upstream, confidence=0.3, raw=raw,
                                 notes=[f"Driver recorded run status '{run_status}'; nothing was retried or fabricated."]),
            ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class OverpassAdapter(Phase5Adapter):
    descriptor=AdapterDescriptor(
        name="overpass", license="OpenStreetMap data / ODbL; Overpass API service", input_types=[SeedType.GEOLOCATION], output_types=[EntityType.PLACE, EntityType.GEOLOCATION, EntityType.UNKNOWN],
        legal_notes=["Read-only query against public OpenStreetMap-derived data. No probing or target interaction.", "Exact coordinates must be supplied by an authorized caller; respect Overpass instance usage policy."],
        rate_limit="Default 500 m radius and one query per invocation; instance throttling applies.", invocation="HTTPS API via dedicated Docker runner", version_pin="public API (2026-10-08)",
        upstream="https://overpass-api.de/", network_required=True, docker_image="aletheia/overpass:public", output_schema={"elements":"object[]"}, health_check="runner.py --health", requires_authorization_assertion=True,
    )
    def supports(self, seed_type): return seed_type == SeedType.GEOLOCATION
    def build_command(self, request, workspace): return [request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); findings=[]
        try: payload=json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: payload={}
        elements=payload.get("elements",[]) if isinstance(payload,dict) else []
        for item in elements[:250]:
            if not isinstance(item,dict): continue
            tags=item.get("tags",{}) or {}; name=tags.get("name") or tags.get("amenity") or tags.get("shop") or tags.get("tourism")
            if not name: continue
            center=item.get("center") or {"lat":item.get("lat"),"lon":item.get("lon")}
            place_url=f"https://www.openstreetmap.org/{item.get('type','node')}/{item.get('id')}" if item.get("type") and item.get("id") else self.descriptor.upstream
            findings.append(Finding(entity_type=EntityType.PLACE,value=str(name),attributes={"osm_type":item.get("type"),"osm_id":item.get("id"),"tags":tags,"center":center},provenance=_prov(self.descriptor,source_url=place_url,confidence=0.90,raw=raw)))
        findings.append(Finding(entity_type=EntityType.GEOLOCATION,value=request.seed.value,attributes={"radius_m":500,"source":"OpenStreetMap/Overpass"},provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.99,raw=raw),source_kind="seed"))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class SunCalcAdapter(Phase5Adapter):
    descriptor=AdapterDescriptor(
        name="suncalc", license="BSD-2-Clause", input_types=[SeedType.GEOLOCATION], output_types=[EntityType.UNKNOWN, EntityType.GEOLOCATION],
        legal_notes=["Deterministic astronomical calculation from supplied coordinates/time. No network or identity inference."], rate_limit="Local CPU only.", invocation="Node package in dedicated Docker container", version_pin="2.0.2",
        upstream="https://www.npmjs.com/package/suncalc", network_required=False, docker_image="aletheia/suncalc:2.0.2", output_schema={"sun":"object"}, health_check="runner.js --health",
    )
    def supports(self, seed_type): return seed_type == SeedType.GEOLOCATION
    def build_command(self, request, workspace): return [request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); findings=[]
        try: data=json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: data={}
        if isinstance(data,dict):
            findings.append(Finding(entity_type=EntityType.GEOLOCATION,value=request.seed.value,attributes={"sun":data},provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.99,raw=raw)))
            for key in ("sun_azimuth","sun_altitude","sunrise","sunset","civil_dawn","civil_dusk"):
                if key in data: findings.append(Finding(entity_type=EntityType.UNKNOWN,value=str(data[key]),attributes={"field":key,"geolocation":request.seed.value},provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.99,raw=raw)))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class DeepFaceAdapter(Phase5Adapter):
    descriptor=AdapterDescriptor(
        name="deepface", license="MIT (DeepFace; underlying model licenses vary)", input_types=[SeedType.IMAGE, SeedType.FILE_PATH], output_types=[EntityType.IMAGE, EntityType.FACE, EntityType.UNKNOWN],
        legal_notes=["Offline face detection only in this adapter; no face database search, person identification, age/gender/race inference, or remote model download is enabled.", "DeepFace documents that wrapped models can carry separate licenses; this adapter uses its OpenCV detector path only."],
        rate_limit="Local CPU; one image per invocation.", invocation="Python package in dedicated Docker container", version_pin="0.0.101",
        upstream="https://github.com/serengil/deepface", network_required=False, docker_image="aletheia/deepface:0.0.101", output_schema={"faces":"object[]"}, health_check="runner.py --health",
    )
    def supports(self, seed_type): return seed_type in {SeedType.IMAGE, SeedType.FILE_PATH}
    def build_command(self, request, workspace):
        image=_stage_image(request,workspace); return [f"/work/{image.name}"]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); findings=[]
        try: data=json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: data={}
        faces=data.get("faces",[]) if isinstance(data,dict) else []
        findings.append(Finding(entity_type=EntityType.IMAGE,value=str(Path(request.seed.value).resolve()),attributes={"face_count":len(faces)},provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.98,raw=raw),source_kind="seed"))
        for i,face in enumerate(faces):
            area=face.get("facial_area",{}) if isinstance(face,dict) else {}
            findings.append(Finding(entity_type=EntityType.FACE,value=f"{Path(request.seed.value).name}#face-{i+1}",attributes={"facial_area":area},provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.92,raw=raw,notes=["Detection only; no identity inference."])))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class InsightFaceAdapter(Phase5Adapter):
    descriptor=AdapterDescriptor(
        name="insightface", license="MIT (package; model licenses vary)", input_types=[SeedType.IMAGE, SeedType.FILE_PATH], output_types=[EntityType.IMAGE, EntityType.FACE, EntityType.UNKNOWN],
        legal_notes=["Offline face detection/landmark extraction only; no identity matching against remote datasets. Model weights must be operator-provisioned under their applicable licenses; network is disabled so automatic model download cannot occur."],
        rate_limit="Local CPU; one image per invocation.", invocation="Python package in dedicated Docker container", version_pin="2.1",
        upstream="https://github.com/deepinsight/insightface", network_required=False, docker_image="aletheia/insightface:2.1", output_schema={"faces":"object[]"}, health_check="runner.py --health",
    )
    def supports(self, seed_type): return seed_type in {SeedType.IMAGE, SeedType.FILE_PATH}
    def build_command(self, request, workspace):
        image=_stage_image(request,workspace); return [f"/work/{image.name}"]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); findings=[]
        try: data=json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: data={}
        faces=data.get("faces",[]) if isinstance(data,dict) else []
        findings.append(Finding(entity_type=EntityType.IMAGE,value=str(Path(request.seed.value).resolve()),attributes={"face_count":len(faces)},provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.98,raw=raw),source_kind="seed"))
        for i,face in enumerate(faces):
            attrs={k:face.get(k) for k in ("bbox","det_score","age") if k in face}
            findings.append(Finding(entity_type=EntityType.FACE,value=f"{Path(request.seed.value).name}#face-{i+1}",attributes=attrs,provenance=_prov(self.descriptor,source_url=self.descriptor.upstream,confidence=0.92,raw=raw,notes=["Detection/landmark output only; no remote identity search."])))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


PHASE5_ADAPTER_CLASSES = [InstaloaderAdapter, RedditAPIAdapter, YouTubeAPIAdapter, OverpassAdapter, SunCalcAdapter, DeepFaceAdapter, InsightFaceAdapter]
