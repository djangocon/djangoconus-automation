import djclick as click
from rich import print

from thunderdome.sync import sync_event


@click.command()
@click.argument("event_slug")
def command(event_slug):
    """Import submissions and reviews from pretalx for the given event."""
    print(f"Syncing from pretalx for [bold]{event_slug}[/bold]...")
    result = sync_event(event_slug)

    if "error" in result:
        print(f"[red]{result['error']}[/red]")
        return

    print(
        f"[green]Submissions: {result['submissions_created']} created, "
        f"{result['submissions_updated']} updated ({result['submissions_total']} total).[/green]"
    )
    print(
        f"[green]Reviews: {result['reviews_created']} created, "
        f"{result['reviews_updated']} updated, "
        f"{result['reviews_skipped']} skipped ({result['reviews_total']} total).[/green]"
    )
