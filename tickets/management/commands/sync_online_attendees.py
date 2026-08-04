import djclick as click
from rich import print

from tickets.sync import DEFAULT_YEAR, sync_online_attendees


@click.command()
@click.option("--year", type=int, default=DEFAULT_YEAR, help="Conference year to sync.")
def command(year):
    """Rebuild the online-attendee roster from Ti.to tickets and webhooks."""
    result = sync_online_attendees(year=year)
    print(
        f"[green]{result['year']}: {result['created']} created, "
        f"{result['updated']} updated, {result['total']} online attendees total.[/green]"
    )
