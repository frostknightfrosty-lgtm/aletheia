#!/usr/bin/env python3
"""Aletheia driver for VENOM (ghostport-sudo/VENOM v7.0).

Modes:
  run_venom.py --type email|username|domain <target>
  run_venom.py --health
  run_venom.py --selftest

Scoped review: docker/venom/RATE_LIMITS.md. Only the reviewed keyless module
set is imported and invoked: 5 modules for email seeds, 12 for username
seeds, 13 for domain seeds (29 upstream module classes, 30 invocations —
psbdmp runs for both email and username seeds). Never imported or invoked:
every keyed service (HIBP, BreachDirectory, LeakCheck, OSINTLeak, IntelX,
Phonebook, Hunter, NumLookup, and the Leak-Lookup module with its borrowed
public key), the Dehashed HTML scrape, the plain-HTTP ip-api module, the
raw-socket SSL/RBL modules, VENOM's own Holehe/Google auth-flow probes, the
DuckDuckGo search scrape, the AI agent, the dork/dark-web link generators,
and the web UI.

Deviations from pinned upstream behavior (both fail closed):

* Random browser User-Agent rotation is replaced with a fixed honest
  ``Aletheia/...`` agent. Upstream modules bind ``get_random_user_agent``
  at import time, so each imported module object is patched explicitly and
  the patch is verified before any run.
* ``BaseOSINTModule._request`` hardcodes ``ssl=False`` (and the social sweep
  calls ``session.get(..., ssl=False)`` directly). The driver runs every
  module against a ``ClientSession`` subclass whose ``_request`` forces
  ``ssl=True``, so no module can silently disable certificate verification.

Transport: no proxy of any kind is passed to the modules and no proxy
rotation is performed. The pinned modules use aiohttp with its default
``trust_env=True``, so the container's ``HTTP_PROXY``/``HTTPS_PROXY``
environment variables route live traffic through the egress proxy.
"""

import asyncio
import json
import os
import re
import sys
import threading

CHECKOUT = os.environ.get("VENOM_CHECKOUT", "/opt/venom")
PINNED_COMMIT = "6fa3a483abc9cb0a1d96567e33b2919be59522c6"
CHECKOUT_VERSION = "7.0"
HONEST_UA = "Aletheia/0.9.0 (venom)"

GATHER_TIMEOUT_SECONDS = 150.0
HARD_DEADLINE_SECONDS = 200.0

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$"
)
_IPV4_RE = re.compile(
    r"^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$"
)

# Reviewed module sets per seed type (driver keys). These tuples are checked
# against the reviewed inventory in --selftest so a module cannot be added to
# a run without being reviewed first.
MODULE_KEYS = {
    "email": ("emailrep", "crtsh_email", "psbdmp", "otx_email", "github_commits"),
    "username": (
        "social", "github_user", "github_orgs", "github_commit_emails",
        "gitlab", "npm", "pypi", "keybase", "twitter", "telegram", "steam",
        "psbdmp_u",
    ),
    "domain": (
        "dns", "whois", "ip", "wayback", "crt_subs", "urlscan", "otx_domain",
        "ht_dns", "ht_rev", "pulsedive", "proxycheck", "internetdb", "otx_ip",
    ),
}

# 30 driver bindings over 29 distinct upstream module classes (psbdmp runs for
# both email and username seeds).
EXPECTED_MODULE_BINDINGS = 30
EXPECTED_DISTINCT_CLASSES = 29

# Upstream module keys that must never appear in MODULE_KEYS (reviewed out:
# keyed services, borrowed keys, scraping, raw sockets, auth-flow probes).
EXCLUDED_KEYS = (
    "hibp_breaches", "hibp_pastes", "breach_directory", "leakcheck", "leakcheck_u",
    "leak_lookup", "leak_lookup_u", "intelx_email", "intelx_d", "intelx_u", "intelx_p",
    "osintleak", "osintleak_u", "osintleak_p", "phonebook", "phonebook_u", "phonebook_d",
    "dehashed", "holehe", "google_probe", "password_audit", "web_search",
    "hunter", "phone_carrier", "ssl", "blacklist", "ipgeo", "bgpview",
)

