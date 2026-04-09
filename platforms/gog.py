import json
import sqlite3

import pandas


class GOG:
    def __init__(self, database_path):
        self._db = database_path

    def read_games_database(self):
        with sqlite3.connect(self._db) as con:
            query = '''
    WITH l AS (SELECT releaseKey, "type" t, "value" v
        FROM ProductPurchaseDates links
        JOIN GamePieces gp ON links.gameReleaseKey = gp.releaseKey
        JOIN GamePieceTypes gpt ON gp.gamePieceTypeId = gpt.id),
    r AS (SELECT releaseKey,
        SUBSTR(releaseKey, 0, INSTR(releaseKey, '_')) platform,
        MIN(CASE WHEN t = 'title' THEN json_extract(v, '$.title') END) AS title,
        MAX(CASE WHEN t = 'myRating' THEN json_extract(v, '$.myRating') END) AS rating,
        MIN(CASE WHEN t = 'allGameReleases' THEN v END) AS allGameReleases,
        MAX(CASE WHEN t = 'originalImages' THEN v END) AS images,
        MAX(CASE WHEN t = 'meta' THEN v END) AS meta,
        MAX(CASE WHEN t = 'summary' THEN json_extract(v, '$.summary') END) AS summary
        FROM l
        GROUP BY releaseKey),
    steam_releases AS (SELECT allGameReleases, NULLIF(CAST(SUBSTR(json_each.value, 7) AS INTEGER), 0) steamRelease
        FROM r, json_each(r.allGameReleases, '$.releases')
        WHERE json_each.value LIKE 'steam%'),
    release_times AS (SELECT r.allGameReleases,
        SUM(times.minutesInGame) total_time,
        MAX(lastPlayed.lastPlayedDate) last_played_date
        FROM r
        LEFT JOIN GameTimes times USING (releaseKey)
        LEFT JOIN LastPlayedDates lastPlayed ON r.releaseKey = lastPlayed.gameReleaseKey
        GROUP BY r.allGameReleases)
    SELECT
        title,
        rt.total_time game_time,
        rt.last_played_date last_played,
        IFNULL(MAX(rating), 0) rating,
        MAX(summary) summary,
        GROUP_CONCAT(DISTINCT platform) platforms,
        json_extract(MAX(images), '$.squareIcon') icon,
        json_extract(MAX(images), '$.verticalCover') cover,
        GROUP_CONCAT(DISTINCT steamRelease) steam_ids,
        json_extract(allGameReleases, '$.releases') all_releases,
        json_group_array(DISTINCT urt.tag) FILTER (WHERE urt.tag IS NOT NULL) tags,
        MAX(meta) meta
    FROM r
        LEFT JOIN steam_releases USING (allGameReleases)
        LEFT JOIN release_times rt USING (allGameReleases)
        LEFT JOIN ReleaseProperties prop USING (releaseKey)
        LEFT JOIN ProductPurchaseDates purchase ON releaseKey = purchase.gameReleaseKey
        LEFT JOIN UserReleaseProperties urp USING (releaseKey)
        LEFT JOIN UserReleaseTags urt USING (releaseKey)
        GROUP BY allGameReleases
        HAVING IFNULL(MAX(prop.isVisibleInLibrary), 1) > 0 AND IFNULL(MAX(prop.isDlc), 0) < 1 AND IFNULL(MAX(urp.isHidden), 0) < 1
        -- AND NOT (Platforms = 'xboxone' AND game_time = 0 AND last_played IS NULL)  -- Xbox Game Pass
        ORDER BY title
    '''
            df = pandas.read_sql_query(query, con)
            df['steam_ids'] = df['steam_ids'].apply(lambda x: x.split(',') if isinstance(x, str) else [])
            df['all_releases'] = df['all_releases'].apply(lambda x: json.loads(x))
            df['tags'] = df['tags'].apply(lambda x: json.loads(x))
            df['meta'] = df['meta'].apply(lambda x: json.loads(x))
            df['hide'] = (df['rating'] == 0) & (df['last_played'].isnull()) & (df['game_time'] == 0)
        return df


    def get_linked_steam_account_id(self) -> str | None:
        with sqlite3.connect(self._db) as con:
            cur = con.execute("SELECT externalUserId FROM ExternalAccounts WHERE externalPlatform = 'steam'")
            row = cur.fetchone()
            if row is not None:
                return row[0]
            return None
