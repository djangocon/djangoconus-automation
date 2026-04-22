import djclick as click
from rich import print

from titowebhooks.sync import sync_tito_events


@click.command()
def command():
    """Sync ticket releases for all DjangoCon US years from the Tito API."""
    print("[bold]Syncing Tito events...[/bold]")
    result = sync_tito_events()

    if "error" in result:
        print(f"[red]{result['error']}[/red]")
        return

    print(f"[green]Created: {result['created']}, Updated: {result['updated']}[/green]")
    if result["failed"]:
        print(f"[yellow]Failed: {', '.join(result['failed'])}[/yellow]")
