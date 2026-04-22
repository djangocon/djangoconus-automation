from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ItemType(str, Enum):
    MENTION = "mention"
    HASHTAG = "hashtag"


@dataclass
class SocialItem:
    id: int
    platform: str
    type: ItemType

    author: str
    content: str
    url: str
    tag: str
    created_at: datetime
