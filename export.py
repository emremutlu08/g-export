import json
import os
import sys
import time
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from multiprocessing.pool import ThreadPool
from pathlib import Path
from sys import stderr
from typing import Iterable, Mapping, Dict, Tuple, Optional
from urllib.parse import urlparse

import requests
from pandas import DataFrame
from steam.client import SteamClient  # noqa
from steam.steamid import SteamID
from tqdm import tqdm

from helpers import TmpFile, one_way_sync, read_json_gz_file, write_json_gz_file
from platforms.gog import GOG
from platforms.platforms import PLATFORMS
from platforms.steam import SteamAPI, PublicSteamAPI
from platforms.steam_info import SteamCategory, STEAM_IMG_BASE_URL
from platforms.types import GameInfoRow, FriendsInfoRow

SCRIPT_DIR = Path(__file__).parent
DIST_DIR = SCRIPT_DIR / 'dist'
DIST_RES_DIR = DIST_DIR / 'res'
DIST_IMG_DIR = DIST_DIR / 'img'
CACHE_DIR = SCRIPT_DIR / 'cache'
RES_DIR = SCRIPT_DIR / 'res'
STEAM_DB_CACHE = CACHE_DIR / 'steamdb.json.gz'
REPORT_FILE = DIST_DIR / 'index.html'
DATA_DUMP_FILE = DIST_DIR / 'data.json.gz'
REPO_URL = 'https://git.romlig.ch/gilles/g-export'


class ImageCache:
    def __init__(self):
        self._locations: Dict[str, Path] = {}

    def path(self, url: str) -> Path:
        if url not in self._locations:
            extension = urlparse(url).path.split('.')[-1].lower()
            digest = sha256(url.encode("utf-8")).hexdigest()
            self._locations[url] = CACHE_DIR / digest[0] / digest[:2] / f'{digest}.{extension}'
        return self._locations[url]

    def rel_path(self, url: str) -> Path:
        return self.path(url).relative_to(CACHE_DIR)


def download_image(url: str):
    dest = IMAGE_CACHE.path(url)
    with TmpFile(dest) as dest_tmp:
        dest_tmp.write_bytes(requests.get(url).content)


IMAGE_CACHE = ImageCache()


def steam_ids(steam_id):
    s = SteamID(steam_id)
    return [
        s.as_32,
        s.as_64,
        s.as_steam2_zero,
        s.as_steam2,
        s.as_steam3
    ]


def create_parent_dirs(missing_images: Iterable[Path]):
    for f in set(p.parent for p in missing_images):
        f.mkdir(exist_ok=True, parents=True)


