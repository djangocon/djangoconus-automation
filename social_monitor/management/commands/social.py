import djclick as click
from django_q.models import Schedule
from rich import print

from social_monitor.models import PlatformHashTag, SocialPlatform


@click.group()
def command():
    """Social monitor command"""
    pass


@command.command()
def monitor():
    """Set up a periodic task to monitor for mentions and hashtags"""
    name = "social-monitor"
    schedule, created = Schedule.objects.update_or_create(
        name=name,
        defaults={
            "func": "social_monitor.mastodon_client.collect_social_activity",
            "schedule_type": Schedule.HOURLY,
        }
    )

    action = "Created" if created else "Updated"
    print(f"[green]{action} schedule for {name}[/green]")

@command.command()
@click.option("--fetch", "fetch_flag", is_flag=True, help="fetch all platforms")
@click.option("--add", "add_platform_name", help="add new platform")
@click.option("--remove", "remove_platform_name", help="remove new platform")
@click.option("--fetch-mentions", "fetch_mentions", default=True, help="fetch mentions")
def platform(fetch_flag, add_platform_name, remove_platform_name, fetch_mentions):
    """add social platform"""

    if fetch_flag:
        platforms = SocialPlatform.objects.all()
        if platforms:
            for i, p in enumerate(platforms):
                print(f"{i+1}) [green]{p}[/green]")
        else:
            print("[red]No platforms found![/red]")
            return

    if add_platform_name:
        p, created = SocialPlatform.objects.get_or_create(
            name=add_platform_name,
            get_mentions=fetch_mentions
        )

        if created:
            print(f"[green]Platform `{add_platform_name}` added![/green]")
        else:
            print(f"[yellow]Platform `{add_platform_name}` already exists.[/yellow]")

    if remove_platform_name:
        try:
            p = SocialPlatform.objects.get(name=remove_platform_name)
            p.delete()
            print(f"[green]Platform `{remove_platform_name} removed![/green]`")
        except SocialPlatform.DoesNotExist:
            print(f"[red]Platform `{remove_platform_name}` does not exists![/red]`")

@command.command()
@click.argument('platform_name')
@click.argument("query_str", required=False)
@click.option("--add", "add_flag", is_flag=True, help="add query to social platform")
@click.option("--remove", "remove_flag", is_flag=True, help="remove query from social platform")
@click.option("--fetch", "fetch_query", is_flag=True, help="fetch queries")
def query(platform_name, query_str, add_flag, remove_flag, fetch_query):
    """add social query"""
    try:
        p = SocialPlatform.objects.get(name=platform_name)
    except SocialPlatform.DoesNotExist:
        print(f"[red]Platform `{platform_name}` does not exist![/red]")
        return

    if add_flag:
        if PlatformHashTag.objects.filter(platform=p, query=query_str).exists():
            print(f"[yellow]Query `{query_str}` already exists for {platform_name}.[/yellow]")
        else:
            PlatformHashTag.objects.create(platform=p, query=query_str)
            print(f"[green]Query `{query_str}` added to {platform_name}![/green]")

    if remove_flag:
        try:
            query_obj = PlatformHashTag.objects.get(platform=p, query=query_str)
            query_obj.delete()
            print(f"[green]Query `{query_str}` removed from {platform_name}![/green]")
        except PlatformHashTag.DoesNotExist:
            print(f"[red]Query `{query_str}` not found for {platform_name}![/red]")
            return

    if fetch_query:
        try:
            query_obj = PlatformHashTag.objects.filter(platform=p)
            for q in query_obj:
                print(f"[green]{q}[/green]")
            return
        except PlatformHashTag.DoesNotExist:
            print(f"[red]Query `{query_str}` not found for {platform_name}![/red]")


    if not add_flag and not remove_flag:
        print(f"[blue]No action specified. Use --add or --remove for `{query_str}` on {platform_name}.[/blue]")


