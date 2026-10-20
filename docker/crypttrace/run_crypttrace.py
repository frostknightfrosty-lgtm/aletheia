"""Pinned crypttrace driver: one Bitcoin address in, one normalized JSON out.

The upstream package (MIT, commit cf60a88, version 0.22.0) is used through its
``crypttrace.report.generate`` library entry point. Only the Bitcoin path is
exposed: mempool.space needs no API key, while the EVM path requires an
Etherscan key and a different chain. The driver never prints the upstream HTML
or Markdown; it reads the report's JSON sibling and emits a bounded,
deterministic subset.

``--health`` and ``--selftest`` are offline. ``--normalize`` parses a saved
report JSON and is the case used under ``--network none``; the actual trace
runs only when the adapter is explicitly invoked with an address file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

PINNED_COMMIT = "cf60a88b8be43581186965d160114fdaf3022c62"
PIN_REPO = "bobslayerX/crypttrace"
MAX_ADDRESS_BYTES = 128
DEPTH = 2
BRANCHING = 3
MAX_FINDINGS = 25
MAX_COUNTERPARTIES = 25
MAX_ERRORS = 10
NETWORK_HOSTS = (
    "https://mempool.space/api",
    "https://api.coingecko.com/api/v3/simple/price",
)
ADDRESS_RE = re.compile(r"^[A-Za-z0-9]{14,90}$")

_SAMPLE_REPORT: dict[str, Any] = {
    "tool": "crypttrace v0.22.0",
    "generated": "2026-01-01 12:00 UTC",
    "subject": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
    "chain": "btc",
    "traced_asset": "BTC",
    "trace_depth": 2,
    "trace_branching": 3,
    "data_source": "mempool.space",
    "summary": {
        "balance_native": 0.125,
        "native_symbol": "BTC",
        "transfers_analysed": 4,
        "first_seen": "2026-01-01 10:00",
        "last_seen": "2026-01-01 11:00",
        "label": None,
        "type": "unknown",
        "risk_score": 0,
    },
    "assessment": {"assessment": "No labelled entities were reached.", "risk": 0, "confidence": "low"},
    "key_findings": [
        {
            "address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
            "label": "Example exchange",
            "type": "exchange",
            "risk": 70,
            "value_reached": 0.01,
            "symbol": "BTC",
            "usd_reached": 1000.0,
            "memo": None,
        }
    ],
    "top_counterparties": [
        {
            "address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
            "label": "Example exchange",
            "in": 0.0,
            "out": 0.01,
            "txs": 1,
        }
    ],
    "errors": [],
}


def _pin_file() -> Path:
    return Path(os.environ.get("CRYPTTRACE_PIN_FILE", "/opt/crypttrace/PINNED_COMMIT"))


def _checkout() -> str:
    return os.environ.get("CRYPTTRACE_CHECKOUT", "/opt/crypttrace-src")


def _pin_ok() -> bool:
    try:
        lines = _pin_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return bool(lines) and lines[0].strip() == PINNED_COMMIT


def _package():
    import crypttrace  # noqa: PLC0415 - offline health must not import at module load

    return crypttrace


def _package_version() -> str:
    return str(getattr(_package(), "__version__", "unknown"))


def _read_address(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError(f"address file not found: {path}")
    data = path.read_bytes()
    if len(data) > MAX_ADDRESS_BYTES:
        raise ValueError(f"address file exceeds {MAX_ADDRESS_BYTES} bytes")
    text = data.decode("utf-8").strip()
    if "\n" in text or "\r" in text:
        raise ValueError("address file must contain exactly one line")
    if not ADDRESS_RE.fullmatch(text):
        raise ValueError("address must be 14-90 base58/bech32 characters")
    return text


def _library_validate(address: str) -> tuple[bool, str]:
    from crypttrace import addresses  # noqa: PLC0415

    return addresses.validate(address, "btc")


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _normalise(raw: Any) -> dict[str, Any]:
    """Reduce a crypttrace report to the adapter's stable, bounded schema."""
    if not isinstance(raw, dict):
        raise ValueError("report must be a JSON object")
    subject = _text(raw.get("subject"), 128)
    chain = _text(raw.get("chain"), 16)
    if not subject or chain != "btc":
        raise ValueError("report is not a Bitcoin crypttrace report")
    summary_raw = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
    summary = {
        "balance_native": _number(summary_raw.get("balance_native")),
        "native_symbol": _text(summary_raw.get("native_symbol"), 16),
        "transfers_analysed": _number(summary_raw.get("transfers_analysed")),
        "first_seen": _text(summary_raw.get("first_seen"), 32),
        "last_seen": _text(summary_raw.get("last_seen"), 32),
        "label": _text(summary_raw.get("label"), 120),
        "type": _text(summary_raw.get("type"), 32),
        "risk_score": _number(summary_raw.get("risk_score")),
    }
    assessment_raw = raw.get("assessment") if isinstance(raw.get("assessment"), dict) else {}
    assessment = {
        "assessment": _text(assessment_raw.get("assessment"), 800),
        "risk": _number(assessment_raw.get("risk")),
        "confidence": _text(assessment_raw.get("confidence"), 64),
    }
    findings: list[dict[str, Any]] = []
    raw_findings = raw.get("key_findings") if isinstance(raw.get("key_findings"), list) else []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        address = _text(item.get("address"), 128)
        if not address:
            continue
        findings.append({
            "address": address,
            "label": _text(item.get("label"), 120),
            "type": _text(item.get("type"), 32),
            "risk": _number(item.get("risk")),
            "value_reached": _number(item.get("value_reached")),
            "symbol": _text(item.get("symbol"), 16),
            "usd_reached": _number(item.get("usd_reached")),
            "memo": _text(item.get("memo"), 120),
        })
        if len(findings) >= MAX_FINDINGS:
            break
    counterparties: list[dict[str, Any]] = []
    raw_counterparties = raw.get("top_counterparties") if isinstance(raw.get("top_counterparties"), list) else []
    for item in raw_counterparties:
        if not isinstance(item, dict):
            continue
        address = _text(item.get("address"), 128)
        if not address:
            continue
        counterparties.append({
            "address": address,
            "label": _text(item.get("label"), 120),
            "in": _number(item.get("in")),
            "out": _number(item.get("out")),
            "txs": _number(item.get("txs")),
        })
        if len(counterparties) >= MAX_COUNTERPARTIES:
            break
    errors: list[str] = []
    raw_errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    for item in raw_errors:
        text = _text(item, 300)
        if text:
            errors.append(text)
        if len(errors) >= MAX_ERRORS:
            break
    return {
        "source": "crypttrace",
        "status": "partial" if errors else "ok",
        "subject": subject,
        "chain": chain,
        "traced_asset": _text(raw.get("traced_asset"), 16),
        "trace_depth": _number(raw.get("trace_depth")),
        "trace_branching": _number(raw.get("trace_branching")),
        "data_source": _text(raw.get("data_source"), 64),
        "summary": summary,
        "assessment": assessment,
        "key_findings": findings,
        "top_counterparties": counterparties,
        "errors": errors,
    }


