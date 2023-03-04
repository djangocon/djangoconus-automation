import json

from django.test import TestCase

from titowebhooks.models import TitoWebhookEvent

TEST_PAYLOAD_DATA = """
{
    "_type": "ticket",
    "id": 9463489,
    "test_mode": true,
    "name": "ngrok4 Ngrokker",
    "first_name": "ngrok4",
    "last_name": "Ngrokker",
    "email": "adamfast+ngrok4@gmail.com",
    "phone_number": null,
    "company_name": "The company",
    "reference": "S6Q7-1",
    "price": "100.0",
    "tax": "0.0",
    "price_less_tax": "100.0",
    "slug": "ti_test_poZATmK8dkdvHnJVTfgxdmg",
    "state_name": "complete",
    "gender": "andy",
    "total_paid": "100.0",
    "total_paid_less_tax": "100.0",
    "updated_at": "2023-02-10T03:51:49.000Z",
    "release_price": "100.0",
    "discount_code_used": "",
    "url": "https://ti.to/defna/test-event-purchase/tickets/ti_test_poZATmK8dkdvHnJVTfgxdmg",
    "admin_url": "https://dashboard.tito.io/defna/test-event-purchase/tickets/ti_test_poZATmK8dkdvHnJVTfgxdmg",
    "release_title": "Early Bird",
    "release_slug": "scwuqmy40qq",
    "release_id": 1207019,
    "release": {
        "id": 1207019,
        "title": "Early Bird",
        "slug": "scwuqmy40qq",
        "metadata": null
    },
    "custom": "",
    "registration_id": 12454475,
    "registration_slug": "pH1wgNvwmf2TFH2v66AZJ1g",
    "metadata": null,
    "answers": [],
    "opt_ins": [],
    "responses": {},
    "last_updated_by_type": null,
    "upgrades": [],
    "upgrade_ids": [],
    "registration": {
        "id": 12454475,
        "slug": "pH1wgNvwmf2TFH2v66AZJ1g",
        "url": "https://ti.to/registrations/pH1wgNvwmf2TFH2v66AZJ1g",
        "admin_url": "https://dashboard.tito.io/defna/test-event-purchase/registrations/pH1wgNvwmf2TFH2v66AZJ1g",
        "total": "100.0",
        "currency": "USD",
        "payment_reference": "ch_3MZnaAD593dUjUPh0LHZos9A",
        "source": null,
        "name": "ngrok4",
        "email": "dcus@example.com",
        "receipt": {
            "total": "100.0",
            "tax": 0,
            "payment_provider": "Stripe (live)",
            "paid": true,
            "receipt_lines": [{
                "total": "100.0",
                "quantity": 1,
                "tax": 0,
                "tax_description": " @0.0%"
            }]
        }
    },
    "event": {
        "_type": "event",
        "id": 1085033,
        "title": "Test Event Purchase",
        "url": "https://ti.to/defna/test-event-purchase",
        "account_slug": "defna",
        "slug": "test-event-purchase",
        "start_date": null,
        "end_date": null,
        "metadata": null
    },
    "text": "Early Bird S6Q7-1 updated"
}
"""


class TitoWebhookCases(TestCase):
    def test_ticket_created(self):
        twe = TitoWebhookEvent.objects.create(
            trigger="ticket.created",
            payload_text=TEST_PAYLOAD_DATA,
        )
        twe.payload = json.loads(twe.payload_text)
        twe.save()

    # todo: ticket_created should subscribe the purchaser to the Sendy list

    # todo: ticket_reassigned should ? (unsubscribe original / subscribe new?; only subscribe new?)
