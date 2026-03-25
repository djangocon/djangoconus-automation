import djclick as click

from emailoctopus.utils import sync_campaigns


@click.command()
def command():
    """Sync campaigns from Email Octopus into the local database."""
    sync_campaigns()
