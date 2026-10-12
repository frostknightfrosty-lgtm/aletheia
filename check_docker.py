import json

with open('PROJECT_MANIFEST.json', 'r') as f:
    manifest = json.load(f)

for entry in manifest['tool_inventory']:
    inv = entry.get('invocation', '')
    has_docker = 'Docker' in inv
    name = entry['name']
    if has_docker:
        print(f'YES: {name}')
    else:
        print(f'NO:  {name}')

print(f'\nTotal with Docker: {sum(1 for e in manifest["tool_inventory"] if "Docker" in str(e.get("invocation", "")))}')