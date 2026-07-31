import environs
from django.conf import settings


def test_email_url_parses_smtp_tls(monkeypatch):
    """Documents the EMAIL_URL format expected in production (Coolify env)."""
    monkeypatch.setenv("EMAIL_URL", "submission://user:secret@smtp.example.com:587")
    email = environs.Env().dj_email_url("EMAIL_URL")
    assert email["EMAIL_BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"
    assert email["EMAIL_HOST"] == "smtp.example.com"
    assert email["EMAIL_PORT"] == 587
    assert email["EMAIL_HOST_USER"] == "user"
    assert email["EMAIL_HOST_PASSWORD"] == "secret"
    assert email["EMAIL_USE_TLS"] is True


def test_unconfigured_email_defaults_to_console(monkeypatch):
    monkeypatch.delenv("EMAIL_URL", raising=False)
    email = environs.Env().dj_email_url("EMAIL_URL", default="console://")
    assert email["EMAIL_BACKEND"] == "django.core.mail.backends.console.EmailBackend"


def test_from_addresses_have_defaults():
    assert settings.DEFAULT_FROM_EMAIL
    assert settings.SERVER_EMAIL
