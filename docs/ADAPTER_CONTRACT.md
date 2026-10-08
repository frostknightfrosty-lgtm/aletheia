# Adapter contract

Each adapter provides:

- `name`
- `license`
- `input_types`
- `output_types`
- `legal_notes`
- `rate_limit`
- `invocation`
- `version_pin`
- `upstream`
- `network_required`
- `docker_image`

Execution is always through `docker run --rm` in Phase 1. The adapter parses only tool-produced artifacts/stdout and converts them into typed `Finding` objects with `Provenance`.

A claim is not considered system-confirmed merely because a tool reports it. Cross-tool entity resolution and re-verification belong to Phase 2.
