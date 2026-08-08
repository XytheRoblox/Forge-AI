from app.registry import MODEL_OPTIONS
from app.docker_manager import PROVIDER_ENV_VAR


def test_featherless_models_in_registry():
    featherless_models = [m for m in MODEL_OPTIONS if m.provider == "featherless"]
    assert len(featherless_models) >= 5
    for model in featherless_models:
        assert model.available is True
        assert model.provider_label == "Featherless AI"
        assert "/" in model.model_id  # HuggingFace-style org/model format


def test_featherless_in_provider_env_var():
    assert "featherless" in PROVIDER_ENV_VAR
    assert PROVIDER_ENV_VAR["featherless"] == "FEATHERLESS_API_KEY"
