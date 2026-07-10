"""
Build two team-level features for FIFA Men's World Cup squads and attach them
to the relevant rows of results.csv:

  1. top5_league_count : # of squad players who appeared in a top-5 European
     league (Premier League, LaLiga, Serie A, Bundesliga, Ligue 1) during the
     club season immediately preceding/ongoing at World Cup time.
  2. connectivity       : # of unique teammate pairs within the squad who were
     at the SAME top-5-league club in that season (sum of C(n,2) per club).

Player ID linkage:
  squads.csv / players.csv use "P-XXXXX" ids (name + birth_date available).
  player_performances.txt uses a separate numeric id with NO name field.
  player_profiles.csv bridges the two: numeric id + player_name + date_of_birth.
  We join players.csv <-> player_profiles.csv on (normalized full name, birth_date).
"""
import re
import pandas as pd
from unidecode import unidecode

TOP5 = {"GB1", "ES1", "IT1", "L1", "FR1"}


def normalize_name(name: str) -> str:
    name = unidecode(str(name)).lower()
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    return name


def load_players():
    players = pd.read_csv("players.csv", dtype=str)
    mononym = players["given_name"].str.lower() == "not applicable"
    players["full_name"] = players["given_name"] + " " + players["family_name"]
    players.loc[mononym, "full_name"] = players.loc[mononym, "family_name"]
    players["name_key"] = players["full_name"].map(normalize_name)
    players["birth_date"] = pd.to_datetime(players["birth_date"], errors="coerce")
    return players


def load_profiles():
    profiles = pd.read_csv("player_profiles.csv", dtype=str, usecols=[
        "player_id", "player_name", "date_of_birth"
    ])
    # player_name looks like "Full Name (id)" -- strip the trailing id suffix
    clean = profiles["player_name"].str.replace(r"\s*\(\d+\)\s*$", "", regex=True)
    profiles["name_key"] = clean.map(normalize_name)
    profiles["date_of_birth"] = pd.to_datetime(profiles["date_of_birth"], errors="coerce")
    profiles["player_id"] = profiles["player_id"].astype(str)
    return profiles


def build_crosswalk(players, profiles):
    """Map squads/players P-XXXXX id -> player_performances numeric id."""
    left = players[["player_id", "name_key", "birth_date"]].dropna(subset=["birth_date"])
    right = profiles[["player_id", "name_key", "date_of_birth"]].dropna(subset=["date_of_birth"])
    right = right.rename(columns={"player_id": "profile_id", "date_of_birth": "birth_date"})

    merged = left.merge(right, on=["name_key", "birth_date"], how="inner")
    # a (name_key, birth_date) pair should be essentially unique; if a player_id
    # matches >1 profile_id (rare collision), keep the first and drop the rest
    merged = merged.drop_duplicates(subset=["player_id"], keep="first")
    xwalk = merged.set_index("player_id")["profile_id"].to_dict()

    match_rate = len(merged) / players["player_id"].nunique()
    print(f"Crosswalk: matched {len(merged)}/{players['player_id'].nunique()} "
          f"players ({match_rate:.1%})")
    return xwalk


def load_mens_squads(min_year=1998):
    squads = pd.read_csv("squads.csv", dtype=str)
    squads = squads[squads["tournament_name"].str.contains("Men's", na=False)].copy()
    squads["year"] = squads["tournament_id"].str.extract(r"WC-(\d{4})").astype(int)
    squads = squads[squads["year"] >= min_year].copy()
    return squads


def season_for_year(results: pd.DataFrame, mens_squads: pd.DataFrame) -> dict:
    """tournament_id -> season_name string (e.g. '17/18') based on the
    calendar month the tournament actually started, per results.csv."""
    wc = results[results["tournament"] == "FIFA World Cup"].copy()
    wc["date"] = pd.to_datetime(wc["date"])
    wc["year"] = wc["date"].dt.year
    start_month = wc.groupby("year")["date"].min().dt.month

    season_map = {}
    for tid, year in mens_squads[["tournament_id", "year"]].drop_duplicates().values:
        month = start_month.get(year)
        if month is None:
            continue
        if month <= 7:  # tournament before/around mid-year -> prior season just ended
            y0, y1 = year - 1, year
        else:  # e.g. Qatar 2022 (Nov) -> season already in progress
            y0, y1 = year, year + 1
        season_map[tid] = f"{y0 % 100:02d}/{y1 % 100:02d}"
    return season_map


