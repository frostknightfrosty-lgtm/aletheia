from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType, Finding,
    Provenance, SeedType,
)


def _prov(adapter: AdapterDescriptor, source_url: str | None, confidence: float, raw: bytes,
          notes: list[str] | None = None) -> Provenance:
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


def _result(request: AdapterRunRequest, adapter: AdapterDescriptor, started: datetime,
            findings: list[Finding], stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
    return AdapterRunResult(
        run_id=request.run_id,
        adapter=adapter,
        status="succeeded" if exit_code == 0 else "partial",
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        exit_code=exit_code,
        findings=findings,
        stderr_tail=stderr[-4000:],
        stdout_tail=stdout[-4000:],
    )


def _json(stdout: str) -> object:
    try:
        return json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        return {}


class Phase6Adapter(Adapter):
    pass


class SECEdgarAdapter(Phase6Adapter):
    descriptor = AdapterDescriptor(
        name="sec-edgar",
        license="U.S. SEC public EDGAR data",
        input_types=[SeedType.NAME],
        output_types=[EntityType.COMPANY, EntityType.LEGAL_ENTITY, EntityType.FILING, EntityType.JURISDICTION, EntityType.UNKNOWN],
        legal_notes=[
            "Uses the public SEC EDGAR REST data endpoints only; no authentication or filing submission is performed.",
            "Every request must identify Aletheia with a descriptive User-Agent and respect SEC fair-access guidance.",
            "SEC results are public filings/metadata and are not themselves evidence of ownership, control, or wrongdoing."
        ],
        rate_limit="Respect SEC fair-access limits; adapter uses bounded sequential requests.",
        invocation="HTTPS API via dedicated Docker runner",
        version_pin="EDGAR REST APIs",
        upstream="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        network_required=True,
        docker_image="aletheia/sec-edgar:public-api",
        output_schema={"company_matches": "object[]", "filings": "object[]"},
        health_check="runner.py --health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self.descriptor.input_types

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return [request.seed.type.value, request.seed.value]

    def parse(self, request, workspace, stdout, stderr, exit_code):
        started = datetime.now(timezone.utc)
        raw = stdout.encode()
        data = _json(stdout)
        findings: list[Finding] = []
        if isinstance(data, dict):
            for match in data.get("companies", []) if isinstance(data.get("companies"), list) else []:
                if not isinstance(match, dict):
                    continue
                cik = str(match.get("cik", "")).zfill(10) if match.get("cik") else None
                name = match.get("name")
                if not name:
                    continue
                source = f"https://www.sec.gov/edgar/browse/?CIK={cik}" if cik else self.descriptor.upstream
                findings.append(Finding(
                    entity_type=EntityType.COMPANY, value=str(name),
                    attributes={"cik": cik, "ticker": match.get("ticker"), "sic": match.get("sic")},
                    provenance=_prov(self.descriptor, source, 0.96, raw,
                                     ["SEC EDGAR company index match; filing data remains source evidence."]),
                ))
                if cik:
                    findings.append(Finding(
                        entity_type=EntityType.LEGAL_ENTITY, value=f"SEC:Cik{cik}",
                        attributes={"cik": cik, "company_name": name},
                        provenance=_prov(self.descriptor, source, 0.94, raw),
                    ))
            for filing in data.get("filings", []) if isinstance(data.get("filings"), list) else []:
                if not isinstance(filing, dict):
                    continue
                accession = filing.get("accession_number")
                if not accession:
                    continue
                cik = filing.get("cik")
                url = filing.get("filing_url") or self.descriptor.upstream
                findings.append(Finding(
                    entity_type=EntityType.FILING, value=str(accession),
                    attributes={k: filing.get(k) for k in ("form", "filing_date", "report_date", "company_name", "cik", "primary_document")},
                    provenance=_prov(self.descriptor, str(url), 0.98, raw, ["SEC filing metadata."]),
                ))
                jurisdiction = filing.get("state_of_incorporation")
                if jurisdiction:
                    findings.append(Finding(
                        entity_type=EntityType.JURISDICTION, value=str(jurisdiction),
                        attributes={"cik": cik, "source": "SEC filing metadata"},
                        provenance=_prov(self.descriptor, str(url), 0.83, raw),
                    ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)


class GLEIFAdapter(Phase6Adapter):
    descriptor = AdapterDescriptor(
        name="gleif",
        license="GLEIF open data / API terms",
        input_types=[SeedType.NAME],
        output_types=[EntityType.LEGAL_ENTITY, EntityType.LEI, EntityType.UNKNOWN],
        legal_notes=[
            "Queries GLEIF's public API for LEI reference/ownership data; no account access or private records are used.",
            "GLEIF fuzzy matching and parent/child data are treated as candidate evidence and are not asserted as identity by themselves."
        ],
        rate_limit="Respect provider limits; one bounded name search per invocation.",
        invocation="HTTPS API via dedicated Docker runner",
        version_pin="GLEIF API v1",
        upstream="https://www.gleif.org/en/lei-data/gleif-api",
        network_required=True,
        docker_image="aletheia/gleif:api-v1",
        output_schema={"lei_records": "object[]"}, health_check="runner.py --health",
        requires_authorization_assertion=True,
    )
    def supports(self, seed_type): return seed_type == SeedType.NAME
    def build_command(self, request, workspace): return [request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started = datetime.now(timezone.utc); raw = stdout.encode(); data = _json(stdout); findings=[]
        records = data.get("records", []) if isinstance(data, dict) else []
        for rec in records if isinstance(records, list) else []:
            if not isinstance(rec, dict): continue
            lei = rec.get("lei")
            entity = rec.get("entity") or {}
            name = entity.get("legalName") or entity.get("name")
            if not name: continue
            source = rec.get("source_url") or f"https://search.gleif.org/#/record/{lei}" if lei else self.descriptor.upstream
            if lei:
                findings.append(Finding(entity_type=EntityType.LEI, value=str(lei), attributes={"legal_name": name, "status": rec.get("status")}, provenance=_prov(self.descriptor, source, 0.99, raw)))
            findings.append(Finding(entity_type=EntityType.LEGAL_ENTITY, value=str(name), attributes={"lei": lei, "jurisdiction": entity.get("jurisdiction"), "legal_form": entity.get("legalForm")}, provenance=_prov(self.descriptor, source, 0.94, raw, ["GLEIF entity record."])))
            parent = (rec.get("parent") or {}).get("lei") if isinstance(rec.get("parent"), dict) else None
            if parent:
                findings.append(Finding(entity_type=EntityType.LEI, value=str(parent), attributes={"relationship": "parent_lei", "child_lei": lei}, provenance=_prov(self.descriptor, source, 0.90, raw)))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class OpenCorporatesAdapter(Phase6Adapter):
    descriptor = AdapterDescriptor(
        name="opencorporates", license="OpenCorporates API terms / dataset licence",
        input_types=[SeedType.NAME], output_types=[EntityType.COMPANY, EntityType.LEGAL_ENTITY, EntityType.JURISDICTION, EntityType.UNKNOWN],
        legal_notes=[
            "Requires an OpenCorporates API token. Token must be supplied as a secret environment variable and never as a command argument.",
            "Respect the account's query, rate, and licensing restrictions; do not scrape the website as a substitute for the API."
        ],
        rate_limit="Provider/account quota; adapter performs one bounded search request.", invocation="HTTPS API via dedicated Docker runner", version_pin="REST API v0.4.8",
        upstream="https://api.opencorporates.com/documentation/API-Reference", network_required=True,
        docker_image="aletheia/opencorporates:api-v0.4.8", output_schema={"companies": "object[]"}, health_check="runner.py --health",
        requires_authorization_assertion=True, secret_env=["OPENCORPORATES_API_TOKEN"],
    )
    def supports(self, seed_type): return seed_type in self.descriptor.input_types
    def build_command(self, request, workspace): return [request.seed.type.value, request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); data=_json(stdout); findings=[]
        companies=data.get("companies",[]) if isinstance(data,dict) else []
        for c in companies if isinstance(companies,list) else []:
            if not isinstance(c,dict): continue
            name=c.get("name") or c.get("company_name")
            company_number=c.get("company_number") or c.get("company_number_norm")
            jurisdiction=c.get("jurisdiction_code") or c.get("jurisdiction")
            url=c.get("opencorporates_url") or self.descriptor.upstream
            if not name: continue
            attrs={"company_number":company_number,"jurisdiction":jurisdiction,"incorporation_date":c.get("incorporation_date"),"current_status":c.get("current_status"),"registered_address":c.get("registered_address_in_full")}
            findings.append(Finding(entity_type=EntityType.COMPANY,value=str(name),attributes=attrs,provenance=_prov(self.descriptor,url,0.91,raw,["OpenCorporates API record; jurisdiction-specific registry is the underlying authority."])))
            if company_number:
                findings.append(Finding(entity_type=EntityType.LEGAL_ENTITY,value=f"{jurisdiction}:{company_number}",attributes=attrs,provenance=_prov(self.descriptor,url,0.89,raw)))
            if jurisdiction:
                findings.append(Finding(entity_type=EntityType.JURISDICTION,value=str(jurisdiction),attributes={"company_number":company_number},provenance=_prov(self.descriptor,url,0.82,raw)))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class OpenSanctionsAdapter(Phase6Adapter):
    descriptor = AdapterDescriptor(
        name="opensanctions", license="OpenSanctions dataset/API terms",
        input_types=[SeedType.NAME, SeedType.EMAIL, SeedType.DOMAIN], output_types=[EntityType.SANCTION, EntityType.PERSON, EntityType.COMPANY, EntityType.LEGAL_ENTITY, EntityType.UNKNOWN],
        legal_notes=[
            "Hosted OpenSanctions API requires an API key; keep the key secret and use the permitted dataset/licensing scope.",
            "This adapter performs a sanctions-scoped text search and returns ranked records. Search relevance is not a match/identity probability and must not be treated as a confirmed sanctions hit."
        ],
        rate_limit="Provider/account quota; one bounded sanctions search per invocation.", invocation="HTTPS API via dedicated Docker runner", version_pin="OpenSanctions API",
        upstream="https://api.opensanctions.org/docs", network_required=True,
        docker_image="aletheia/opensanctions:api", output_schema={"results": "object[]"}, health_check="runner.py --health",
        requires_authorization_assertion=True, secret_env=["OPENSANCTIONS_API_KEY"],
    )
    def supports(self, seed_type): return seed_type in self.descriptor.input_types
    def build_command(self, request, workspace): return [request.seed.type.value, request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); data=_json(stdout); findings=[]
        results=data.get("results",[]) if isinstance(data,dict) else []
        for r in results if isinstance(results,list) else []:
            if not isinstance(r,dict): continue
            title=r.get("caption") or r.get("name") or r.get("id")
            if not title: continue
            score=r.get("score")
            try: conf=max(0.0,min(1.0,float(score))) if score is not None else 0.50
            except (ValueError,TypeError): conf=0.50
            ent_type=str(r.get("schema") or "").casefold()
            mapped = EntityType.PERSON if "person" in ent_type else EntityType.COMPANY if "company" in ent_type or "organization" in ent_type else EntityType.SANCTION
            source=r.get("url") or self.descriptor.upstream
            findings.append(Finding(entity_type=mapped,value=str(title),attributes={"id":r.get("id"),"schema":r.get("schema"),"topics":r.get("topics"),"datasets":r.get("datasets"),"search_score":score},provenance=_prov(self.descriptor,source,conf,raw,["Search relevance score is not identity/match probability."])))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


class CourtListenerAdapter(Phase6Adapter):
    descriptor = AdapterDescriptor(
        name="courtlistener", license="CourtListener terms / source-specific court documents",
        input_types=[SeedType.NAME], output_types=[EntityType.COURT_CASE, EntityType.PERSON, EntityType.COMPANY, EntityType.JURISDICTION, EntityType.UNKNOWN],
        legal_notes=[
            "Uses CourtListener's public API search only; it does not access PACER credentials or sealed/private court records.",
            "CourtListener search results are discovery leads. Verify the underlying docket/opinion before treating a legal claim as established fact."
        ],
        rate_limit="Respect CourtListener API rate limits; one bounded search request per invocation.", invocation="HTTPS API via dedicated Docker runner", version_pin="REST API v3",
        upstream="https://www.courtlistener.com/api/rest/v3/", network_required=True,
        docker_image="aletheia/courtlistener:api-v3", output_schema={"results": "object[]"}, health_check="runner.py --health",
        requires_authorization_assertion=True,
    )
    def supports(self, seed_type): return seed_type == SeedType.NAME
    def build_command(self, request, workspace): return [request.seed.value]
    def parse(self, request, workspace, stdout, stderr, exit_code):
        started=datetime.now(timezone.utc); raw=stdout.encode(); data=_json(stdout); findings=[]
        results=data.get("results",[]) if isinstance(data,dict) else []
        for r in results if isinstance(results,list) else []:
            if not isinstance(r,dict): continue
            name=r.get("caseName") or r.get("case_name") or r.get("absolute_url")
            if not name: continue
            url=r.get("absolute_url") or self.descriptor.upstream
            attrs={"court":r.get("court_citation") or r.get("court"),"dateFiled":r.get("dateFiled") or r.get("date_filed"),"docketNumber":r.get("docketNumber") or r.get("docket_number"),"type":r.get("type"),"snippet":r.get("snippet")}
            findings.append(Finding(entity_type=EntityType.COURT_CASE,value=str(name),attributes=attrs,provenance=_prov(self.descriptor,url,0.88,raw,["CourtListener search result; underlying source should be reviewed."])))
            court=attrs.get("court")
            if court:
                findings.append(Finding(entity_type=EntityType.JURISDICTION,value=str(court),attributes={"case":name},provenance=_prov(self.descriptor,url,0.75,raw)))
        return _result(request,self.descriptor,started,findings,stdout,stderr,exit_code)


PHASE6_ADAPTER_CLASSES = [SECEdgarAdapter, GLEIFAdapter, OpenCorporatesAdapter, OpenSanctionsAdapter, CourtListenerAdapter]
