from parser_test_marker import parser_test
import json
from pathlib import Path
from uuid import uuid4

from aletheia.adapters.corporate_records import (
    CourtListenerAdapter, GLEIFAdapter, OpenCorporatesAdapter, OpenSanctionsAdapter, SECEdgarAdapter,
)
from aletheia.core.models import AdapterRunRequest, Seed, SeedType, EntityType


def req(kind, value):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType(kind), value=value), authorization_assertion="authorized test")


def test_phase6_descriptors_are_legal_gated():
    for adapter in [SECEdgarAdapter(), GLEIFAdapter(), OpenCorporatesAdapter(), OpenSanctionsAdapter(), CourtListenerAdapter()]:
        assert adapter.descriptor.requires_authorization_assertion is True
        assert adapter.descriptor.network_required is True


@parser_test('sec-edgar')
def test_sec_parser_normalizes_company_and_filing():
    a=SECEdgarAdapter(); r=req("name","Acme Corp")
    stdout=json.dumps({"companies":[{"name":"ACME CORP","cik":"0000123456","ticker":"ACME","sic":"1234"}],"filings":[{"accession_number":"0000123456-26-000001","form":"10-K","filing_date":"2026-02-01","report_date":"2025-12-31","company_name":"ACME CORP","cik":"0000123456","primary_document":"acme-10k.htm","filing_url":"https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/acme-10k.htm"}]})
    res=a.parse(r,Path("/tmp"),stdout,"",0)
    assert any(f.entity_type==EntityType.COMPANY and f.value=="ACME CORP" for f in res.findings)
    assert any(f.entity_type==EntityType.FILING and f.value=="0000123456-26-000001" for f in res.findings)


@parser_test('gleif')
def test_gleif_parser_extracts_lei():
    a=GLEIFAdapter(); r=req("name","ACME CORP")
    stdout=json.dumps({"records":[{"lei":"549300TESTLEI00000001","status":"ISSUED","entity":{"legalName":"ACME CORP","jurisdiction":"US","legalForm":"Corporation"},"parent":None,"source_url":"https://api.gleif.org/api/v1/lei-records/549300TESTLEI00000001"}]})
    res=a.parse(r,Path("/tmp"),stdout,"",0)
    assert any(f.entity_type==EntityType.LEI for f in res.findings)


@parser_test('opencorporates')
def test_opencorporates_parser_extracts_company():
    a=OpenCorporatesAdapter(); r=req("name","ACME CORP")
    stdout=json.dumps({"companies":[{"name":"ACME CORP","company_number":"12345","jurisdiction_code":"gb","current_status":"Active","opencorporates_url":"https://opencorporates.com/companies/gb/12345"}]})
    res=a.parse(r,Path("/tmp"),stdout,"",0)
    assert any(f.entity_type==EntityType.COMPANY for f in res.findings)
    assert any(f.entity_type==EntityType.JURISDICTION for f in res.findings)


@parser_test('opensanctions')
def test_opensanctions_marks_search_score_not_identity_probability():
    a=OpenSanctionsAdapter(); r=req("name","John Doe")
    stdout=json.dumps({"results":[{"id":"NK-1","caption":"John Doe","schema":"Person","score":0.91,"topics":["sanction"],"datasets":["us_ofac_sdn"]}]})
    res=a.parse(r,Path("/tmp"),stdout,"",0)
    hit=next(f for f in res.findings if f.value=="John Doe")
    assert hit.entity_type==EntityType.PERSON
    assert "search relevance score is not identity/match probability." in hit.provenance.notes[0].lower()


@parser_test('courtlistener')
def test_courtlistener_parser_extracts_case():
    a=CourtListenerAdapter(); r=req("name","Jane Doe")
    stdout=json.dumps({"results":[{"caseName":"Doe v. Example","absolute_url":"https://www.courtlistener.com/docket/1/","court_citation":"Example Dist. Ct.","dateFiled":"2026-01-01","docketNumber":"1:26-cv-00001","type":"r","snippet":"example","score":0.8}]})
    res=a.parse(r,Path("/tmp"),stdout,"",0)
    assert any(f.entity_type==EntityType.COURT_CASE and f.value=="Doe v. Example" for f in res.findings)
