import base64
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.test import TestCase, override_settings

TEST_PAYLOAD = {
    "_type": "ticket",
    "id": 9463489,
    "test_mode": True,
    "name": "Test User",
    "first_name": "Test",
    "last_name": "User",
    "email": "test@example.com",
    "event": {
        "_type": "event",
        "id": 1085033,
        "title": "Test Event",
        "account_slug": "defna",
        "slug": "test-event",
        "start_date": None,
        "end_date": None,
    },
}

TEST_SECURITY_TOKEN = "test-security-token"


def make_signature(payload_bytes, token):
    return base64.b64encode(hmac.new(token.encode(), payload_bytes, hashlib.sha256).digest()).decode().strip()


@pytest.mark.django_db
class TestTitoWebhookView(TestCase):
    def _post_webhook(self, payload_bytes, headers=None):
        default_headers = {
            "HTTP_X_WEBHOOK_NAME": "ticket.created",
            "HTTP_X_WEBHOOK_ENDPOINT_ID": "12345",
        }
        default_headers.update(headers or {})
        return self.client.post(
            "/titowebhook/",
            data=payload_bytes,
            content_type="application/json",
            **default_headers,
        )

    @override_settings(TITO_SECURITY_TOKEN="")
    @patch("titowebhooks.views.async_task")
    def test_webhook_without_token_configured(self, mock_async_task):
        """When no security token is configured, webhooks are accepted without signature."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        response = self._post_webhook(payload_bytes)
        assert response.status_code == 200

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_valid_signature(self, mock_async_task):
        """When security token is configured, valid signatures are accepted."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        signature = make_signature(payload_bytes, TEST_SECURITY_TOKEN)
        response = self._post_webhook(payload_bytes, headers={"HTTP_TITO_SIGNATURE": signature})
        assert response.status_code == 200

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_invalid_signature(self, mock_async_task):
        """When security token is configured, invalid signatures are rejected."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        response = self._post_webhook(payload_bytes, headers={"HTTP_TITO_SIGNATURE": "invalid"})
        assert response.status_code == 403

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_missing_signature(self, mock_async_task):
        """When security token is configured, missing signatures are rejected."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        response = self._post_webhook(payload_bytes)
        assert response.status_code == 403

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_wrong_token_signature(self, mock_async_task):
        """Signature computed with wrong token is rejected."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        signature = make_signature(payload_bytes, "wrong-token")
        response = self._post_webhook(payload_bytes, headers={"HTTP_TITO_SIGNATURE": signature})
        assert response.status_code == 403
