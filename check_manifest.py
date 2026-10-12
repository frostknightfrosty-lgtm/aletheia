import json
with open('PROJECT_MANIFEST.json', 'r') as f:
    manifest = json.load(f)
for entry in manifest['tool_inventory']:
    if entry.get('name') == 'government_records_us':
        print('verification_status:', entry['verification_status'])
        print('last_audited:', entry['last_audited'])
        print('note:', entry['note'][:200])
        break