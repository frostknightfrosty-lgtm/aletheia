import json

# 1. Fix pytest-mock in requirements
with open('requirements-test.txt', 'r') as f:
    content = f.read()
if 'pytest-mock' not in content:
    with open('requirements-test.txt', 'a') as f:
        f.write('pytest-mock>=3.10\n')
    print('Added pytest-mock to requirements-test.txt')
else:
    print('pytest-mock already in requirements-test.txt')

# 2. Fix manifest verification_status to 'unknown' (allowed value)
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

# 3. Update test_project_manifest.py expected adapter count to 36 (was 35)
# Wait, let me check what the count should be
with open('PROJECT_MANIFEST.json', 'r') as f:
    manifest = json.load(f)
docker_adapters = [e for e in manifest['tool_inventory'] if 'Docker' in str(e.get('invocation', ''))]
print(f'Docker adapters count: {len(docker_adapters)}')
# The test checks for adapters with "Docker" in invocation
# Let me update the test if needed