"""Shift cards shouldn't print the role name twice.

Titles are conventionally "<Role> · <Day> <time>" and the card already prints
the role and the time on its own line, so a title that only repeats the role is
suppressed. A title that says something extra survives.
"""

import datetime

import pytest
from django.utils import timezone

from volunteers.models import Role, Shift


def make_shift(role_name, title):
    role = Role.objects.create(name=role_name)
    start = timezone.now() + datetime.timedelta(hours=2)
    return Shift.objects.create(
        role=role, title=title, starts_at=start, ends_at=start + datetime.timedelta(hours=2)
    )


@pytest.mark.django_db
class TestDisplayTitle:
    def test_title_that_only_repeats_the_role_is_suppressed(self):
        shift = make_shift("In-person sprints welcomer", "In-person sprints welcomer · Thu 9:00 AM")
        assert shift.display_title == ""

    def test_title_matching_the_role_exactly_is_suppressed(self):
        shift = make_shift("Swag Bag Stuffing", "Swag Bag Stuffing")
        assert shift.display_title == ""

    def test_title_that_adds_something_is_kept(self):
        shift = make_shift("Session Manager", "Morning Session Manager · Mon")
        assert shift.display_title == "Morning Session Manager · Mon"

    def test_an_unrelated_title_is_kept(self):
        shift = make_shift("Online Moderator", "Moderator 1")
        assert shift.display_title == "Moderator 1"

    def test_comparison_ignores_case_and_padding(self):
        shift = make_shift("Registration Desk", "  registration desk · Sun 2:00 PM  ")
        assert shift.display_title == ""
