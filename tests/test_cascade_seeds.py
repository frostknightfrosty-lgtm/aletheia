"""Tests for seed autodetection, canonicalization, dedup, and multi-seed wiring.

Everything here is pure detection logic plus one ``create_run`` wiring test:
no Docker, no network.
"""

from __future__ import annotations

from aletheia.cascade.seeds import canonicalize_seed, dedupe_seeds, detect_seeds
from aletheia.core.models import Seed, SeedType
from aletheia.core.orchestrator import Orchestrator

GOLDEN_TEXT = (
    "Reach me at alice@Example.COM or https://Example.com/u/alice, "
    "mirror example.org. Server 8.8.8.8. "
    "BTC 1BoatSLRHtKNngkdXEeobR76b53LETtpyT "
    "ETH 0x52908400098527886E0F7030069857D2E4169EE7. "
    "Phone +1 (555) 123-4567 or 555-987-6543. VIN 1HGCM82633A004352. Ping @alice_dev."
)


def test_detect_seeds_golden_classes_in_first_appearance_order():
    detected = [(seed.type.value, seed.value) for seed in detect_seeds(GOLDEN_TEXT)]
    assert detected == [
        ("email", "alice@example.com"),
        ("url", "https://example.com/u/alice"),
        ("domain", "example.org"),
        ("ip", "8.8.8.8"),
        ("crypto_address", "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"),
        ("crypto_address", "0x52908400098527886e0f7030069857d2e4169ee7"),
        ("phone", "+15551234567"),
        ("phone", "5559876543"),
        ("vin", "1HGCM82633A004352"),
        ("username", "alice_dev"),
    ]


def test_detect_seeds_does_not_guess_prose():
    noise = (
        "Ratio 3.14, mixed 1.618, version 1.2.3. See report.pdf and notes.docx. "
        "Call 555-0100 for details or ext. 555. mailto: alice@localhost does not resolve. "
        "Not an address: 999.999.999.999. The end."
    )
    assert detect_seeds(noise) == []


def test_detect_seeds_never_double_reports_a_host():
    seeds = detect_seeds("profile https://example.com/u/alice and mail bob@example.com")
    assert [(seed.type.value, seed.value) for seed in seeds] == [
        ("url", "https://example.com/u/alice"),
        ("email", "bob@example.com"),
    ]


def test_detect_seeds_dedupes_case_and_repeat_variants():
    seeds = detect_seeds("Example.COM then example.com. then @ALICE and @alice again")
    assert [(seed.type.value, seed.value) for seed in seeds] == [
        ("domain", "example.com"),
        ("username", "alice"),
    ]


def test_canonicalization_units():
    cases = [
        (Seed(type=SeedType.USERNAME, value="@Frost2233"), "frost2233"),
        (Seed(type=SeedType.EMAIL, value="Alice@Example.COM"), "alice@example.com"),
        (Seed(type=SeedType.DOMAIN, value="ExAmPle.CoM."), "example.com"),
        (Seed(type=SeedType.DOMAIN, value="m\u00fcnchen.de"), "xn--mnchen-3ya.de"),
        (Seed(type=SeedType.PHONE, value="+1 (555) 123-4567"), "+15551234567"),
        (Seed(type=SeedType.PHONE, value="0044 20 7123 4567"), "+442071234567"),
        (Seed(type=SeedType.IP, value="8.8.8.8"), "8.8.8.8"),
        (Seed(type=SeedType.VIN, value="1hgcm82633a004352"), "1HGCM82633A004352"),
        (
            Seed(type=SeedType.CRYPTO_ADDRESS, value="0x52908400098527886E0F7030069857D2E4169EE7"),
            "0x52908400098527886e0f7030069857d2e4169ee7",
        ),
        (Seed(type=SeedType.NAME, value="Alice   von  Example"), "Alice von Example"),
        (
            Seed(type=SeedType.URL, value="HTTPS://Example.COM/Path?Q=1#frag"),
            "https://example.com/Path?Q=1",
        ),
    ]
    for seed, expected in cases:
        assert canonicalize_seed(seed).value == expected, seed


def test_dedupe_seeds_preserves_first_appearance_order():
    seeds = [
        Seed(type=SeedType.DOMAIN, value="B.example"),
        Seed(type=SeedType.DOMAIN, value="a.example"),
        Seed(type=SeedType.DOMAIN, value="b.EXAMPLE"),
    ]
    assert [seed.value for seed in dedupe_seeds(seeds)] == ["b.example", "a.example"]


def test_detected_seeds_feed_multi_seed_create_run(tmp_path):
    detected = detect_seeds("investigate example.com and alice@example.com")
    assert [(seed.type.value, seed.value) for seed in detected] == [
        ("domain", "example.com"),
        ("email", "alice@example.com"),
    ]
    orch = Orchestrator(tmp_path)
    run_id = orch.create_run(detected)
    manifest = orch.checkpoints.load(run_id)
    assert manifest is not None
    assert manifest["goal"].startswith("Aletheia multi-seed investigation")
    assert [seed["type"] for seed in manifest["seeds"]] == ["domain", "email"]
    assert manifest["pending_seeds"]["theHarvester"] == [0]
    assert manifest["pending_seeds"]["holehe"] == [1]
    for name, indices in manifest["pending_seeds"].items():
        assert indices, name
        for index in indices:
            assert orch.adapters[name].supports(detected[index].type)
