import os
from unittest.mock import patch

from app.cloudrun_manager import _service_name, _image_uri, is_available


def test_service_name_format():
    assert _service_name(1) == "forge-agent-1"
    assert _service_name(42) == "forge-agent-42"


def test_image_uri_format():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": "my-project", "GCP_REGION": "us-central1", "GCP_ARTIFACT_REPO": "forge"}):
        from importlib import reload
        import app.cloudrun_manager as mod
        reload(mod)
        assert "my-project" in mod._image_uri(1)
        assert "agent-1:latest" in mod._image_uri(1)


def test_is_available_without_project_id():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": ""}, clear=False):
        from importlib import reload
        import app.cloudrun_manager as mod
        reload(mod)
        assert mod.is_available() is False