def run(*, gog_db, tags=False, steam_id=None, steam_api_key=None, all_friends=False, friends=None) -> None:
    export_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    CACHE_DIR.mkdir(exist_ok=True)
    gog = GOG(gog_db)

    print("Reading GOG database…", end=" ")
    df = gog.read_games_database()
    print("done")
    steam_db = get_steam_metadata(df)

    def get_steam_game_id(ids):
        for game_id in sorted(ids, key=lambda x: int(x)):
            if game_id in steam_db and steam_db[game_id] and not steam_db[game_id]['_missing_token']:
                return game_id
        return None

    def get_game_info(row):
        if row.steam_id:
            return steam_db[row.steam_id]
        return None

    unknown_categories = set()

    def get_categories(info):
        categories = set()
        if info is not None and 'category' in info['common']:
            for c in info['common']['category'].keys():
                num = int(c.replace('category_', ''))
                try:
                    categories.add(SteamCategory(num))
                except:
                    unknown_categories.add(num)
        return categories

    friends_info, game_friends = get_friends_info(gog, all_friends, friends, steam_api_key, steam_id)

    df['steam_id'] = df['steam_ids'].apply(get_steam_game_id)
    df['info'] = df.apply(get_game_info, axis=1)
    df['categories'] = df['info'].apply(get_categories)
    df['icon_rel'] = df['icon'].apply(lambda x: IMAGE_CACHE.rel_path(x) if x else None)
    df['cover_rel'] = df['cover'].apply(lambda x: IMAGE_CACHE.rel_path(x) if x else None)

    if len(unknown_categories):
        print(r'  ! Unknown Steam categories', ', '.join(str(c) for c in sorted(unknown_categories)), file=sys.stderr)

    friends_info['icon_rel'] = friends_info['icon'].apply(lambda x: IMAGE_CACHE.rel_path(x) if x else None)
    images = [
        *df['icon'].dropna(),
        *df['cover'].dropna(),
        *friends_info['icon'].dropna(),
        *(STEAM_IMG_BASE_URL + e.icon_url for e in SteamCategory)
    ]

    download_missing_images(images)

    DIST_DIR.mkdir(exist_ok=True)
    DIST_RES_DIR.mkdir(exist_ok=True)
    DIST_IMG_DIR.mkdir(exist_ok=True)
    one_way_sync(CACHE_DIR, DIST_IMG_DIR, (IMAGE_CACHE.rel_path(i) for i in images))
    one_way_sync(RES_DIR, DIST_RES_DIR, (f.relative_to(RES_DIR) for f in RES_DIR.iterdir() if f.is_file()))
    row: GameInfoRow
    games_dump = [dict(
        title=row.title,
        icon=str('img' / row.icon_rel).replace('\\', '/') if row.icon else None,
        cover=str('img' / row.cover_rel).replace('\\', '/') if row.cover else None,
        platforms=row.platforms,
        categories=dict(
            single=SteamCategory.SINGLE_PLAYER in row.categories,
            multi=SteamCategory.MULTI_PLAYER in row.categories,
            coop=SteamCategory.CO_OP in row.categories or SteamCategory.ONLINE_CO_OP in row.categories,
            pvp=SteamCategory.PVP in row.categories or SteamCategory.ONLINE_PVP in row.categories
        ) if row.info else False,
        gameTime=row.game_time,
        lastPlayed=row.last_played,
        rating=row.rating,
        summary=row.summary,
        friends=list(sorted(set(f for r in row.all_releases for f in game_friends[r]))),
        steamId=row.steam_id,
        allReleases=row.all_releases,
        hide=row.hide,
        tags=row.tags if tags else [],
        releaseDate=min((int(r) for r in [
            row.meta.get('releaseDate'),
            row.info.get('common', {}).get('steam_release_date') if row.info else None
        ] if r is not None), default=None),
    ) for row in df.itertuples()]
    friend_row: FriendsInfoRow
    friends_dump = {friend_row.Index: dict(
        name=friend_row.name,
        icon=str('img' / friend_row.icon_rel).replace('\\', '/') if friend_row.icon else None
    ) for friend_row in friends_info.itertuples()}
    platforms_dump = {p.key: p.name for p in PLATFORMS.values()}
    num_games = (df['hide'] == False).sum()
    hidden_games = df['hide'].sum()
    write_json_gz_file(DATA_DUMP_FILE, dict(games=games_dump, friends=friends_dump, platforms=platforms_dump))
    with TmpFile(REPORT_FILE) as r, r.open('wt', encoding='utf-8') as report:
        report.write(
            '<!DOCTYPE html>\n'
            '<html><head>\n'
            '<meta charset="utf-8"/>\n'
            '<meta rel="shortcut icon" href="res/p-generic.svg"/>\n'
            '<title>My Games</title>\n'
            '<script src="res/ag-grid-community.min.noStyle.js"></script>\n'
            '<script src="res/luxon.min.js"></script>\n'
            '<script>const data = '
        )
        json.dump(games_dump, report)
        report.write(f';\n')
        report.write(f'const showFriends = {"true" if friends or all_friends else "false"};\n')
        report.write(f'const showTags = {"true" if tags else "false"};\n')
        report.write(f'const friendsInfo = ')
        json.dump(friends_dump, report)
        report.write(';\nconst platformsInfo = ')
        json.dump(platforms_dump, report)
        report.write(';\n')
        report.write(
            '</script>\n'
            '<script src="res/script.js"></script>\n'
            '<link rel="stylesheet" href="res/style.css">\n'
            '<link rel="stylesheet" href="res/ag-grid.css">\n'
            '<link rel="stylesheet" href="res/ag-theme-balham-dark.css">\n'
            '</head><body>\n'
            '<div id="gridContainer"><div id="myGrid" class="ag-theme-balham-dark"></div>\n'

            f'<div id="exportInfo">{num_games} games – '
            f'game list exported from GOG Galaxy using <a href="{REPO_URL}">g-export</a> – '
            f'{export_time} – '
            f'<input id="showIgnored" type="checkbox"/><label for="showIgnored">show {hidden_games} without activity</label>'
            f'</div></div>\n'

            '<div id="details"><div id="background"><img width=48 height=48 alt=""/><div class="shadow"></div></div>'
            '<img id="cover" height=482 width=342/>'
            '<h1>My Games</h1><div id="summary"></div></div>\n'

            '</body>\n'
        )


def get_steam_metadata(games_df):
    # Retrieve missing Steam metadata
    if STEAM_DB_CACHE.is_file():
        steam_db = read_json_gz_file(STEAM_DB_CACHE)
    else:
        steam_db = {}
    if 'apps' not in steam_db:
        steam_db['apps'] = {}
    missing_apps = [int(a) for ids in games_df['steam_ids']
                    for a in ids if a not in steam_db]
    if len(missing_apps):
        print(f"Downloading Steam metadata for {len(missing_apps)} apps…")
        client = PublicSteamAPI()
        steam_data = client.get_product_info(apps=missing_apps)
        retrieve_stamp = int(time.time())
        for a in missing_apps:
            if a not in steam_data['apps']:
                steam_data['apps'][str(a)] = False  # invalid app number
            else:
                steam_data['apps'][a]['retrieved'] = retrieve_stamp
        steam_db.update((str(k), v) for k, v in steam_data['apps'].items())
        write_json_gz_file(STEAM_DB_CACHE, steam_db)
        print("done")
    return steam_db


