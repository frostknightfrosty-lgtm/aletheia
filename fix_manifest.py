import json

with open('PROJECT_MANIFEST.json', 'r') as f:
    manifest = json.load(f)

# Find and update government_records_us verification_status
for entry in manifest['tool_inventory']:
    if entry.get('name') == 'government_records_us':
        entry['verification_status'] = 'verified-fixture'
        # Update the note to reflect CI verification
        entry['note'] = 'Synthetic fixture parser and Docker health smoke verified in CI. Fixture file: tests/fixtures/government_records_us.json. No live API lookups have occurred.'
        print(f'Updated {entry["name"]}: verification_status={entry["verification_status"]}')
        break

with open('PROJECT_MANIFEST.json', 'w') as f:
    json.dump(manifest, f, indent=2)
print('Manifest updated')