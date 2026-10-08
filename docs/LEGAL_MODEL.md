# Legal / compliance boundary — Phase 1

Aletheia is a provenance-first orchestrator, not a bypass mechanism. Phase 1 accepts only `legal_only=true` investigations.

The adapter layer must reject access-control circumvention, credentialed access without explicit authorization, CAPTCHA bypasses, paywall bypasses, and active target-facing actions outside an explicitly authorized scope.

TheHarvester is deliberately invoked with a small passive-source set (`crtsh,certspotter`) and without DNS resolution (`-r`), screenshots, target path probing, or other active actions. Upstream documents the passive/active distinction and warns that active actions require explicit authorization.

Networked adapters accept an operator-configured HTTP/SOCKS proxy where the upstream tool supports it. This is transport configuration, not anonymity or authorization.

A production deployment should enforce egress policy outside the application process (for example, an audited proxy or network telemetry layer) so the claim “every outbound request is logged” can be made from observed network events rather than inferred from adapter invocations.