_REAL_STDOUT = sys.stdout
_CACHED_CLASSES = None
_CACHED_SESSION_CLASS = None


def _fixed_user_agent():
    """Replacement for the upstream rotating-user-agent helper."""
    return HONEST_UA


def _pin_file_matches():
    try:
        with open(os.path.join(CHECKOUT, "PINNED_COMMIT"), "r", encoding="utf-8") as handle:
            return handle.read().strip() == PINNED_COMMIT
    except OSError:
        return False


def _upstream_module_objects():
    """The upstream module objects whose ``get_random_user_agent`` bindings exist."""
    if CHECKOUT not in sys.path:
        sys.path.insert(0, CHECKOUT)
    from modules import base as base_mod
    from modules import breach as breach_mod
    from modules import domain as domain_mod
    from modules import email as email_mod
    from modules import username as username_mod

    return (base_mod, breach_mod, domain_mod, email_mod, username_mod)


def _apply_ua_patch(module_objects=None):
    """Replace the rotating user agent with the fixed honest agent; verify it."""
    objects = module_objects if module_objects is not None else _upstream_module_objects()
    for module in objects:
        if hasattr(module, "get_random_user_agent"):
            module.get_random_user_agent = _fixed_user_agent
    return all(
        getattr(module, "get_random_user_agent", None) is _fixed_user_agent
        for module in objects
        if hasattr(module, "get_random_user_agent")
    )


def _module_classes():
    """Import the reviewed upstream module classes; returns key -> class."""
    global _CACHED_CLASSES
    if _CACHED_CLASSES is not None:
        return _CACHED_CLASSES
    if CHECKOUT not in sys.path:
        sys.path.insert(0, CHECKOUT)
    from modules.breach import OTXEmailModule, PSBDMPModule
    from modules.domain import (
        CrtshDomainModule,
        DNSModule,
        HackerTargetPassiveDNSModule,
        HackerTargetReverseIPModule,
        IPResolutionModule,
        OTXDomainModule,
        OTXIPModule,
        ProxyCheckModule,
        PulsediveModule,
        ShodanInternetDBModule,
        URLScanModule,
        WaybackModule,
        WHOISModule,
    )
    from modules.email import CrtshEmailModule, EmailRepModule
    from modules.username import (
        GitHubCommitEmailsModule,
        GitHubEmailCommitsModule,
        GitHubOrgsModule,
        GitHubUserModule,
        GitLabUserModule,
        KeybaseModule,
        NPMUserModule,
        PyPIUserModule,
        SocialEnumerationModule,
        SteamProfileModule,
        TelegramResolveModule,
        TwitterOembedModule,
    )

    _CACHED_CLASSES = {
        "emailrep": EmailRepModule,
        "crtsh_email": CrtshEmailModule,
        "psbdmp": PSBDMPModule,
        "psbdmp_u": PSBDMPModule,
        "otx_email": OTXEmailModule,
        "github_commits": GitHubEmailCommitsModule,
        "social": SocialEnumerationModule,
        "github_user": GitHubUserModule,
        "github_orgs": GitHubOrgsModule,
        "github_commit_emails": GitHubCommitEmailsModule,
        "gitlab": GitLabUserModule,
        "npm": NPMUserModule,
        "pypi": PyPIUserModule,
        "keybase": KeybaseModule,
        "twitter": TwitterOembedModule,
        "telegram": TelegramResolveModule,
        "steam": SteamProfileModule,
        "dns": DNSModule,
        "whois": WHOISModule,
        "ip": IPResolutionModule,
        "wayback": WaybackModule,
        "crt_subs": CrtshDomainModule,
        "urlscan": URLScanModule,
        "otx_domain": OTXDomainModule,
        "otx_ip": OTXIPModule,
        "ht_dns": HackerTargetPassiveDNSModule,
        "ht_rev": HackerTargetReverseIPModule,
        "pulsedive": PulsediveModule,
        "proxycheck": ProxyCheckModule,
        "internetdb": ShodanInternetDBModule,
    }
    return _CACHED_CLASSES


