# Rate Limits, Authentication and Scope: researcher_ids

`researcher_ids` is a two-sub-source composite adapter. Both sub-sources are keyless public HTTPS APIs; no credential, account, email address, or registration is involved. The runner sends a descriptive `User-Agent` and makes bounded, single-shot queries only.

## Sub-source summary

| Sub-source | Input | Endpoint used | Auth | Documented limit / policy | Data licence | Official documentation |
|---|---|---|---|---|---|---|
| wikidata | person name | `GET https://www.wikidata.org/w/api.php` with `action=wbsearchentities`, then at most two `action=wbgetentities` reads | None (public) | Wikimedia API etiquette asks for a descriptive User-Agent and bounded requests; the runner sends one search (max 5 hits) plus at most two entity reads (hits plus at most 40 referenced IDs), with `maxlag=5`, a 30-second timeout, no retries, and no pagination | Wikidata data: CC0 1.0 | https://www.wikidata.org/wiki/Wikidata:Data_access and https://www.mediawiki.org/wiki/API:Etiquette |
| orcid | person name | `GET https://pub.orcid.org/v3.0/expanded-search/` with `q=<fielded-name-query>&rows=5` | None (public API) | ORCID publishes a public API rate limit of 24 requests/second; the runner makes one request per run (max 5 rows), with a 30-second timeout, no retries, and no pagination | ORCID public data: CC0 1.0 | https://info.orcid.org/documentation/api-tutorials/api-tutorial-search/ and https://info.orcid.org/documentation/api-reference/ |

## Query contract

- The adapter accepts a `person_name` seed only.
- The runner trims and collapses whitespace, rejects control characters and embedded double quotes/backslashes, and bounds the input to 120 characters.
- Wikidata receives the full name as `search=<name>` with `language=en`, `type=item`, `limit=5`.
- ORCID receives a fielded query when the name has at least two tokens: `given-names:"<first>" AND family-name:"<last>"`. A one-token name uses the documented free-text field: `text:"<name>"`. Middle names are not guessed into the ORCID query. The normalized document records the query mode.
- ORCID's public search is fuzzy and relevance-ranked. The returned `num-found` can be large even when the top rows are unrelated; only the top five rows are recorded, and the run finding records both `num-found` and `returned`.

## Data minimization

Only public fields are normalized:

- Wikidata: QID, label, description, aliases, instance-of, occupation, birth date/place, citizenship, gender, given/family name, public external identifiers (ORCID, VIAF, ISNI, GND), official website, and public Twitter username.
- ORCID: ORCID iD, given/family/credit name, other names, and public institution names.

ORCID search responses can contain an `email` array. The runner deliberately excludes it: the normalized document never contains an email address or any private profile field. No ORCID biography, keyword, or works list is fetched.

## Interpretation limits

- A name search is a lead, not proof of identity. Common names collide, and neither service asserts that a row is the person the operator intended.
- Wikidata ranks by its own search relevance; ORCID ranks by its own relevance. The adapter preserves the source order but never merges a Wikidata QID with an ORCID iD automatically.
- ORCID iDs and Wikidata QIDs are public persistent identifiers, not secrets. They are emitted so a human can review the source record; the adapter does not assert that two identifiers denote the same person.

## Version pins

Neither sub-source is a locally installed package, so there is no artefact commit to pin. The reviewed contracts are the Wikidata Action API and the ORCID public API v3.0, reviewed on 2026-10-20. The image is `python:3.13-slim-bookworm`; the adapter descriptor is pinned at `version_pin="1.0 (public API contracts reviewed 2026-10-20)"`.

## Verification

- No live target is on file for this adapter. Verification is fixture-based: a synthetic combined normalized document in `tests/fixtures/researcher_ids.json`, parser tests, offline driver self-tests, and a Docker health smoke under `--network none`.
- The `--normalize` image case re-validates a synthetic combined document offline. It performs no network access.
- `--health` performs no network access; it prints exactly `ok` on stdout and a JSON contract summary on stderr.
