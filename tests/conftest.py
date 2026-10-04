from pathlib import Path

import pytest

from architect_assistant.models import Specification


@pytest.fixture
def specification():
    path = Path(__file__).parents[1] / "examples" / "document-generation.json"
    return Specification.model_validate_json(path.read_text(encoding="utf-8"))
