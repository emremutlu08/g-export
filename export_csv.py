import csv
from pathlib import Path
from platforms.gog import GOG

GOG_DB = r'C:\ProgramData\GOG.com\Galaxy\storage\galaxy-2.0.db'
OUTPUT = Path(__file__).parent / 'games.csv'

gog = GOG(GOG_DB)
df = gog.read_games_database()

with OUTPUT.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Game Name', 'Hours Played', 'Platforms'])
    for row in df.itertuples():
        platforms = row.platforms.split(',') if isinstance(row.platforms, str) else []
        if platforms == ['xboxone']:
            continue
        minutes = int(row.game_time) if row.game_time else 0
        hours = round(minutes / 60, 1)
        writer.writerow([row.title, hours, ', '.join(platforms)])

print(f'Exported to {OUTPUT}')
