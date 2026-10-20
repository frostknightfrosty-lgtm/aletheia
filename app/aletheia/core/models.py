from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SeedType(StrEnum):
    USERNAME = "username"
    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    DOMAIN = "domain"
    URL = "url"
    IP = "ip"
    FILE_PATH = "file_path"
    IMAGE = "image"
    GEOLOCATION = "geolocation"
    COMPANY_NAME = "company_name"
    BANK_NAME = "bank_name"
    VIN = "vin"
    PERSON_NAME = "person_name"
    LOBBYIST_NAME = "lobbyist_name"
    CRYPTO_ADDRESS = "crypto_address"
    # Hashtag seed: a platform topic tag (leading '#' optional,
    # case-insensitive). Added for the tiktok-hashtag-analysis adapter; no
    # existing SeedType covered a topic tag as a query unit.
    HASHTAG = "hashtag"
    # Shadow-observation seed: an object height (m), shadow length (m), and a
    # UTC datetime, encoded as key=value pairs in the seed value. Added for the
    # ShadowFinder adapter; no existing SeedType covered a measurement payload.
    SHADOW_OBSERVATION = "shadow_observation"
    # Composite IP seed: a patent number, a trademark serial/registration number,
    # an assignee/inventor name, or a free-text patent/trademark query. Added for
    # the patents_trademarks batch adapter; no existing SeedType covered it.
    INTELLECTUAL_PROPERTY = "intellectual_property"


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
    GOVERNMENT_RECORD = "government_record"
    COMPANY_REGISTRY_RECORD = "company_registry_record"
    ACADEMIC_RECORD = "academic_record"
    TLS_OBSERVATION = "tls_observation"
    BLOCKCHAIN_INTEL_RECORD = "blockchain_intel_record"
    INTELLECTUAL_PROPERTY_RECORD = "intellectual_property_record"
    # Composite email-authentication observation: MX/SPF/DMARC (and related)
    # DNS-record results from the scan.mx API or the checkdmarc library. Added
    # for the email_auth batch adapter; no existing EntityType covered it.
    EMAIL_AUTH_RECORD = "email_auth_record"
    # Composite technical-surface finding: a source-code search match returned by
    # the code_search batch adapter, carrying a typed finding_kind. Added for the
    # code_search batch adapter; no existing EntityType covered it.
    TECHNICAL_FINDING = "technical_finding"
    # Composite web-search finding: a normalized search-engine or web-index
    # result returned by the search_engines batch adapter. Added for the
    # search_engines batch adapter; no existing EntityType covered a web-search
    # result, so the plan's "WebSearchResult" output type maps to this member.
    WEB_SEARCH_RESULT = "web_search_result"
    # Composite geolocation/image observation: a normalized place, street-level
    # image, satellite catalogue item, or bounded local image-forensics result.
    GEO_EVIDENCE = "geo_evidence"
    # Composite transport asset registry observation (aircraft registry, aircraft
    # photo metadata, or railway facility data).
    TRANSPORT_ASSET_RECORD = "transport_asset_record"


class RelationshipType(StrEnum):
    OBSERVED_AT = "observed_at"
    RESOLVES_TO = "resolves_to"
    ASSOCIATED_WITH = "associated_with"
    DERIVED_FROM = "derived_from"
    MENTIONS = "mentions"
    SAME_AS_CANDIDATE = "same_as_candidate"
    # Phase 17 (P17.2) additions — written once cascade decisions exist.
    SAME_AS_CONFIRMED = "same_as_confirmed"
    SAME_AS_EXCLUDED = "same_as_excluded"
    PIVOTED_FROM = "pivoted_from"


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: SeedType
    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.strip()


class ContextFilters(BaseModel):
    """Optional constraint filters for a multi-seed investigation.

    A filter narrows an investigation without blocking it: the values are carried
    through the run (manifest, adapter requests, resolution, reporting) and are
    enforced only where an attribute they name can actually be compared. An
    entity that carries no value for a filtered attribute is never excluded on
    that basis, because absence of evidence is not a mismatch.

    Matching is deliberately dependency-free and documented per field:

    - ``country``: token match against attribute values (case-insensitive). A
      value matches when the filter equals one of the value's alphanumeric
      tokens ("US" matches "United States (US)") or, for filters longer than
      three characters, when the filter appears as a substring. No ISO-3166
      dataset is bundled, so "US" does not expand to "United States".
    - ``age_min``/``age_max``: compared against an ``age`` attribute or an age
      derived from ``birth_year``/``birthdate``/``birth_date``/``dob`` at the
      current UTC year. Only entities whose age is computable are filtered.
    - ``language``: token match like ``country`` ("en" matches "en-US").
    - ``timezone``: case-insensitive equality or substring match against an IANA
      timezone string ("America/New_York").
    """

    model_config = ConfigDict(extra="forbid")
    country: str | None = None
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    language: str | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def _age_range_is_ordered(self) -> "ContextFilters":
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("age_min must be <= age_max")
        return self

    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (self.country, self.age_min, self.age_max, self.language, self.timezone)
        )


