from pr_creator.cursor_utils.config import get_cursor_model


def test_get_cursor_model_defaults_to_cursor_model(monkeypatch):
    monkeypatch.delenv("CURSOR_MODEL", raising=False)
    monkeypatch.delenv("CURSOR_MODEL_CHANGE", raising=False)
    assert get_cursor_model(intent="change") == "gpt-5.2"

    monkeypatch.setenv("CURSOR_MODEL", "base-model")
    assert get_cursor_model(intent="change") == "base-model"
    assert get_cursor_model(intent="review") == "base-model"


def test_get_cursor_model_intent_override(monkeypatch):
    monkeypatch.setenv("CURSOR_MODEL", "base-model")
    monkeypatch.setenv("CURSOR_MODEL_CHANGE", "change-model")

    assert get_cursor_model(intent="change") == "change-model"
    assert get_cursor_model(intent="review") == "base-model"


def test_get_cursor_model_intent_is_sanitized(monkeypatch):
    monkeypatch.setenv("CURSOR_MODEL", "base-model")
    monkeypatch.setenv("CURSOR_MODEL_EVALUATE", "eval-model")
    # Ensure CURSOR_MODEL_CHANGE is not set (to prevent interference)
    monkeypatch.delenv("CURSOR_MODEL_CHANGE", raising=False)

    # ensure we don't accept weird suffixes; we normalize "evaluate\n" -> "EVALUATE"
    assert get_cursor_model(intent=" evaluate\n") == "eval-model"

    # No override for this sanitized key -> fall back to base.
    assert get_cursor_model(intent="../change") == "base-model"
