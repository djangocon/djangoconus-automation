from django.core.management.base import BaseCommand

from volunteers.tasks import send_shift_reminders


class Command(BaseCommand):
    help = "Send reminder emails for volunteer shifts starting in the next 24 hours."

    def handle(self, *args, **options):
        count = send_shift_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {count} reminder(s)."))
