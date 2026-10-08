from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SeedType(StrEnum):
    USERNAME = "username"
    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    DOMAIN = "domain"
    IP = "ip"
    FILE_PATH = "file_path"
    IMAGE = "image"
    GEOLOCATION = "geolocation"


class EntityType(StrEnum):
    PERSON = "person"
    USERNAME = "username"
    NAME = "name"
    DOMAIN = "domain"
    URL = "url"
    EMAIL = "email"
    IP = "ip"
    HOST = "host"
    FILE = "file"
    PHONE = "phone"
    SERVICE = "service"
    BREACH = "breach"
    SOCIAL_ACCOUNT = "social_account"
    PLACE = "place"
    GEOLOCATION = "geolocation"
    IMAGE = "image"
    FACE = "face"
    OCR_TEXT = "ocr_text"
    COMPANY = "company"
    LEGAL_ENTITY = "legal_entity"
    LEI = "lei"
    FILING = "filing"
    COURT_CASE = "court_case"
    SANCTION = "sanction"
    JURISDICTION = "jurisdiction"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    OBSERVED_AT = "observed_at"
    RESOLVES_TO = "resolves_to"
    ASSOCIATED_WITH = "associated_with"
    DERIVED_FROM = "derived_from"
    MENTIONS = "mentions"
    SAME_AS_CANDIDATE = "same_as_candidate"


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: SeedType
    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.strip()


class Provenance(BaseModel):
    tool: str
    source_url: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_evidence_sha256: str | None = None
    adapter_version: str
    notes: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: UUID = Field(default_factory=uuid4)
    entity_type: EntityType
    value: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    source_kind: str = "collector"


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: UUID = Field(default_factory=uuid4)
    entity_type: EntityType
    canonical_value: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime = Field(default_factory=utc_now)
    last_seen: datetime = Field(default_factory=utc_now)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edge_id: UUID = Field(default_factory=uuid4)
    source_entity_id: UUID
    target_entity_id: UUID
    relationship: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    attributes: dict[str, Any] = Field(default_factory=dict)


class AdapterDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    license: str
    input_types: list[SeedType]
    output_types: list[EntityType]
    legal_notes: list[str]
    rate_limit: str
    invocation: str
    version_pin: str
    upstream: str
    network_required: bool
    docker_image: str
    output_schema: dict[str, Any] = Field(default_factory=dict)
    health_check: str = ""
    requires_authorization_assertion: bool = False
    secret_env: list[str] = Field(default_factory=list)
    parser_test_exempt: bool = False
    parser_test_exempt_reason: str | None = None


class AdapterRunRequest(BaseModel):
    run_id: UUID
    seed: Seed
    legal_only: bool = True
    authorization_assertion: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    proxy_url: str | None = None


class AdapterRunResult(BaseModel):
    run_id: UUID
    adapter: AdapterDescriptor
    status: str
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    findings: list[Finding] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    stderr_tail: str = ""
    stdout_tail: str = ""
    error: str | None = None


class AuditEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    occurred_at: datetime = Field(default_factory=utc_now)
    event_type: str
    adapter: str | None = None
    command: list[str] | None = None
    request_meta: dict[str, Any] = Field(default_factory=dict)
    outcome: str | None = None
