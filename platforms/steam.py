from enum import IntEnum

import requests
from steam.client import SteamClient
from steam.webapi import WebAPI

from helpers import split_chunks


class Genre(IntEnum):
    ACTION = 1
    STRATEGY = 2
    RPG = 3
    CASUAL = 4
    RACING = 9
    SPORTS = 18
    INDIE = 23
    ADVENTURE = 25
    SIMULATION = 28
    MMO = 29
    F2P = 37
    ACCOUNTING = 50
    ANIMATION_MODELING = 51
    AUDIO_PRODUCTION = 52
    DESIGN_ILLUSTRATION = 53
    EDUCATION = 54
    PHOTO_EDITING = 55
    SOFTWARE_TRAINING = 56
    UTILITIES = 57
    VIDEO_PRODUCTION = 58
    WEB_PUBLISHING = 59
    GAME_DEVELOPMENT = 60
    EARLY_ACCESS = 70
    SEXUAL = 71
    NUDITY = 72
    VIOLENT = 73
    GORE = 74
    DOCUMENTARY = 81
    TUTORIAL = 84


GENRE_NAMES = {
    Genre.ACTION: "Action",
    Genre.STRATEGY: "Strategy",
    Genre.RPG: "RPG",
    Genre.CASUAL: "Casual",
    Genre.RACING: "Racing",
    Genre.SPORTS: "Sports",
    Genre.INDIE: "Indie",
    Genre.ADVENTURE: "Adventure",
    Genre.SIMULATION: "Simulation",
    Genre.MMO: "Massively Multiplayer",
    Genre.F2P: "Free to Play",
    Genre.ACCOUNTING: "Accounting",
    Genre.ANIMATION_MODELING: "Animation & Modeling",
    Genre.AUDIO_PRODUCTION: "Audio Production",
    Genre.DESIGN_ILLUSTRATION: "Design & Illustration",
    Genre.EDUCATION: "Education",
    Genre.PHOTO_EDITING: "Photo Editing",
    Genre.SOFTWARE_TRAINING: "Software Training",
    Genre.UTILITIES: "Utilities",
    Genre.VIDEO_PRODUCTION: "Video Production",
    Genre.WEB_PUBLISHING: "Web Publishing",
    Genre.GAME_DEVELOPMENT: "Game Development",
    Genre.EARLY_ACCESS: "Early Access",
    Genre.SEXUAL: "Sexual Content",
    Genre.NUDITY: "Nudity",
    Genre.VIOLENT: "Violent",
    Genre.GORE: "Gore",
    Genre.DOCUMENTARY: "Documentary",
    Genre.TUTORIAL: "Tutorial",
}


class SteamAPI:
    def __init__(self, steam_api_key):
        self._api = WebAPI(steam_api_key)
        self._key = steam_api_key

    def get_friends(self, steam_id):
        return self._api.ISteamUser.GetFriendList_v1(steamid=steam_id, relationship='friend')['friendslist']['friends']

    def get_player_summaries(self, steam_ids):
        players_info = {}
        for chunk in split_chunks(steam_ids, 100):
            players = self._api.ISteamUser.GetPlayerSummaries_v2(
                steamids=','.join(chunk)
            )['response']['players']
            for p in players:
                players_info[p['steamid']] = p
        return players_info

    def get_owned_games(self, steam_id):
        return self._api.IPlayerService.GetOwnedGames(
            steamid=steam_id, include_played_free_games=True, include_appinfo=False, appids_filter=[],
            include_free_sub=True, language='english', include_extended_appinfo=False)['response']

    def get_steam_categories(self):
        return requests.get("https://api.steampowered.com/IStoreBrowseService/GetStoreCategories/v1/",
                            {"key": self._key, "elanguage": 0}).json()["response"]["categories"]


class PublicSteamAPI:
    def __init__(self):
        self._api = SteamClient()
        self._api.anonymous_login()

    def get_product_info(self, apps):
        return self._api.get_product_info(apps=apps)
