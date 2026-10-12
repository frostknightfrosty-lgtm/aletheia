import json

path = r"C:\Users\N V\Documents\GitHub\aletheia\PROJECT_MANIFEST.json"
with open(path, "r") as f:
    manifest = json.load(f)

# Find ip_intelligence in the tool_inventory list
ip_intel_idx = None
for i, entry in enumerate(manifest["tool_inventory"]):
    if entry.get("name") == "ip_intelligence":
        ip_intel_idx = i
        break

print(f"ip_intelligence found at index: {ip_intel_idx}")

# Insert government_records_us after ip_intelligence
gov_entry = {
    "name": "government_records_us",
    "upstream": "https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/government_records_us",
    "license": "Composite adapter; sub-sources are US federal/state public data APIs",
    "version_pin": "1.0",
    "invocation": "HTTPS APIs via dedicated Docker runner (aletheia/gov-records-us:v1)",
    "input_types": ["name", "company_name", "bank_name", "vin", "person_name", "lobbyist_name"],
    "output_schema": "GovernmentRecordsUSFinding[]",
    "legal_notes": "Composite adapter querying 11 US government records sub-sources via their public APIs. Sub-sources requiring free API keys (OCC, SAM.gov, FOIA.gov) will be skipped if the corresponding environment variable is not set. Skip reasons are recorded in output. Tier 1 sub-sources (FINRA, FDIC, Federal Reserve, USAspending, LDA anonymous, NHTSA, BOP, NYC Open Data anonymous) run without keys. All sub-sources are public government data APIs; no unauthorized access, CAPTCHA bypass, or credential use against third-party accounts. Rate limits are per-sub-source; the adapter queries each at most once per run. Respect provider quotas and 429 responses.",
    "network": "required",
    "last_audited": "2026-10-13T00:00:00Z",
    "verification_status": "unverified-fixture",
    "fixture_provenance": "synthetic",
    "legal_tier": 1,
    "enabled_by_default": True,
    "disabled_reason": None,
    "batch_grouping": "government_records_us",
    "requires_key": False,
    "sub_sources": [
        {"name": "finra-brokercheck", "requires_key": False},
        {"name": "fdic-bankfind", "requires_key": False},
        {"name": "fed-enforcement", "requires_key": False},
        {"name": "occ-enforcement", "requires_key": False},
        {"name": "usaspending", "requires_key": False},
        {"name": "sam-gov", "requires_key": True, "key_cost": "free"},
        {"name": "lda", "requires_key": False},
        {"name": "foia-gov", "requires_key": True, "key_cost": "free"},
        {"name": "nhtsa-vpic", "requires_key": False},
        {"name": "bop-inmate-locator", "requires_key": False},
        {"name": "nyc-open-data", "requires_key": False}
    ]
}

# Insert after ip_intelligence
manifest["tool_inventory"].insert(ip_intel_idx + 1, gov_entry)

with open(path, "w") as f:
    json.dump(manifest, f, indent=2)

print("Done! government_records_us added to manifest.")
print(f"Total entries in tool_inventory: {len(manifest['tool_inventory'])}")