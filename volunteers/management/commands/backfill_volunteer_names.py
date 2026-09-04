"""Fill in blank volunteer names from their Ti.to tickets."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from volunteers.models import VolunteerSignup
from volunteers.names import fill_missing_name, ticket_names


class Command(BaseCommand):
    help = "Fill blank first/last names on volunteer accounts from their Ti.to ticket."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change without saving.")
        parser.add_argument(
            "--all-users",
            action="store_true",
            help="Consider every account, not just people with an active sign-up.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.filter(first_name="", last_name="")
        if not options["all_users"]:
            volunteer_ids = VolunteerSignup.objects.filter(cancelled=False).values_list("user_id", flat=True)
            users = users.filter(id__in=volunteer_ids)

        names = ticket_names()
        filled = 0
        missed = []

        for user in users:
            match = names.get((user.email or "").strip().lower())
            if not match:
                missed.append(user.email or user.get_username())
                continue
            if options["dry_run"]:
                self.stdout.write(f"would set {user.email} -> {' '.join(part for part in match if part)}")
            else:
                fill_missing_name(user, names=names)
                self.stdout.write(f"{user.email} -> {' '.join(part for part in match if part)}")
            filled += 1

        verb = "Would fill" if options["dry_run"] else "Filled"
        self.stdout.write(self.style.SUCCESS(f"{verb} {filled} name(s); {len(missed)} not found in Ti.to."))
        for email in missed:
            self.stdout.write(f"  no ticket: {email}")