def get_friends_info(gog: GOG, all_friends: bool, friends: Optional[Iterable[str]],
                     steam_api_key: Optional[str], steam_id: Optional[str]) -> Tuple[DataFrame, Mapping[str, list]]:
    game_friends = defaultdict(list)
    friends_info = {}
    if friends or all_friends:
        if steam_id is None:
            steam_id = gog.get_linked_steam_account_id()
            if steam_id is None:
                raise ValueError('Steam ID is not set and could not be retrieved from the GOG database')
        my_id = SteamID(steam_id)
        if not my_id.is_valid():
            my_id = SteamID.from_url(f'https://steamcommunity.com/id/{steam_id}')
        if my_id is None or not my_id.is_valid():
            raise ValueError('Failed to retrieve info for steam id', steam_id)

        print("Retrieve Steam friends list…", end=" ")
        api = SteamAPI(steam_api_key)
        steam_friends = api.get_friends(my_id)
        steam_friends_info = api.get_player_summaries([f['steamid'] for f in steam_friends])
        if all_friends:
            my_friends = steam_friends
        else:
            friends_filter = set(friends)
            my_friends = [f for f in steam_friends
                          if f.steamid in friends_filter
                          or steam_friends_info[f.steamid]['personaname'] in friends_filter
                          or any(p in friends_filter for p in steam_ids(f['steamid']))
                          or steam_friends_info[f['steamid']].profileurl
                          .replace('https://steamcommunity.com/id/', '')
                          .rtrim('/') in friends_filter]
        print("done")
        not_sharing = []
        for f in tqdm(my_friends, desc="Retrieve friends' game lists"):
            resp = api.get_owned_games(f['steamid'])
            if 'games' in resp:
                for a in resp['games']:
                    game_friends[f'steam_{a["appid"]}'].append(f'steam_{f["steamid"]}')
            else:
                not_sharing.append(steam_friends_info[f['steamid']]['personaname'])
                steam_friends_info.pop(f['steamid'])
        friends_info.update((f'steam_{k}', dict(name=info['personaname'], icon=info['avatar'], platform='steam'))
                            for k, info in steam_friends_info.items())
        if len(not_sharing):
            print('  ! Some friends do not share their game collection: ' + ', '.join(not_sharing), file=stderr)
    if len(friends_info):
        friends_info = DataFrame.from_dict(friends_info, 'index')
    else:
        friends_info = DataFrame(columns=['name', 'icon', 'platform'])
    return friends_info, game_friends


def download_missing_images(images: Iterable[str]):
    """Download missing images"""
    missing_images = [i for i in set(images) if not IMAGE_CACHE.path(i).exists()]
    if len(missing_images):
        print("Downloading missing images…")
        create_parent_dirs(IMAGE_CACHE.path(url) for url in missing_images)
        with ThreadPool(4) as pool:
            list(tqdm(pool.imap(download_image, missing_images),
                      desc='Downloading images', total=len(missing_images)))


if __name__ == '__main__':
    parser = ArgumentParser(
        description='Export a game list from GOG Galaxy as an HTML page.\n'
                    'The HTML page is located in the dist folder as well as all resources (e.g. game covers).',
        epilog='When using --friends or --all-friends, --steam-api-key must be set. '
               'Only Steam friends are supported, their game collections must be public.')
    parser.add_argument('--tags', help='Export user tags for the games', action='store_true')
    parser.add_argument(
        '--steam-id',
        help='Steam ID or vanity URL name (appears in the url of the profile page), can be retrieved from the GOG database when not set',
        default=os.environ.get('STEAM_ID'),
    )
    parser.add_argument(
        '--steam-api-key',
        help='Steam Web API key, get one here: https://steamcommunity.com/dev/apikey',
        default=os.environ.get('STEAM_API_KEY'),
    )
    parser.add_argument('--all-friends', action='store_true', help='Show games owned by all friends')
    parser.add_argument(
        '--friends', nargs='+',
        help='Show games owned by listed friends, Steam ID or vanity URL name or pseudonym'
    )
    parser.add_argument(
        '--gog-db',
        help='Location of the GOG Galaxy database file galaxy-2.0.db',
        default=os.environ.get('GOG_DB', r'C:\ProgramData\GOG.com\Galaxy\storage\galaxy-2.0.db'),
    )
    arg = parser.parse_args()
    if arg.friends and arg.all_friends:
        print('--friends cannot be used with --all-friends', file=stderr)
        sys.exit(1)
    if (arg.friends or arg.all_friends) and not arg.steam_api_key:
        print('When using --friends or --all-friends, --steam-api-key must be set', file=stderr)
        sys.exit(1)
    run(**vars(arg))
