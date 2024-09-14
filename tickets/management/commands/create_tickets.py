import djclick as click

from tickets.models import TicketLink


@click.command()
@click.argument("urls", nargs=-1)
def command(urls):
    """
    Creates a new TicketLink for every URL provided as an argument.
    Usage: python manage.py create_tickets <url1> <url2> ... <urlN>
    """
    if not urls:
        click.echo("No URLs provided. Please provide at least one URL.")
        return

    created_count = 0
    for url in urls:
        try:
            TicketLink.objects.create(link=url)
            click.echo(f"Created TicketLink for URL: {url}")
            created_count += 1
        except Exception as e:
            click.echo(f"Failed to create TicketLink for URL: {url}. Error: {e}")

    click.echo(f"Total TicketLinks created: {created_count}")
