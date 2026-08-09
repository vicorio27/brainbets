#!/usr/bin/env python3
"""Download La Liga historical match data and save it in football-data.co.uk
CSV format so the existing ingestion pipeline can consume it.

Strategy:
- Prefer Wayback Machine snapshots of football-data.co.uk (the live site is
  blocked by the local ISP).
- Fall back to openfootball/football.json when Wayback only has an incomplete
  season snapshot.
- Normalize team names to the football-data.co.uk convention so Elo/Poisson
  models see consistent competitor identities across seasons.

Seasons covered: 2010-11 through 2023-24.
"""

import csv
import json
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

SEASONS = [
    "2010-11",
    "2011-12",
    "2012-13",
    "2013-14",
    "2014-15",
    "2015-16",
    "2016-17",
    "2017-18",
    "2018-19",
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
]

# Minimum rows expected for a "complete" La Liga season (20 teams, 38 matchdays,
# 380 matches). We allow a small margin in case a snapshot dropped a header line.
MIN_COMPLETE_ROWS = 370


def season_code(season: str) -> str:
    """Convert '2012-13' to '1213'."""
    start, end = season.split("-")
    return start[2:] + end


def fmt_date(iso_date: str) -> str:
    """Convert '2023-08-11' to football-data '11/08/2023'."""
    if not iso_date:
        return ""
    y, m, d = iso_date.split("-")
    return f"{d}/{m}/{y}"


def result(home: int, away: int) -> str:
    if home > away:
        return "H"
    if away > home:
        return "A"
    return "D"


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "brainbets-historical-ingestion/1.0"})
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_json(url: str):
    return json.loads(fetch(url).decode("utf-8"))


def latest_wayback_snapshot(season: str) -> str:
    """Query the Wayback CDX API and return the timestamp of the largest CSV."""
    code = season_code(season)
    cdx_url = (
        "https://web.archive.org/cdx/search/cdx"
        f"?url=www.football-data.co.uk/mmz4281/{code}/SP1.csv"
        "&output=json&filter=statuscode:200"
    )
    rows = fetch_json(cdx_url)
    if len(rows) <= 1:
        raise ValueError(f"No Wayback snapshots found for {season}")

    # rows[0] is the header; data rows are [urlkey, timestamp, original, ...]
    best = max(rows[1:], key=lambda r: int(r[6] if len(r) > 6 else 0))
    return best[1]


def fetch_wayback_csv(season: str) -> tuple[str, int]:
    """Return (csv_text, row_count) from the best Wayback snapshot."""
    code = season_code(season)
    timestamp = latest_wayback_snapshot(season)
    url = (
        f"https://web.archive.org/web/{timestamp}id_/"
        f"https://www.football-data.co.uk/mmz4281/{code}/SP1.csv"
    )
    print(f"  Wayback snapshot {timestamp}")
    data = fetch(url).decode("utf-8", errors="replace")
    lines = [line for line in data.splitlines() if line.strip()]
    row_count = max(0, len(lines) - 1) if lines else 0
    return data, row_count


def fetch_openfootball_rows(season: str) -> list[dict]:
    url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/es.1.json"
    print(f"  Falling back to openfootball ({url})")
    data = fetch_json(url)
    matches = data.get("matches", [])
    rows = []
    for m in matches:
        score = m.get("score") or {}
        ft = score.get("ft") or [None, None]
        ht = score.get("ht") or [None, None]
        fthg, ftag = ft[0], ft[1]
        if fthg is None or ftag is None:
            continue
        hthg, htag = ht[0], ht[1]
        rows.append({
            "Div": "SP1",
            "Date": fmt_date(m.get("date", "")),
            "Time": m.get("time", ""),
            "HomeTeam": m.get("team1", ""),
            "AwayTeam": m.get("team2", ""),
            "FTHG": fthg,
            "FTAG": ftag,
            "FTR": result(int(fthg), int(ftag)),
            "HTHG": hthg if hthg is not None else "",
            "HTAG": htag if htag is not None else "",
            "HTR": result(int(hthg), int(htag)) if hthg is not None and htag is not None else "",
            "Referee": "",
        })
    return rows


