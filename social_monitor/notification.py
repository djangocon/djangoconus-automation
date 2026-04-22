import logging

from django.conf import settings
from django.utils.html import strip_tags
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from social_monitor.schemas import SocialItem

client = WebClient(token=settings.SLACK_OAUTH_TOKEN)


def _format_item(item: SocialItem) -> list:
    type_emoji = ":speech_balloon:" if item.type == "mention" else ":hash:"
    content_text = strip_tags(item.content)
    content_preview = (content_text[:200] + "...") if len(content_text) > 200 else content_text

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{item.author}* on {item.platform} ({item.created_at:%Y-%m-%d %H:%M})\n\n{type_emoji} {item.tag}\n\n{content_preview}\n{item.url}\n",
            },
        },
    ]

    return blocks


def send_slack_notification(content: SocialItem) -> bool:
    try:
        response = client.chat_postMessage(
            channel=settings.SLACK_CHANNEL_ID,
            blocks=_format_item(content),
        )

        return response.get("ok", False)
    except SlackApiError as e:
        logging.error(e)

    return False
