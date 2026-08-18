import djclick as click
from rich import print

from tickets.sync import DEFAULT_YEAR, sync_ticket_releases


@click.command()
@click.option("--year", type=int, default=DEFAULT_YEAR, help="Conference year to sync.")
def command(year):
    """Discover Ti.to ticket types so their Venueless access can be toggled in admin."""
    result = sync_ticket_releases(year=year)
    print(f"[green]{result['year']}: {result['created']} new ticket types, {result['total']} total.[/green]")
