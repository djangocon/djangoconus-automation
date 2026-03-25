from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import TestCase

from emailoctopus.models import Campaign
from titowebhooks.models import TitoWebhookEvent


@pytest.mark.django_db
class TestSendToEmailOctopusCommand(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(list_id="test-list-123", name="Test Campaign", default=True)

        self.event1 = TitoWebhookEvent.objects.create(
            trigger="ticket.created", payload={"email": "test1@example.com", "first_name": "John", "last_name": "Doe"}
        )
        self.event2 = TitoWebhookEvent.objects.create(
            trigger="ticket.created",
            payload={"email": "test2@example.com", "first_name": "Jane", "last_name": "Smith"},
        )
        self.event_no_email = TitoWebhookEvent.objects.create(
            trigger="ticket.created", payload={"first_name": "No", "last_name": "Email"}
        )

    @patch("titowebhooks.management.commands.send_to_emailoctopus.async_task")
    def test_send_all_events(self, mock_async_task):
        """Test sending all events when no PKs specified."""
        call_command("send_to_emailoctopus")

        assert mock_async_task.call_count == 2

        calls = mock_async_task.call_args_list
        assert calls[0][0] == ("emailoctopus.utils.send_to_emailoctopus",)
        assert calls[0][1] == {"email": "test1@example.com", "name": "John Doe", "list_id": "test-list-123"}
        assert calls[1][0] == ("emailoctopus.utils.send_to_emailoctopus",)
        assert calls[1][1] == {"email": "test2@example.com", "name": "Jane Smith", "list_id": "test-list-123"}

    @patch("titowebhooks.management.commands.send_to_emailoctopus.async_task")
    def test_send_specific_events(self, mock_async_task):
        """Test sending specific events by PKs."""
        call_command("send_to_emailoctopus", pks=[self.event1.pk])

        assert mock_async_task.call_count == 1

        call_args = mock_async_task.call_args
        assert call_args[0] == ("emailoctopus.utils.send_to_emailoctopus",)
        assert call_args[1] == {"email": "test1@example.com", "name": "John Doe", "list_id": "test-list-123"}

    @patch("titowebhooks.management.commands.send_to_emailoctopus.async_task")
    def test_no_default_lists(self, mock_async_task):
        """Test behavior when no default Email Octopus lists exist."""
        self.campaign.default = False
        self.campaign.save()

        call_command("send_to_emailoctopus")

        assert mock_async_task.call_count == 0

    @patch("titowebhooks.management.commands.send_to_emailoctopus.async_task")
    def test_event_without_email(self, mock_async_task):
        """Test that events without email are skipped."""
        call_command("send_to_emailoctopus", pks=[self.event_no_email.pk])

        assert mock_async_task.call_count == 0
