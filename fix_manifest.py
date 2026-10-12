with open('C:\\Users\\N V\\Documents\\GitHub\\aletheia\\PROJECT_MANIFEST.json', 'r') as f:
    content = f.read()

# Fix the structure - find the exact pattern
old = '''  ],
    "supported_seeds": [
      "username",
      "domain",
      "file_path"
    ],
    "graph_store": "File-backed JSON graph and checkpoint stores are current; production database backends remain future work",
    "durable_orchestrator": "checkpointed local DAG runner in Phase 1; Temporal/Celery integration boundary reserved",
    "reporting": "completed in Phase 2",
    "benchmarking": "not implemented until Phase 7"
  },
  "known_environment_limitations": ['''

new = '''  ],
  "phase_1_scope": {
    "supported_seeds": [
      "username",
      "domain",
      "file_path"
    ],
    "graph_store": "File-backed JSON graph and checkpoint stores are current; production database backends remain future work",
    "durable_orchestrator": "checkpointed local DAG runner in Phase 1; Temporal/Celery integration boundary reserved",
    "reporting": "completed in Phase 2",
    "benchmarking": "not implemented until Phase 7"
  },
  "known_environment_limitations": ['''

if old in content:
    content = content.replace(old, new)
    with open('C:\\Users\\N V\\Documents\\GitHub\\aletheia\\PROJECT_MANIFEST.json', 'w') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Pattern not found')
    # Debug: find the actual content
    idx = content.find('"supported_seeds"')
    if idx >= 0:
        print('Found at:', idx)
        print(repr(content[idx-50:idx+200]))