def _health() -> int:
    payload: dict[str, Any] = {
        "source": "crypttrace",
        "pinned_commit": PINNED_COMMIT,
        "pin_repo": PIN_REPO,
        "checkout": _checkout(),
        "pin_file": _pin_ok(),
        "network_required": True,
        "chain": "btc",
        "depth": DEPTH,
        "branching": BRANCHING,
        "network_hosts": list(NETWORK_HOSTS),
    }
    try:
        payload["package_version"] = _package_version()
        payload["package_import"] = True
    except Exception as exc:  # noqa: BLE001 - health must report, never raise
        payload["package_version"] = None
        payload["package_import"] = False
        payload["error"] = str(exc)[:300]
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    if payload["pin_file"] and payload["package_import"]:
        print("ok")
        return 0
    return 1


def _selftest() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("pin_file", _pin_ok(), str(_pin_file()))
    try:
        version = _package_version()
        check("package_import", True, version)
    except Exception as exc:  # noqa: BLE001
        version = "unimportable"
        check("package_import", False, str(exc)[:200])
    try:
        from crypttrace import addresses  # noqa: PLC0415

        valid, reason = addresses.validate("1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "btc")
        invalid, _ = addresses.validate("not-a-bitcoin-address", "btc")
        check("address_validation", valid and not invalid, reason if not valid else "bech32/base58")
    except Exception as exc:  # noqa: BLE001
        check("address_validation", False, str(exc)[:200])
    try:
        from crypttrace import chains  # noqa: PLC0415

        symbol = chains.symbol("btc")
        check("chain_registry", symbol == "BTC", f"symbol={symbol}")
    except Exception as exc:  # noqa: BLE001
        check("chain_registry", False, str(exc)[:200])
    try:
        from crypttrace import report  # noqa: PLC0415

        check(
            "report_api",
            callable(getattr(report, "generate", None)) and callable(getattr(report, "collect", None)),
            "report.generate/report.collect",
        )
    except Exception as exc:  # noqa: BLE001
        check("report_api", False, str(exc)[:200])
    try:
        normalised = _normalise(_SAMPLE_REPORT)
        check(
            "normalisation",
            normalised["subject"] == _SAMPLE_REPORT["subject"]
            and len(normalised["key_findings"]) == 1
            and len(normalised["top_counterparties"]) == 1,
            "synthetic report -> bounded schema",
        )
    except Exception as exc:  # noqa: BLE001
        check("normalisation", False, str(exc)[:200])
    check(
        "bounds",
        DEPTH == 2 and BRANCHING == 3 and MAX_FINDINGS == 25 and MAX_COUNTERPARTIES == 25,
        f"depth={DEPTH} branching={BRANCHING}",
    )
    check(
        "network_hosts",
        NETWORK_HOSTS[0] == "https://mempool.space/api" and "coingecko" in NETWORK_HOSTS[1],
        ", ".join(NETWORK_HOSTS),
    )
    print(json.dumps({"crypttrace_selftest": "ok" if all(c["ok"] for c in checks) else "failed",
                      "version": version, "checks": checks}, sort_keys=True, indent=2))
    return 0 if all(item["ok"] for item in checks) else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--health", action="store_true")
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--normalize", metavar="REPORT_JSON")
    parser.add_argument("address_file", nargs="?")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.health:
        return _health()
    if args.selftest:
        return _selftest()
    if args.normalize:
        try:
            raw = json.loads(Path(args.normalize).read_text(encoding="utf-8"))
            print(json.dumps(_normalise(raw), sort_keys=True, indent=2))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"source": "crypttrace", "status": "invalid_report", "error": str(exc)[:300]},
                             sort_keys=True))
            return 2
    if not args.address_file:
        print(json.dumps({"source": "crypttrace", "status": "invalid_target",
                          "error": "one Bitcoin address file is required"}, sort_keys=True))
        return 2
    try:
        address = _read_address(Path(args.address_file))
    except ValueError as exc:
        print(json.dumps({"source": "crypttrace", "status": "invalid_target", "error": str(exc)},
                         sort_keys=True))
        return 2
    try:
        valid, reason = _library_validate(address)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"source": "crypttrace", "status": "error", "error": str(exc)[:300]},
                         sort_keys=True))
        return 1
    if not valid:
        print(json.dumps({"source": "crypttrace", "status": "invalid_target", "error": reason},
                         sort_keys=True))
        return 2
    try:
        from crypttrace import report  # noqa: PLC0415

        out_dir = Path(os.environ.get("CRYPTTRACE_OUT", "/work/reports"))
        paths = report.generate(address, "btc", DEPTH, BRANCHING, out_dir)
        data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        print(json.dumps(_normalise(data), sort_keys=True, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - report errors are output, not a traceback
        print(json.dumps({"source": "crypttrace", "status": "error", "error": str(exc)[:300]},
                         sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
