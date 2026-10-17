import tempfile
from pathlib import Path

import pytest

from glucotwin.config import MODEL_DIR, SYNTH_DIR

needs_artifacts = pytest.mark.skipif(not (MODEL_DIR / "manifest.json").exists() or not (SYNTH_DIR / "fhir").exists(),
                                     reason="run `make data train` first")


@pytest.fixture(scope="session")
def twin():
    from glucotwin.twin.engine import WardTwin
    from glucotwin.twin.store import Store
    return WardTwin(store=Store(Path(tempfile.mkdtemp()) / "t.db"))


@pytest.fixture(scope="session")
def ward():
    from glucotwin.ingest.fhir_bulk import load_ward
    return load_ward()
