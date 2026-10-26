"""Unauthenticated public-profile lookup with instaloader.

Readiness audit 2026-10-25: Instagram blocks most unauthenticated profile
lookups, and instaloader's default behaviour is to sleep through rate limits and
retry, so the runner hung until the orchestrator's 120 s timeout killed it.
This runner now fails fast instead:

* one connection attempt, a 20 s request timeout and a 45 s overall deadline;
* a rate controller that raises instead of sleeping through a rate limit;
* a blocked lookup (login wall, 429, bad request, connection failure, deadline)
  exits 5 with the reason on stderr, which the adapter records as a skip, so
  "blocked" is never confused with "searched and found nothing";
* a profile that does not exist exits 0 with empty stdout.

No login, cookies or session are ever used.
"""
import json
import signal
import sys

import instaloader
from instaloader.exceptions import (
    ConnectionException,
    LoginRequiredException,
    ProfileNotExistsException,
    QueryReturnedBadRequestException,
    QueryReturnedNotFoundException,
    TooManyRequestsException,
)

DEADLINE_SECONDS = 45
REQUEST_TIMEOUT = 20.0
MAX_SLEEP_SECONDS = 5.0
EXIT_BLOCKED = 5


class FailFastRateController(instaloader.RateController):
    """Raise instead of sleeping through a rate limit longer than a few seconds."""

    def sleep(self, secs):
        if secs > MAX_SLEEP_SECONDS:
            raise TooManyRequestsException(
                f"rate limit would require waiting {secs:.0f}s; failing fast"
            )
        super().sleep(secs)


def _on_deadline(signum, frame):
    raise TimeoutError(f"no response within {DEADLINE_SECONDS}s")


def _blocked(exc):
    first_line = (str(exc).strip().splitlines() or [""])[0][:300]
    print(
        "instagram blocked the unauthenticated profile lookup: "
        f"{type(exc).__name__}: {first_line}".rstrip(": "),
        file=sys.stderr,
    )
    return EXIT_BLOCKED


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 2:
        print("usage: runner.py <username>", file=sys.stderr)
        return 2
    username = sys.argv[1].lstrip("@").strip()
    if not username or "/" in username or " " in username:
        print("invalid username", file=sys.stderr)
        return 2
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _on_deadline)
        signal.alarm(DEADLINE_SECONDS)
    try:
        loader = instaloader.Instaloader(
            quiet=True,
            max_connection_attempts=1,
            request_timeout=REQUEST_TIMEOUT,
            rate_controller=lambda context: FailFastRateController(context),
        )
        profile = instaloader.Profile.from_username(loader.context, username)
        payload = {
            "username": profile.username,
            "profile_url": f"https://www.instagram.com/{profile.username}/",
            "full_name": profile.full_name,
            "biography": profile.biography,
            "followers": profile.followers,
            "followees": profile.followees,
            "mediacount": profile.mediacount,
            "is_private": profile.is_private,
            "is_verified": profile.is_verified,
            "external_url": profile.external_url,
        }
    except (ProfileNotExistsException, QueryReturnedNotFoundException):
        print(f"profile not found: {username}", file=sys.stderr)
        return 0
    except (
        LoginRequiredException,
        TooManyRequestsException,
        QueryReturnedBadRequestException,
        ConnectionException,
        TimeoutError,
    ) as exc:
        return _blocked(exc)
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
