import json

with open('PROJECT_MANIFEST.json', 'r') as f:
    manifest = json.load(f)

for entry in manifest['tool_inventory']:
    if entry.get('name') == 'government_records_us':
        entry['verification_status'] = 'unknown'
        entry['note'] = 'Synthetic fixture parser tests pass (25/25). Docker health check passes. Full CI run pending. Fixture file: tests/fixtures/government_records_us.json. No live API lookups have occurred.'
        print('Fixed manifest verification_status to unknown')
        break

with open('PROJECT_MANIFEST.json', 'w') as f:
    json.dump(manifest, f, indent=2)

print('Done')