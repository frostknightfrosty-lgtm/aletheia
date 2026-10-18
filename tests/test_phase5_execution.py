from pathlib import Path
from uuid import uuid4

from aletheia.adapters.social_geo_image import DeepFaceAdapter
from aletheia.core.models import AdapterRunRequest, Seed, SeedType


def test_image_file_is_staged_into_workspace(tmp_path):
    src=tmp_path/'photo.jpg'; src.write_bytes(b'JPEGTEST')
    ws=tmp_path/'ws'
    request=AdapterRunRequest(run_id=uuid4(),seed=Seed(type=SeedType.IMAGE,value=str(src)),legal_only=True)
    cmd=DeepFaceAdapter().build_command(request, ws)
    staged=ws/'input.jpg'
    assert staged.read_bytes()==b'JPEGTEST'
    # The image ENTRYPOINT supplies `python /opt/runner.py` and the mount puts
    # the workspace at /work; the command is the container-side path only. The
    # old form repeated the entrypoint's script and passed a host path
    # (run 39120709419 era) and could never have executed.
    assert cmd==['/work/input.jpg']
