# Step 3 — Fixture Provenance Checkpoint

- Added required `fixture_provenance` to all 33 adapter inventory entries.
- Allowed values are exactly `synthetic` and `captured`.
- All 33 current adapters are `synthetic`; none are captured.
- Internal dependencies rapidfuzz and reportlab are not adapter entries and do not receive this field.
- Loader now fails closed on missing/invalid adapter fixture provenance.
- Audit CSV/Markdown consume `verification_status` and `fixture_provenance` from `PROJECT_MANIFEST.json`.
- No adapter code, parser implementation, or CI workflow semantics were changed for this fixture-provenance step.
