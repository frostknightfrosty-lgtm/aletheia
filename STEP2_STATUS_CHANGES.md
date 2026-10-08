# Step 2 — Manifest Status Changes

Every manifest entry previously carried only the legacy `verified` date. Step 2 removes that field completely and adds explicit `last_audited` plus `verification_status`. Each line below records the new machine status and why it is honest; none constitutes a live-run claim.

| Entry | New verification_status | Why |
|---|---|---|
| sherlock | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_adapters.py::test_sherlock_parser_mock |
| theHarvester | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_adapters.py::test_theharvester_parser_mock |
| exiftool | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_adapters.py::test_exiftool_parser_mock |
| rapidfuzz | verified-source-read | Internal dependency; upstream package/version documentation was reviewed. No adapter execution is implied. |
| reportlab | verified-source-read | Internal dependency; upstream package/version documentation was reviewed. No adapter execution is implied. |
| amass | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_amass_parser |
| subfinder | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_subfinder_parser |
| assetfinder | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_assetfinder_parser; tests/fixtures/assetfinder.txt |
| dnsx | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_dnsx_parser |
| massdns | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_massdns_parser |
| dnsrecon | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_dnsrecon_parser; tests/fixtures/dnsrecon.json |
| fierce | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_fierce_parser; tests/fixtures/fierce.txt |
| shodan | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_shodan_parser |
| censys | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_censys_parser |
| crt.sh | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase3_adapters.py::test_crtsh_parser |
| maigret | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_maigret_parser |
| holehe | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_holehe_parser |
| h8mail | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_h8mail_parser |
| hibp | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_hibp_parser |
| phoneinfoga | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_phoneinfoga_parser |
| libphonenumber | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_libphonenumber_parser |
| twilio-lookup | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase4_adapters.py::test_twilio_lookup_parser |
| instaloader | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_instaloader_parser |
| reddit-api | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_reddit_api_parser |
| youtube-api | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_youtube_api_parser |
| overpass | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_overpass_parser |
| suncalc | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_suncalc_parser |
| deepface | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_deepface_parser |
| insightface | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_insightface_parser |
| google-vision | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase5_adapters.py::test_google_vision_parser |
| sec-edgar | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase6_adapters.py::test_sec_edgar_parser |
| gleif | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase6_adapters.py::test_gleif_parser |
| opencorporates | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase6_adapters.py::test_opencorporates_parser |
| opensanctions | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase6_adapters.py::test_opensanctions_parser |
| courtlistener | verified-fixture | Passing Step 1 parser fixture coverage: tests/test_phase6_adapters.py::test_courtlistener_parser |