def _verified_session_class():
    """Aiohttp session that never lets a module disable TLS verification."""
    global _CACHED_SESSION_CLASS
    if _CACHED_SESSION_CLASS is not None:
        return _CACHED_SESSION_CLASS
    import aiohttp

    class VerifiedSession(aiohttp.ClientSession):
        @staticmethod
        def _force_verified(kwargs):
            kwargs["ssl"] = True
            return kwargs

        async def _request(self, method, url, **kwargs):
            kwargs = self._force_verified(dict(kwargs))
            return await super()._request(method, url, **kwargs)

    _CACHED_SESSION_CLASS = VerifiedSession
    return VerifiedSession


def _session_forces_verification():
    import aiohttp

    session_class = _verified_session_class()
    return (
        session_class._request is not aiohttp.ClientSession._request
        and session_class._force_verified({"ssl": False}).get("ssl") is True
    )


def _validate_target(target_type, raw):
    value = (raw or "").strip()
    if target_type == "email":
        return value if _EMAIL_RE.match(value) else None
    if target_type == "username":
        return value if _USERNAME_RE.match(value) else None
    if target_type == "domain":
        lowered = value.lower()
        return lowered if _DOMAIN_RE.match(lowered) else None
    return None


def _is_error_result(result):
    if not isinstance(result, dict):
        return False
    status = result.get("Status")
    if isinstance(status, str) and status.startswith(("Protected", "Timeout", "Connection", "Failed", "Error")):
        return True
    return isinstance(result.get("error"), str)


def _is_blocked_result(result):
    status = result.get("Status") if isinstance(result, dict) else None
    return isinstance(status, str) and status.startswith("Protected")


def _derive_status(results):
    if not results:
        return "error"
    if any(_is_blocked_result(result) for result in results.values()):
        return "blocked"
    if all(_is_error_result(result) for result in results.values()):
        return "error"
    return "ok"


async def _execute(target_type, target, state):
    classes = _module_classes()
    session_class = _verified_session_class()
    results = {}

    async with session_class() as session:

        async def run_one(key, action):
            state["stage"] = key
            try:
                return key, await action(session)
            except Exception as exc:  # a module's own run() already catches; belt and braces
                return key, {"Status": "Failed", "error": f"{type(exc).__name__}: {exc}"}

        async def run_module(key, target_value):
            return await run_one(key, classes[key](target_value).run)

        deferred = set()
        if target_type == "username":
            # Needs the repository list from github_user, so it runs after it.
            deferred.add("github_commit_emails")
        elif target_type == "domain":
            # These four modules take the resolved address, not the domain.
            deferred.update(("internetdb", "otx_ip", "proxycheck", "ht_rev"))
        tasks = []
        for key in MODULE_KEYS[target_type]:
            if key in deferred:
                continue
            tasks.append(run_module(key, target))
        pairs = await asyncio.gather(*tasks, return_exceptions=True)
        for item in pairs:
            if isinstance(item, Exception):
                continue
            key, result = item
            results[key] = result

        if target_type == "username":
            repos = []
            profile = results.get("github_user")
            if isinstance(profile, dict) and isinstance(profile.get("repos"), list):
                repos = [repo for repo in profile["repos"] if isinstance(repo, dict) and repo.get("name")]
            if repos:
                module = classes["github_commit_emails"](target, repos=repos[:6])
                key, result = await run_one("github_commit_emails", module.run)
                results[key] = result
            else:
                results["github_commit_emails"] = {"emails": []}

        if target_type == "domain":
            resolved = results.get("ip")
            ip = resolved.get("ip") if isinstance(resolved, dict) else None
            if isinstance(ip, str) and _IPV4_RE.match(ip):
                ip_tasks = [
                    run_module(key, ip)
                    for key in ("internetdb", "otx_ip", "proxycheck", "ht_rev")
                ]
                pairs = await asyncio.gather(*ip_tasks, return_exceptions=True)
                for item in pairs:
                    if isinstance(item, Exception):
                        continue
                    key, result = item
                    results[key] = result
            else:
                for key in ("internetdb", "otx_ip", "proxycheck", "ht_rev"):
                    results[key] = {"status": "skipped", "reason": "the domain did not resolve to an address"}

    return results


