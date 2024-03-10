from dataclasses import dataclass


@dataclass
class Platform:
    key: str
    name: str


PLATFORMS = {p.key: p for p in [
    # svg icon in res folder
    Platform('epic', 'Epic'),
    Platform('xboxone', 'Xbox'),
    Platform('steam', 'Steam'),
    Platform('gog', 'GOG.com'),
    Platform('uplay', 'Ubisoft Connect'),
    Platform('origin', 'Origin'),
    Platform('rockstar', 'Rockstar'),
    Platform('battlenet', 'Battle.net'),
    Platform('generic', 'Other'),
]}
