"""
Recompute top5_league_count / connectivity for WC-2002 from the manually
scraped world_cup_top5_league_players_2002.csv, replacing the automated
(transfermarkt-crosswalk-derived) values for that tournament only.
Also drops WC-1998 rows (out of scope) and writes team_tournament_features.csv.
"""
import pandas as pd

NAME_FIX = {
    "China PR": "China",
}

df = pd.read_csv("world_cup_top5_league_players_2002.csv")
df["Country"] = df["Country"].replace(NAME_FIX)

counted = df[df["Counted?"] == True].copy()

top5_count = counted.groupby("Country")["Player"].nunique().rename("top5_league_count")

club_sizes = counted.groupby(["Country", "Club"]).size()
pairs = (club_sizes * (club_sizes - 1) // 2)
connectivity = pairs.groupby(level="Country").sum().rename("connectivity")

all_teams = df["Country"].unique()
new_2002 = pd.concat([top5_count, connectivity], axis=1).reindex(all_teams).fillna(0).astype(int)
new_2002.index.name = "team_name"
new_2002 = new_2002.reset_index()

tf = pd.read_csv("team_tournament_features.csv")
tf = tf[tf["year"] >= 2002].copy()

wc2002_teams = set(tf.loc[tf["tournament_id"] == "WC-2002", "team_name"])
csv_teams = set(new_2002["team_name"])
print("In scraped CSV but not in team_tournament_features.csv (WC-2002):", csv_teams - wc2002_teams)
print("In team_tournament_features.csv (WC-2002) but not in scraped CSV:", wc2002_teams - csv_teams)

tf = tf.merge(new_2002, on="team_name", how="left", suffixes=("", "_new"))
is_2002 = tf["tournament_id"] == "WC-2002"
tf.loc[is_2002, "top5_league_count"] = tf.loc[is_2002, "top5_league_count_new"]
tf.loc[is_2002, "connectivity"] = tf.loc[is_2002, "connectivity_new"]
tf = tf.drop(columns=["top5_league_count_new", "connectivity_new"])
tf["top5_league_count"] = tf["top5_league_count"].astype(int)
tf["connectivity"] = tf["connectivity"].astype(int)

tf.to_csv("team_tournament_features.csv", index=False)
print(f"\nWrote team_tournament_features.csv ({len(tf)} rows, years {sorted(tf['year'].unique())})")
print("\nWC-2002 rows:")
print(tf[tf["tournament_id"] == "WC-2002"].sort_values("connectivity", ascending=False).to_string(index=False))
