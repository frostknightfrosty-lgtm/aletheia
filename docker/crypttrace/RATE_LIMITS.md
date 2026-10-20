# crypttrace — scope and limits

- **Upstream:** `bobslayerX/crypttrace`, MIT, version 0.22.0, pinned at commit
  `cf60a88b8be43581186965d160114fdaf3022c62` (2026-10-17). Installed unmodified
  from the pinned checkout; the Aletheia driver is separate.
- **Input:** exactly one Bitcoin address in `/work/address.txt` (`SeedType.
  CRYPTO_ADDRESS`), at most 128 bytes, one line, 14–90 base58/bech32
  characters. The checksum is validated by the package's
  `crypttrace.addresses.validate(address, "btc")`; a rejected address is a
  documented `invalid_target`, never sent upstream.
- **Scope:** Bitcoin only. The driver calls `crypttrace.report.generate(address,
  "btc", depth=2, branching=3, out_dir=/work/reports)` and reads the JSON file
  it writes. The EVM/Tron/Solana/TON paths are not exposed (Ethereum requires
  an Etherscan key and none is registered).
- **Network:** required for a real trace. The only hosts contacted by this
  path are `https://mempool.space/api` (address history, UTXOs) and
  `https://api.coingecko.com/api/v3/simple/price` (optional BTC/USD price for
  the report's USD column). Both are keyless.
- **Upstream throttling and retries:** the fetcher spaces mempool.space calls
  by 0.25 s, caches responses in a local SQLite file under
  `$CRYPTTRACE_HOME`, and retries a 429 with exponential backoff. The container
  home is `/tmp/crypttrace`, so the cache is ephemeral and never leaves the
  container; the Aletheia parser does not retry or cache anything itself.
- **Depth and branching:** depth 2 (the seed plus two counterparty hops) and
  branching 3 (largest three outflows per address). This bounds a run to a
  small number of addresses; no pagination and no full-history crawl.
- **Output bounds:** at most 25 key findings and 25 top counterparties are
  emitted. The upstream `tree_text`, HTML and Markdown are never returned; the
  driver reduces the report to the stable schema in
  `app/aletheia/adapters/crypttrace.py`.
- **Interpretation:** labels, risk scores and “exchange” classifications are
  upstream heuristics and lead generators, **not proof of ownership or
  wrongdoing**. Public-blockchain pseudonymity means reaching an address does
  not identify a person. USD values are indicative and may be absent.
- **Authorization:** a real trace is a network lookup and requires the
  adapter's authorization assertion; no live target is on file for this
  source, so the CI evidence is fixture-based (health, selftest, and parsing of
  a synthetic report under `--network none`). No live trace has been run.
- **No secrets:** no API key is read or stored. `ETHERSCAN_API_KEY` is not
  used by the Bitcoin path.

See `app/aletheia/adapters/crypttrace.py` for the descriptor and parser and
`docker/crypttrace/run_crypttrace.py` for the driver.
