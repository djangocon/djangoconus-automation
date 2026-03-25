import djclick as click

from emailoctopus.utils import sync_lists


@click.command()
def command():
    """Sync lists from Email Octopus into the local database."""
    sync_lists()
