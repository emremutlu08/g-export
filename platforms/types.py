from datetime import datetime
from pathlib import Path

from platforms.steam_info import SteamCategory


class GameInfoRow:
    title: str
    game_time: int
    last_played: datetime | None
    rating: int
    summary: str | None
    platforms: list[str]
    icon: str | None
    cover: str | None
    steam_ids: list[str]
    all_releases: list[str]
    tags: list[str]
    meta: ...

    steam_id: str
    info: ...
    categories: set[SteamCategory]
    icon_rel: Path | None
    cover_rel: Path | None
    hide: bool


class FriendsInfoRow:
    Index: str
    name: str
    icon: str | None
    platform: str

    icon_rel: Path | None