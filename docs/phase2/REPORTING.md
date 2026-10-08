# Phase 2 - Reporting

The reporting layer emits JSON, PDF, GraphML, and STIX 2.1-shaped JSON artifacts from the same normalized graph.

Every dossier claim carries entity ID, normalized value, confidence, and all `DERIVED_FROM` provenance records available in the graph. The report also includes the Phase 1 checkpoint hash and a canonical report-content SHA-256 anchor.

The PDF is an evidence-oriented technical report, not a guarantee of legal admissibility. Jurisdiction-specific evidence rules, authenticity requirements, and judicial determinations remain outside Aletheia.

STIX output uses standard STIX 2.1 object types where a direct mapping exists (`user-account`, `domain-name`, `url`, `email-addr`, `ipv4-addr`, `ipv6-addr`, `file`, and `observed-data`) and Aletheia `x_` properties for provenance annotations.
