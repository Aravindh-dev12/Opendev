import os
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def project(tmp_path):
    dst = tmp_path / "proj"
    for d in ("company", "erp", "tasks"):
        shutil.copytree(os.path.join(ROOT, d), dst / d, ignore=shutil.ignore_patterns("state.json", "__pycache__"))
    return str(dst)
