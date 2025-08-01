import djclick as click
from django_q.tasks import async_task
from rich import print

from sendy.models import List
from titowebhooks.models import TitoWebhookEvent


@click.command()
@click.option(
    "--pks",
    multiple=True,
    type=int,
    help="Primary keys of TitoWebhookEvent objects to process. If not provided, processes all events.",
)
def command(pks):
    """Send TitoWebhookEvent data to Sendy mailing lists."""
    if pks:
        queryset = TitoWebhookEvent.objects.filter(pk__in=pks)
        print(f"Processing {queryset.count()} events with PKs: {list(pks)}")
    else:
        queryset = TitoWebhookEvent.objects.all()
        print(f"Processing all {queryset.count()} events")

    sendy_lists = List.objects.filter(default=True)

    if not sendy_lists.exists():
        print("[red]No default Sendy lists found![/red]")
        return

    print(f"Found {sendy_lists.count()} default Sendy list(s)")

    success_count = 0
    error_count = 0

    for sendy_list in sendy_lists:
        for event in queryset:
            try:
                if "email" not in event.payload:
                    print(f"[yellow]Skipping event {event.pk}: No email in payload[/yellow]")
                    continue

                email = event.payload["email"]
                first_name = event.payload.get("first_name", "")
                last_name = event.payload.get("last_name", "")
                name = f"{first_name} {last_name}".strip()

                async_task(
                    "sendy.utils.send_to_sendy",
                    email=email,
                    name=name,
                    campaign_id=sendy_list.list_id,
                )

                print(f"[green]Queued: {email} -> {sendy_list.name}[/green]")
                success_count += 1

            except Exception as e:
                print(f"[red]Error processing event {event.pk}: {e}[/red]")
                error_count += 1

    print("\n[bold]Summary:[/bold]")
    print(f"  [green]Successfully queued: {success_count}[/green]")
    print(f"  [red]Errors: {error_count}[/red]")