def _deadline_abort(state):
    document = {
        "source": "VENOM",
        "sub_source": "venom",
        "target_type": state.get("target_type"),
        "target": state.get("target"),
        "pinned_commit": PINNED_COMMIT,
        "status": "error",
        "deadline_exceeded": True,
        "stage": state.get("stage"),
        "modules": {},
        "error": f"hard deadline of {int(HARD_DEADLINE_SECONDS)}s exceeded",
    }
    _REAL_STDOUT.write(json.dumps(document, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()
    os._exit(3)


def health():
    details = {"pinned_commit": PINNED_COMMIT, "checkout_version": CHECKOUT_VERSION}
    try:
        classes = _module_classes()
        details["module_bindings"] = len(classes)
        details["distinct_classes"] = len(set(classes.values()))
        details["ua_patched"] = _apply_ua_patch()
        details["tls_verified"] = _session_forces_verification()
        details["pin_file"] = _pin_file_matches()
    except Exception as exc:
        sys.stderr.write(f"health check failed: {type(exc).__name__}: {exc}\n")
        print("error")
        return 1
    sys.stderr.write(json.dumps(details, ensure_ascii=False) + "\n")
    if (
        details.get("module_bindings") != EXPECTED_MODULE_BINDINGS
        or details.get("distinct_classes") != EXPECTED_DISTINCT_CLASSES
    ):
        print("error")
        return 1
    if not (details["ua_patched"] and details["tls_verified"] and details["pin_file"]):
        print("error")
        return 1
    print("ok")
    return 0


def selftest(loader=None, patcher=None, session_probe=None):
    checks = []

    def check(name, ok):
        checks.append({"name": name, "ok": bool(ok)})

    report = {
        "venom_selftest": "ok",
        "pinned_commit": PINNED_COMMIT,
        "checks": checks,
    }

    check("pin_file", _pin_file_matches())

    load = loader if loader is not None else _module_classes
    try:
        classes = load()
    except Exception as exc:
        classes = None
        check("module_imports", False)
        report["module_import_error"] = f"{type(exc).__name__}: {exc}"
    else:
        check(
            "module_imports",
            len(classes) == EXPECTED_MODULE_BINDINGS
            and len(set(classes.values())) == EXPECTED_DISTINCT_CLASSES,
        )
        report["module_bindings"] = len(classes)

    patch = patcher if patcher is not None else _apply_ua_patch
    try:
        check("ua_patch", bool(patch()))
    except Exception:
        check("ua_patch", False)

    probe = session_probe if session_probe is not None else _session_forces_verification
    try:
        check("tls_verified", bool(probe()))
    except Exception:
        check("tls_verified", False)

    check(
        "target_validation",
        bool(_validate_target("email", "user@example.com"))
        and not _validate_target("email", "not-an-email")
        and bool(_validate_target("username", "example_user"))
        and not _validate_target("username", "two words")
        and bool(_validate_target("domain", "Example.COM"))
        and not _validate_target("domain", "no-dot")
        and _validate_target("domain", "no-dot") is None,
    )

    expected_keys = {
        "email": ("emailrep", "crtsh_email", "psbdmp", "otx_email", "github_commits"),
        "username": (
            "social", "github_user", "github_orgs", "github_commit_emails",
            "gitlab", "npm", "pypi", "keybase", "twitter", "telegram", "steam",
            "psbdmp_u",
        ),
        "domain": (
            "dns", "whois", "ip", "wayback", "crt_subs", "urlscan", "otx_domain",
            "ht_dns", "ht_rev", "pulsedive", "proxycheck", "internetdb", "otx_ip",
        ),
    }
    check("module_scoping", MODULE_KEYS == expected_keys and len(MODULE_KEYS["email"]) == 5
          and len(MODULE_KEYS["username"]) == 12 and len(MODULE_KEYS["domain"]) == 13)

    check(
        "excluded_scope",
        isinstance(EXCLUDED_KEYS, tuple)
        and len(EXCLUDED_KEYS) >= 28
        and not any(key in MODULE_KEYS[target] for target in MODULE_KEYS for key in EXCLUDED_KEYS),
    )

    if not all(item["ok"] for item in checks):
        report["venom_selftest"] = "fail"
    return report


def main(argv):
    if argv == ["--health"]:
        return health()
    if argv == ["--selftest"]:
        report = selftest()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["venom_selftest"] == "ok" else 1

    if len(argv) != 3 or argv[0] != "--type" or argv[1] not in MODULE_KEYS:
        sys.stderr.write(
            "usage: run_venom.py --type email|username|domain <target> | --health | --selftest\n"
        )
        return 2

    target_type = argv[1]
    target = _validate_target(target_type, argv[2])
    document = {
        "source": "VENOM",
        "sub_source": "venom",
        "target_type": target_type,
        "target": (argv[2] or "").strip(),
        "pinned_commit": PINNED_COMMIT,
        "checkout_version": CHECKOUT_VERSION,
        "user_agent": HONEST_UA,
        "tls_verified": True,
        "status": "error",
        "modules": {},
    }
    if target is None:
        document["status"] = "invalid_target"
        document["error"] = (
            "expected an email address, a 1-32 character [A-Za-z0-9_.-] username, "
            "or a registrable domain"
        )
        print(json.dumps(document, ensure_ascii=False))
        return 2

    try:
        classes = _module_classes()
        patched = _apply_ua_patch()
        _verified_session_class()
    except Exception as exc:
        document["error"] = f"driver setup failed: {type(exc).__name__}: {exc}"
        print(json.dumps(document, ensure_ascii=False))
        return 1
    if not patched:
        document["error"] = (
            "user-agent patch target missing in the pinned checkout; refusing to run (fail closed)"
        )
        print(json.dumps(document, ensure_ascii=False))
        return 1
    if len(classes) != EXPECTED_MODULE_BINDINGS:
        document["error"] = "reviewed module inventory does not match the pinned checkout; refusing to run"
        print(json.dumps(document, ensure_ascii=False))
        return 1

    state = {"target_type": target_type, "target": target, "stage": "setup"}
    watchdog = threading.Timer(HARD_DEADLINE_SECONDS, _deadline_abort, args=(state,))
    watchdog.daemon = True
    watchdog.start()
    try:
        try:
            results = asyncio.run(
                asyncio.wait_for(_execute(target_type, target, state), timeout=GATHER_TIMEOUT_SECONDS)
            )
        except asyncio.TimeoutError:
            document["error"] = f"module runs timed out after {int(GATHER_TIMEOUT_SECONDS)}s"
            results = {}
        except Exception as exc:
            document["error"] = f"{type(exc).__name__}: {exc}"
            results = {}
    finally:
        watchdog.cancel()

    document["reported_modules"] = sorted(results.keys())
    document["modules"] = results
    status = _derive_status(results)
    document["status"] = status
    print(json.dumps(document, ensure_ascii=False))
    return 0 if status in {"ok", "blocked"} else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
