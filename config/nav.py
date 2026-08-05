from django_simple_nav.nav import Nav, NavGroup, NavItem

NAV_ITEMS = [
    NavGroup(
        title="Ticket Management",
        permissions=["is_authenticated"],
        items=[
            NavItem(title="Create Tickets", url="create_tickets", permissions=["is_staff"]),
            NavItem(title="View All Tickets", url="tickets_list", permissions=["is_staff"]),
            NavItem(title="Ticket Info", url="tickets_info"),
        ],
    ),
    NavGroup(
        title="Thunderdome",
        permissions=["is_staff"],
        items=[
            NavItem(title="Submissions", url="thunderdome_submissions"),
        ],
    ),
    NavGroup(
        title="Sprints",
        permissions=["is_staff"],
        items=[
            NavItem(title="Sprint Tickets", url="sprint_tickets"),
        ],
    ),
    NavGroup(
        title="Sales",
        permissions=["is_superuser"],
        items=[
            NavItem(title="Ticket Sales Dashboard", url="tito_sales_dashboard"),
        ],
    ),
    NavGroup(
        title="Volunteers",
        permissions=["is_authenticated"],
        items=[
            NavItem(title="Sign Up to Volunteer", url="volunteers:shifts"),
            NavItem(title="My Shifts", url="volunteers:my_shifts"),
            NavItem(title="Volunteer Dashboard", url="volunteers:dashboard", permissions=["is_staff"]),
            NavItem(title="Volunteer Interest Report", url="volunteer_interest", permissions=["is_superuser"]),
        ],
    ),
    NavGroup(
        title="Administration",
        permissions=["is_authenticated"],
        items=[
            NavItem(title="Django Admin", url="admin:index", permissions=["is_staff"]),
            NavItem(title="Email Previews", url="email_previews", permissions=["is_staff"]),
            NavItem(title="Sign Out", url="account_logout"),
        ],
    ),
    NavItem(title="Sign In", url="account_login", extra_context={"anonymous_only": True}),
]


class MainNav(Nav):
    template_name = "nav/main.html"
    items = NAV_ITEMS
