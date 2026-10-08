from parser_test_marker import parser_test
from uuid import uuid4
from pathlib import Path

from aletheia.adapters.exiftool import ExifToolAdapter
from aletheia.adapters.sherlock import SherlockAdapter
from aletheia.adapters.theharvester import TheHarvesterAdapter
from aletheia.core.models import AdapterRunRequest, Seed, SeedType


@parser_test('sherlock')
def test_sherlock_parser_mock(tmp_path):
    (tmp_path / "sherlock.txt").write_text("https://example.com/u/alice\n", encoding="utf-8")
    a = SherlockAdapter()
    r = a.parse(AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType.USERNAME, value="alice")), tmp_path, "", "", 0)
    assert any(f.value == "https://example.com/u/alice" for f in r.findings)


@parser_test('theHarvester')
def test_theharvester_parser_mock(tmp_path):
    (tmp_path / "harvest.jsonl").write_text('{"host":"a.example.com","email":"a@example.com"}\n', encoding="utf-8")
    a = TheHarvesterAdapter()
    r = a.parse(AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType.DOMAIN, value="example.com")), tmp_path, "", "", 0)
    values = {f.value for f in r.findings}
    assert "a.example.com" in values
    assert "a@example.com" in values


@parser_test('exiftool')
def test_exiftool_parser_mock(tmp_path):
    a = ExifToolAdapter()
    r = a.parse(AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType.FILE_PATH, value="/tmp/x.jpg")), tmp_path,
                '[{"SourceFile":"/work/input.bin","EXIF:Make":"Canon"}]', "", 0)
    assert any(f.value == "Canon" for f in r.findings)
