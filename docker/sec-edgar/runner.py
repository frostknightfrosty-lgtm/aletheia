from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request

UA = os.environ.get("ALETHEIA_SEC_USER_AGENT", "Aletheia/0.6.0")


def get(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", "Host": urllib.parse.urlsplit(url).netloc})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("sec-edgar runner ok")
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "name":
        print("usage: runner.py name:<company name> or --health", file=sys.stderr)
        return 2
    query = sys.argv[2].strip()
    if not query:
        return 2
    index = get("https://www.sec.gov/files/company_tickers.json")
    if not isinstance(index, dict):
        raise RuntimeError("unexpected SEC company_tickers response")
    q = query.casefold()
    ranked = []
    for row in index.values():
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", ""))
        score = 1.0 if title.casefold() == q else 0.7 if q in title.casefold() else 0.0
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda x: (-x[0], str(x[1].get("title", ""))))
    companies, filings = [], []
    for score, row in ranked[:3]:
        cik = str(row.get("cik_str", "")).zfill(10)
        name = row.get("title")
        companies.append({"name": name, "cik": cik, "ticker": row.get("ticker"), "match_score": score})
        try:
            sub = get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        except Exception:
            continue
        recent = ((sub.get("filings") or {}).get("recent") or {}) if isinstance(sub, dict) else {}
        keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument", "primaryDocDescription", "items", "stateOfIncorporation"]
        n = min(len(recent.get("accessionNumber", [])), 10)
        for i in range(n):
            acc = recent.get("accessionNumber", [None])[i]
            if not acc:
                continue
            doc = recent.get("primaryDocument", [None])[i]
            archive = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}" if doc else None
            filings.append({
                "accession_number": acc, "filing_date": recent.get("filingDate", [None])[i],
                "report_date": recent.get("reportDate", [None])[i], "form": recent.get("form", [None])[i],
                "primary_document": doc, "items": recent.get("items", [None])[i],
                "state_of_incorporation": recent.get("stateOfIncorporation", [None])[i],
                "company_name": name, "cik": cik, "filing_url": archive,
            })
    print(json.dumps({"companies": companies, "filings": filings}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