class Provenance(BaseModel):
    tool: str
    source_url: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_evidence_sha256: str | None = None
    adapter_version: str
    notes: list[str] = Field(default_factory=list)
    # Multi-seed runs tag each finding with the index of the seed whose
    # expansion produced it (0-based position in ``manifest["seeds"]``). The
    # value stays ``None`` for single-seed runs so their artifacts keep the
    # pre-multi-seed shape.
    seed_index: int | None = None
    # Phase 17 (P17.2) cascade provenance. The defaults keep a single-pass
    # finding's meaning unchanged: depth 0 means "produced directly from a
    # seed", and no parent finding or pivot reason is recorded outside the
    # cascade.
    parent_finding_id: UUID | None = None
    cascade_depth: int = Field(default=0, ge=0)
    pivot_reason: str | None = None


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
    network_name: str | None = None
    # Position of ``seed`` in a multi-seed run (0 for single-seed runs). Adapters
    # may include it in their own audit metadata; the orchestrator uses it to
    # tag findings and to keep per-seed workspaces separate.
    seed_index: int = Field(default=0, ge=0)
    # Constraint filters carried from the run manifest. Adapters may use them as
    # query hints; enforcement happens in entity resolution and reporting, and
    # the filters never block a run.
    context_filters: ContextFilters | None = None


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


# ---------------------------------------------------------------------------
# Phase 17 (P17.2) cascade models (design section 14). All additions are
# additive and backward compatible: nothing here changes existing behavior.
# ---------------------------------------------------------------------------


class IdentityTier(StrEnum):
    """Identity-cluster tier (design section 6.3).

    A cluster that has not been reviewed yet keeps no tier (``None`` where the
    field is optional); these four members are the review outcomes.
    """

    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    EXCLUDED = "excluded"


class SourceGrade(BaseModel):
    """Admiralty-style source grading (design section 6.3).

    ``reliability`` is A (completely reliable) through F (cannot be judged);
    ``credibility`` is 1 (confirmed) through 6 (cannot be judged). Claims
    inherit their source's grade and a low-grade source alone can never clear
    a tier gate. The honest default for an ungraded source is F6.
    """

    model_config = ConfigDict(extra="forbid")
    reliability: str
    credibility: int = Field(ge=1, le=6)

    @field_validator("reliability")
    @classmethod
    def _reliability_is_admiralty(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"A", "B", "C", "D", "E", "F"}:
            raise ValueError("reliability must be one of A-F (Admiralty scale)")
        return value

    @property
    def label(self) -> str:
        return f"{self.reliability}{self.credibility}"

    @classmethod
    def unrated(cls) -> "SourceGrade":
        return cls(reliability="F", credibility=6)


class Hypothesis(StrEnum):
    """Analysis-of-Competing-Hypotheses labels (design section 6.3)."""

    SUBJECT = "H_subject"
    OTHER = "H_other"
    SHARED = "H_shared"


class HypothesisVerdict(StrEnum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    NEUTRAL = "neutral"


class HypothesisAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis: Hypothesis
    verdict: HypothesisVerdict
    evidence: list[str] = Field(default_factory=list)
    rationale: str = ""


class ClusterDecision(BaseModel):
    """One merge / no-merge decision over a set of identity clusters.

    ``score`` is the uncalibrated likelihood-ratio sum and is never presented
    as a probability; ``calibrated_probability`` stays ``None`` until the
    calibrator is trained.
    """

    model_config = ConfigDict(extra="forbid")
    decision_id: UUID = Field(default_factory=uuid4)
    entity_ids: list[UUID] = Field(min_length=2)
    tier: IdentityTier | None = None
    accepted: bool = False
    score: float | None = None
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    assessments: list[HypothesisAssessment] = Field(default_factory=list)
    conflict: str | None = None
    reason: str = ""


class PivotCandidate(BaseModel):
    """A typed seed derived from an observed claim (design sections 4, 7).

    ``gate`` is the minimum surviving cluster tier that permits the pivot;
    personal identifiers require ``confirmed``, structural seeds
    ``probable``, and media seeds ``probable`` with local comparison.
    """

    model_config = ConfigDict(extra="forbid")
    pivot_id: UUID = Field(default_factory=uuid4)
    claim_entity_type: EntityType
    claim_value: str
    seed: Seed
    gate: IdentityTier
    reason: str = ""
    seed_index: int | None = None
    parent_finding_id: UUID | None = None