# Hardcoded mapping from openfootball/verbose names to football-data.co.uk names.
# This keeps competitor identities consistent across seasons so Elo/Poisson
# models train on a single record per real team.
NAME_MAPPING = {
    "Athletic Club": "Ath Bilbao",
    "Club Atlético de Madrid": "Ath Madrid",
    "Atlético Madrid": "Ath Madrid",
    "FC Barcelona": "Barcelona",
    "Real Betis Balompié": "Betis",
    "Real Betis": "Betis",
    "Cádiz CF": "Cadiz",
    "RC Celta de Vigo": "Celta",
    "RC Celta": "Celta",
    "Deportivo Alavés": "Alaves",
    "CD Alavés": "Alaves",
    "SD Eibar": "Eibar",
    "RCD Espanyol": "Espanol",
    "Espanyol Barcelona": "Espanol",
    "Getafe CF": "Getafe",
    "Girona FC": "Girona",
    "Granada CF": "Granada",
    "UD Las Palmas": "Las Palmas",
    "CD Leganés": "Leganes",
    "Levante UD": "Levante",
    "Málaga CF": "Malaga",
    "RCD Mallorca": "Mallorca",
    "CA Osasuna": "Osasuna",
    "Real Sociedad de Fútbol": "Sociedad",
    "Real Sociedad": "Sociedad",
    "Sevilla FC": "Sevilla",
    "Sporting de Gijón": "Sp Gijon",
    "Rayo Vallecano de Madrid": "Vallecano",
    "Real Madrid CF": "Real Madrid",
    "Real Valladolid CF": "Valladolid",
    "Real Valladolid": "Valladolid",
    "Valencia CF": "Valencia",
    "Villarreal CF": "Villarreal",
    "UD Almería": "Almeria",
    "SD Huesca": "Huesca",
    "Real Zaragoza": "Zaragoza",
    "Deportivo La Coruna": "La Coruna",
    "Racing Santander": "Santander",
    "Real Oviedo": "Oviedo",
    "CD Numancia": "Numancia",
    "CD Tenerife": "Tenerife",
    "Xerez CD": "Xerez",
    "Real Murcia": "Murcia",
    "Recreativo Huelva": "Recreativo",
    "Gimnàstic Tarragona": "Gimnastic",
    "Albacete Balompié": "Albacete",
    "Córdoba CF": "Cordoba",
    "CD Mirandés": "Mirandes",
    "Real Jaén": "Jaen",
    "CE Sabadell FC": "Sabadell",
    "CD Lugo": "Lugo",
    "AD Alcorcón": "Alcorcon",
    "SD Ponferradina": "Ponferradina",
    "CF Fuenlabrada": "Fuenlabrada",
    "UD Logroñés": "Logrones",
    "FC Cartagena": "Cartagena",
    "Burgos CF": "Burgos",
    "CD Eldense": "Eldense",
    "FC Andorra": "Andorra",
    "Elche CF": "Elche",
    "Celta de Vigo": "Celta",
    "Rcd Mallorca": "Mallorca",
    "Real Sporting de Gijón": "Sp Gijon",
}


def normalize_name(name: str) -> str:
    return NAME_MAPPING.get(name.strip(), name.strip())


def normalize_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["HomeTeam"] = normalize_name(row["HomeTeam"])
        row["AwayTeam"] = normalize_name(row["AwayTeam"])
    return rows


def write_csv(out_path: Path, rows: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "Div", "Date", "Time", "HomeTeam", "AwayTeam",
            "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HTR", "Referee",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def download_season(season: str, out_dir: Path) -> int:
    code = season_code(season)
    out_path = out_dir / f"football_{code}_SP1.csv"

    print(f"Downloading {season} ...")
    try:
        wayback_text, row_count = fetch_wayback_csv(season)
    except Exception as e:
        print(f"  Wayback failed: {e}")
        wayback_text, row_count = "", 0

    if row_count >= MIN_COMPLETE_ROWS:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            f.write(wayback_text)
        print(f"  Wrote {row_count} matches to {out_path} (wayback)")
        return row_count

    rows = fetch_openfootball_rows(season)
    rows = normalize_rows(rows)
    write_csv(out_path, rows)
    print(f"  Wrote {len(rows)} matches to {out_path} (openfootball)")
    return len(rows)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "storage" / "historical_raw"
    total = 0
    for season in SEASONS:
        total += download_season(season, out_dir)
    print(f"Total matches written: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
