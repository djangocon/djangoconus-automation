from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import TestCase

from sendy.models import Brand, List
from titowebhooks.models import TitoWebhookEvent


@pytest.mark.django_db
class TestSendToSendyCommand(TestCase):
    def setUp(self):
        # Create a test brand and list
        self.brand = Brand.objects.create(brand_id=1, name="Test Brand")
        self.sendy_list = List.objects.create(brand=self.brand, list_id="test-list-123", name="Test List", default=True)

        # Create test webhook events
        self.event1 = TitoWebhookEvent.objects.create(
            trigger="ticket.created", payload={"email": "test1@example.com", "first_name": "John", "last_name": "Doe"}
        )
        self.event2 = TitoWebhookEvent.objects.create(
            trigger="ticket.created", payload={"email": "test2@example.com", "first_name": "Jane", "last_name": "Smith"}
        )
        self.event_no_email = TitoWebhookEvent.objects.create(
            trigger="ticket.created", payload={"first_name": "No", "last_name": "Email"}
        )

    @patch("titowebhooks.management.commands.send_to_sendy.async_task")
    def test_send_all_events(self, mock_async_task):
        """Test sending all events when no PKs specified."""
        call_command("send_to_sendy")

        # Should call async_task twice (for events with emails)
        assert mock_async_task.call_count == 2

        # Check the calls were made with correct arguments
        calls = mock_async_task.call_args_list
        assert calls[0][0] == ("sendy.utils.send_to_sendy",)
        assert calls[0][1] == {"email": "test1@example.com", "name": "John Doe", "campaign_id": "test-list-123"}
        assert calls[1][0] == ("sendy.utils.send_to_sendy",)
        assert calls[1][1] == {"email": "test2@example.com", "name": "Jane Smith", "campaign_id": "test-list-123"}

    @patch("titowebhooks.management.commands.send_to_sendy.async_task")
    def test_send_specific_events(self, mock_async_task):
        """Test sending specific events by PKs."""
        call_command("send_to_sendy", pks=[self.event1.pk])

        # Should only call async_task once
        assert mock_async_task.call_count == 1

        # Check it was called with correct arguments
        call_args = mock_async_task.call_args
        assert call_args[0] == ("sendy.utils.send_to_sendy",)
        assert call_args[1] == {"email": "test1@example.com", "name": "John Doe", "campaign_id": "test-list-123"}

    @patch("titowebhooks.management.commands.send_to_sendy.async_task")
    def test_no_default_lists(self, mock_async_task):
        """Test behavior when no default Sendy lists exist."""
        self.sendy_list.default = False
        self.sendy_list.save()

        call_command("send_to_sendy")

        # Should not call async_task at all
        assert mock_async_task.call_count == 0

    @patch("titowebhooks.management.commands.send_to_sendy.async_task")
    def test_event_without_email(self, mock_async_task):
        """Test that events without email are skipped."""
        call_command("send_to_sendy", pks=[self.event_no_email.pk])

        # Should not call async_task for event without email
        assert mock_async_task.call_count == 0
