import logging
from typing import List

from django.conf import settings
from mastodon import Mastodon

from social_monitor.models import PlatformHashTag, SocialPlatform
from social_monitor.notification import send_slack_notification
from social_monitor.schemas import ItemType, SocialItem

PLATFORM_NAME = "mastodon"


mastodon = Mastodon(
    access_token=settings.MASTODON_ACCESS_TOKEN,
    api_base_url=settings.MASTODON_API_BASE_URL,
)


def _get_hashtags():
    platform = SocialPlatform.objects.get(name=PLATFORM_NAME)
    query_obj = PlatformHashTag.objects.filter(platform=platform)
    return query_obj


def fetch_mentions(limit: int = 5) -> List[SocialItem]:
    """fetch the most recent mentions of the current Mastodon account."""
    mastodon_mentions = []
    try:
        platform = SocialPlatform.objects.get(name=PLATFORM_NAME)

        if platform.get_mentions:
            mentions = mastodon.notifications(types=['mention'], limit=limit, since_id=0 if platform.last_seen is None else int(platform.last_seen))
            for mention in mentions:
                mastodon_mentions.append(
                    SocialItem(
                        id=int(mention.id),
                        platform=PLATFORM_NAME,
                        type=ItemType.MENTION,
                        author=mention.account.acct,
                        content=mention.status.content,
                        url=mention.status.url,
                        tag=ItemType.MENTION.name,
                        created_at=mention.status.created_at
                    )
                )
        else:
            logging.info(f"mentions for `{platform.name}` are not being collected. Please enable them first.")
    except Exception as e:
        logging.error(e)

    return mastodon_mentions


def fetch_posts(limit: int = 5) -> List[SocialItem]:
    """fetch the most recent posts containing a specific hashtag from Mastodon."""
    mastodon_posts = []
    try:
        queries = _get_hashtags()
        for query in queries:
            if query.is_active:
                posts = mastodon.timeline_hashtag(query.query, limit=limit, since_id=0 if query.last_seen is None else int(query.last_seen))
                for post in posts:
                    mastodon_posts.append(
                        SocialItem(
                            id=int(post.id),
                            platform=PLATFORM_NAME,
                            type=ItemType.HASHTAG,
                            author=post.account.acct,
                            content=post.content,
                            url=post.url,
                            tag=query.query,
                            created_at=post.created_at,
                        )
                    )
            else:
                logging.info(f"`{query.query}` not active")
    except Exception as e:
        logging.error(e)

    return mastodon_posts




def collect_social_activity():

    mentions = fetch_mentions()
    posts = fetch_posts(limit=1)

    all_activities = mentions + posts
    last_seen_marked = []

    if all_activities:
        platform = SocialPlatform.objects.get(name=PLATFORM_NAME)
        for activity in all_activities:
            notified = send_slack_notification(activity)

            if notified:
                if activity.type == ItemType.MENTION and ItemType.MENTION not in last_seen_marked:
                    platform.last_seen = activity.id
                    platform.save()
                    last_seen_marked.append(ItemType.MENTION)

                if activity.type == ItemType.HASHTAG and activity.tag not in last_seen_marked:
                    social_query = PlatformHashTag.objects.get(platform=platform, query=activity.tag)
                    social_query.last_seen = activity.id
                    social_query.save()
                    last_seen_marked.append(activity.tag)
            else:
                logging.error(f"error while sending notification for `{activity.id}` `{activity.tag}`")


