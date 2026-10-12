import json
with open('PROJECT_MANIFEST.json', 'r') as f:
    manifest = json.load(f)
for entry in manifest['tool_inventory']:
    if entry.get('name') == 'government_records_us':
        entry['verification_status'] = 'unverified-fixture'
        entry['note'] = 'Synthetic fixture parser and Docker health smoke to be verified in CI. Fixture file: tests/fixtures/government_records_us.json. No live API lookups have occurred.'
        print('Reverted to unverified-fixture')
        break
with open('PROJECT_MANIFEST.json', 'w') as f:
    json.dump(manifest, f, indent=2)
print('Done')