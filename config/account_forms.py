"""Allauth customization: let the magic-link page create the account.

Out of the box, ``/accounts/login/code/`` only mails a code to users who already
exist; an unknown address gets allauth's "we do not have any record of such an
account" email and a dead end. Attendees have no reason to have signed up first,
so that dead end is the whole failure mode this removes.

Wired up via ``ACCOUNT_FORMS["request_login_code"]`` in settings.
"""

import logging

from allauth.account.adapter import get_adapter
from allauth.account.forms import RequestLoginCodeForm
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email, user_username
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


class AutoSignupRequestLoginCodeForm(RequestLoginCodeForm):
    """Create the account when the address is unknown, then let the code go out.

    Safe to do without a password or a separate confirmation step: the code is
    only ever mailed to the address that was typed, so an account created this
    way can only be reached by whoever actually reads that inbox. Someone
    entering a stranger's address just creates a shell they cannot log into.
    """

    def clean_email(self):
        # super() consumes the rate limit and sets _user; keep both behaviours.
        email = super().clean_email()

        if email and self._user is None:
            self._user = self._create_user(email)

        return email

    def _create_user(self, email: str):
        adapter = get_adapter()
        User = get_user_model()

        user = User()
        user_email(user, email)
        # Stock auth.User has a UNIQUE username column, so it has to be filled.
        # populate_username() derives one from the address and de-duplicates it
        # ("jeff@a.com" -> jeff, "jeff@b.com" -> jeff1). See #89 for why this
        # must not be short-circuited with ACCOUNT_USER_MODEL_USERNAME_FIELD.
        adapter.populate_username(None, user)
        # Passwordless by construction: there is no password to set, and an
        # unusable one keeps the account off the password-login path entirely.
        user.set_unusable_password()

        try:
            with transaction.atomic():
                user.save()
                EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
        except IntegrityError:
            # Two requests for the same new address can race here. Whoever lost
            # just uses the row the winner made.
            logger.info("Race creating magic-link account for %s; using the existing row", email)
            existing = EmailAddress.objects.filter(email__iexact=email).select_related("user").first()
            return existing.user if existing else None

        logger.info("Auto-created account %s (%s) from a magic-link request", user.pk, user_username(user))
        return user
