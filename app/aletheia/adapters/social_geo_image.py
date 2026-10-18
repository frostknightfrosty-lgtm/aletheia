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
            attrs={"platform":"youtube","title":snip.get("title"),"description":snip.get("description"),"custom_url":snip.get("customUrl"),"country":snip.get("country"),"statistics":stats}
            findings.append(Finding(entity_type=EntityType.URL,value=url,attributes={"platform":"youtube","channel_id":cid,"username_query":request.seed.value},provenance=_prov(self.descriptor,source_url=url,confidence=0.95,raw=raw)))
            findings.append(Finding(entity_type=EntityType.SOCIAL_ACCOUNT,value=url,attributes=attrs,provenance=_prov(self.descriptor,source_url="https://developers.google.com/youtube/v3",confidence=0.94,raw=raw)))
        if exit_code == 5 and not stdout.strip():
            findings.append(_credential_skip(self.descriptor, stderr))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


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
