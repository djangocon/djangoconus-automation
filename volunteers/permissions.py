"""Who counts as a volunteer chair, and what that lets them do.

Chairs are members of the "Volunteer Chair" group (seeded in migration 0010),
which carries the two permissions defined on ``VolunteerChairPermissions``.
Nobody loses access they already had: the dashboard still lets staff in, and the
interest report still lets superusers in.
"""

import functools

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import redirect_to_login
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied

VOLUNTEER_CHAIR_GROUP = "Volunteer Chair"

# (codename, human-readable name) — mirrors VolunteerChairPermissions.Meta.
CHAIR_PERMISSIONS = [
    ("view_volunteer_dashboard", "Can view and manage the volunteer dashboard"),
    ("view_volunteer_interest", "Can view the volunteer interest report"),
]

DASHBOARD_PERM = "volunteers.view_volunteer_dashboard"
INTEREST_PERM = "volunteers.view_volunteer_interest"


def _active(user):
    return user.is_authenticated and user.is_active


def can_manage_dashboard(user):
    """May see and manage the volunteer dashboard, its roster, and its actions.

    Staff could already do this, so they keep it.
    """
    return _active(user) and (user.is_staff or user.has_perm(DASHBOARD_PERM))


def can_view_volunteer_interest(user):
    """May see the volunteer interest report.

    This one was superuser-only, and stays that way apart from chairs — being
    staff isn't enough, same as before.
    """
    return _active(user) and (user.is_superuser or user.has_perm(INTEREST_PERM))


def _requires(test):
    """Build a decorator that runs ``test`` against ``request.user``.

    Anonymous users are sent to log in; signed-in users without access get a 403
    rather than a login loop.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if test(request.user):
                return view_func(request, *args, **kwargs)
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            raise PermissionDenied

        return wrapper

    return decorator


dashboard_required = _requires(can_manage_dashboard)
volunteer_interest_required = _requires(can_view_volunteer_interest)


def nav_can_manage_dashboard(request):
    return can_manage_dashboard(request.user)


def nav_can_view_volunteer_interest(request):
    return can_view_volunteer_interest(request.user)


def volunteer_chairs():
    """Active members of the Volunteer Chair group, for the chairs line."""
    return (
        get_user_model()
        .objects.filter(groups__name=VOLUNTEER_CHAIR_GROUP, is_active=True)
        .order_by("first_name", "last_name", "username")
    )


def grant_chair_group(group_model=None, permission_model=None, content_type_model=None):
    """Create the chair group and its permissions, idempotently.

    The models can be passed in so migration 0010 can hand over its historical
    versions; called with no arguments it uses the live ones. The permissions
    are normally created by ``create_permissions`` in a post_migrate hook, which
    hasn't run yet during that migration, so they're created here on demand and
    simply found later.
    """
    group_model = group_model or Group
    permission_model = permission_model or Permission
    content_type_model = content_type_model or ContentType

    content_type, _ = content_type_model.objects.get_or_create(
        app_label="volunteers", model="volunteerchairpermissions"
    )

    permissions = []
    for codename, name in CHAIR_PERMISSIONS:
        permission, _ = permission_model.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": name},
        )
        permissions.append(permission)

    group, _ = group_model.objects.get_or_create(name=VOLUNTEER_CHAIR_GROUP)
    group.permissions.add(*permissions)
    return group
