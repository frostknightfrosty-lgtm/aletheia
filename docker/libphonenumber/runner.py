import json
import sys
import phonenumbers
from phonenumbers import carrier, geocoder, timezone


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 2:
        print("usage: runner.py <phone>", file=sys.stderr)
        return 2
    raw = sys.argv[1]
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException as exc:
        print(str(exc), file=sys.stderr)
        return 4
    payload = {
        "input": raw,
        "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        "international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
        "region": geocoder.region_code_for_number(parsed),
        "description": geocoder.description_for_number(parsed, "en"),
        "carrier": carrier.name_for_number(parsed, "en"),
        "timezone": list(timezone.time_zones_for_number(parsed)),
        "number_type": phonenumbers.number_type(parsed),
        "valid": phonenumbers.is_valid_number(parsed),
        "possible": phonenumbers.is_possible_number(parsed),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