def compute_features(squads, xwalk, season_map, perf):
    squads = squads.copy()
    squads["profile_id"] = squads["player_id"].map(xwalk)
    squads["season_name"] = squads["tournament_id"].map(season_map)

    linked = squads.dropna(subset=["profile_id", "season_name"]).copy()
    print(f"Squad rows with a resolvable profile+season: "
          f"{len(linked)}/{len(squads)} ({len(linked)/len(squads):.1%})")

    perf_top5 = perf[perf["competition_id"].isin(TOP5)][
        ["player_id", "season_name", "team_id"]
    ].drop_duplicates()
    perf_top5 = perf_top5.rename(columns={"player_id": "profile_id", "team_id": "club_id"})
    perf_top5["profile_id"] = perf_top5["profile_id"].astype(str)

    hits = linked.merge(perf_top5, on=["profile_id", "season_name"], how="inner")

    # Feature 1: distinct top5-league players per (tournament_id, team_id)
    top5_count = (
        hits.drop_duplicates(subset=["tournament_id", "team_id", "player_id"])
        .groupby(["tournament_id", "team_id"])
        .size()
        .rename("top5_league_count")
    )

    # Feature 2: connectivity = sum of C(n,2) teammate pairs per club, per squad
    club_sizes = (
        hits.drop_duplicates(subset=["tournament_id", "team_id", "club_id", "player_id"])
        .groupby(["tournament_id", "team_id", "club_id"])
        .size()
    )
    pairs_per_club = (club_sizes * (club_sizes - 1) // 2)
    connectivity = pairs_per_club.groupby(level=["tournament_id", "team_id"]).sum().rename(
        "connectivity"
    )

    team_names = squads[["tournament_id", "team_id", "team_name", "year"]].drop_duplicates()
    out = team_names.merge(top5_count, on=["tournament_id", "team_id"], how="left")
    out = out.merge(connectivity, on=["tournament_id", "team_id"], how="left")
    out["top5_league_count"] = out["top5_league_count"].fillna(0).astype(int)
    out["connectivity"] = out["connectivity"].fillna(0).astype(int)
    return out


def attach_to_results(results, team_features):
    results = results.copy()
    results["date"] = pd.to_datetime(results["date"])
    results["year"] = results["date"].dt.year
    is_wc = results["tournament"] == "FIFA World Cup"

    feat = team_features.rename(columns={"team_name": "team"})
    home = feat.rename(columns={
        "team": "home_team", "top5_league_count": "home_top5_league_count",
        "connectivity": "home_connectivity",
    })[["home_team", "year", "home_top5_league_count", "home_connectivity"]]
    away = feat.rename(columns={
        "team": "away_team", "top5_league_count": "away_top5_league_count",
        "connectivity": "away_connectivity",
    })[["away_team", "year", "away_top5_league_count", "away_connectivity"]]

    results = results.merge(home, on=["home_team", "year"], how="left")
    results = results.merge(away, on=["away_team", "year"], how="left")

    for c in ["home_top5_league_count", "home_connectivity",
              "away_top5_league_count", "away_connectivity"]:
        results.loc[~is_wc, c] = pd.NA

    return results.drop(columns=["year"])


def main():
    print("Loading data...")
    players = load_players()
    profiles = load_profiles()
    results = pd.read_csv("results.csv")
    mens_squads = load_mens_squads()

    perf = pd.read_csv(
        "player_performances.txt",
        usecols=["player_id", "season_name", "competition_id", "team_id"],
        dtype={"player_id": str, "season_name": str, "competition_id": str, "team_id": str},
    )

    xwalk = build_crosswalk(players, profiles)
    season_map = season_for_year(results, mens_squads)

    team_features = compute_features(mens_squads, xwalk, season_map, perf)
    team_features.to_csv("team_tournament_features.csv", index=False)
    print("Wrote team_tournament_features.csv "
          f"({len(team_features)} team/tournament rows)")

    enriched = attach_to_results(results, team_features)
    enriched.to_csv("results_with_features.csv", index=False)
    n_wc = (enriched["tournament"] == "FIFA World Cup").sum()
    print(f"Wrote results_with_features.csv ({n_wc} FIFA World Cup rows enriched)")

    print("\nSample (2022):")
    print(team_features[team_features["year"] == 2022]
          .sort_values("top5_league_count", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
