with open('C:/Users/N V/Documents/GitHub/aletheia/PROJECT_MANIFEST.json', 'r') as f:
    content = f.read()

old = """      "verification_status": "unknown",
      "last_audited": "2026-10-12T12:00:00Z",
      "note": "Synthetic fixture parser and Docker health smoke pending CI run; fixture file: tests/fixtures/ip_intelligence.json. No live API lookups have occurred." """

new = """      "verification_status": "verified-fixture",
      "last_audited": "2026-10-12T12:00:00Z",
      "note": "Synthetic fixture parser and Docker health smoke passed in CI run 38303951248 on commit 7f06d100930fc7457774aca7112762a889e95b86 (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38303951248). Raw evidence: PARSER PREFLIGHT: PASS \u2014 34/34 adapters have parser coverage; 152 passed, 1 warning in 12.87s; DOCKER CAPTURE: PASS \u2014 35/35 cases captured. Fixture file: tests/fixtures/ip_intelligence.json. No live API lookups have occurred." """

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/N V/Documents/GitHub/aletheia/PROJECT_MANIFEST.json', 'w') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Pattern not found')
    idx = content.find('"verification_status": "unknown"')
    if idx >= 0:
        print('Found at:', idx)
        print(repr(content[idx:idx+300]))