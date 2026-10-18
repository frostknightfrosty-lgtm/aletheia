# Jurisdiction warnings (informational)

When a seed or a finding indicates a strong-privacy jurisdiction, a minor,
health data, or a protected-class context, a run records an informational
warning. This implements the sensitive-behavior requirement from
`docs/PROJECT_DIRECTION.md`.

## What the warnings are — and are not

- **Informational only.** They never gate, block, slow, or alter a run. An empty
  or warning-heavy result changes nothing about which adapters run.
- **Heuristic.** They are pattern matches over the attributes a run happened to
  collect. Both false positives and false negatives are expected; the recorded
  signal says exactly what matched so an operator can re-check by hand.
- **Not a legal determination.** The warning text says so explicitly, and the
  report repeats it. Nothing here decides whether a collection is lawful.

## Triggers

| Kind | Trigger |
| --- | --- |
| `strong_privacy_jurisdiction` | A seed value, or an attribute named `country`, `country_code`, `address_country`, `location_country`, `nationality`, or `jurisdiction`, matches the documented list: EU/EEA member states, the United Kingdom, Switzerland, and the regime names (GDPR, EU, EEA). Two-letter codes match as tokens only. |
| `minor_indicators` | An attribute `minor`/`is_minor` set to true, or a computable age below 18 (from `age`, `birth_year`, or an ISO `birthdate`/`birth_date`/`dob`, computed at the current UTC year). |
| `health_data_indicators` | An attribute key named `health`, `health_data`, `medical`, `medical_data`, `diagnosis`, `medication`, `patient`, `condition(s)`, or a topical attribute (`industry`, `sector`, `category`, `topic`, `record_type`) whose value contains a health keyword (health, medical, patient, diagnosis, clinic, hospital, medication, therapy, pharma). |
| `protected_class_indicators` | An attribute key named `religion`, `religious_affiliation`, `faith`, `ethnicity`, `ethnic_group`, `race`, `racial_group`, `sexual_orientation`, `union_membership`, `trade_union`, `disability`/`disabilities`, or a topical attribute whose value contains a protected-class keyword. |

Warnings are deduplicated by `(kind, subject, signal)`. Subjects are
`seed:<index>` or `entity:<type>=<value>`.

## Where they are recorded

- **Audit trail:** one `jurisdiction_warning` event per warning, appended during
  `aletheia phase2` before the `phase2_finalize` event (hash-chained like every
  other event).
- **Report:** `report.json` field `jurisdiction_warnings` and a "Jurisdiction
  Warnings (informational)" section in `report.pdf`.
- **Manifest:** `jurisdiction_warning_count`.

## Honest limits

- Free-text values elsewhere in the graph are not scanned; only the attribute
  keys and topical fields above. This keeps the signal small enough to audit but
  misses contexts expressed in prose.
- The jurisdiction list is a static, bias-toward-inclusion heuristic, not an
  ISO-3166 dataset or a legal-regime database.
- A "minor" signal derived from `birth_year` is exact only at yearly
  granularity; `birthdate`-based ages are exact to the day. Neither verifies the
  underlying data.
