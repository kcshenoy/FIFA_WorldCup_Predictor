# Feature Engineering Methodology: Top-5-League Count and Squad Connectivity

## 1. Objective

For each national team's roster at a given FIFA Men's World Cup, we derive two
features:

1. **`top5_league_count`** — the number of squad players who were active in one
   of the "big five" European domestic leagues (Premier League, La Liga, Serie
   A, Bundesliga, Ligue 1) during the club season immediately surrounding the
   tournament.
2. **`connectivity`** — a measure of how many squad members were also club
   teammates with one another at a top-5-league club, capturing pre-existing
   on-field familiarity within the international squad.

## 2. Data sources

| File | Role | Grain |
|---|---|---|
| `results.csv` | International match results, 1872–present | 1 row per match |
| `squads.csv` | World Cup roster entries, 1930–2022 (men's + women's) | 1 row per player per tournament |
| `players.csv` | Player biographical data (name, birth date) | 1 row per player, `P-XXXXX` id |
| `player_performances.txt` | Club season-by-season stats (competition, team, appearances) | 1 row per player per club season per competition, numeric id |
| `player_profiles.csv` | Player biographical data (name, birth date), numeric id | 1 row per player |

The key obstacle: `squads.csv`/`players.csv` identify players with a `P-XXXXX`
id and a name, while `player_performances.txt` — which is the only source of
actual club/league history — identifies players with an unrelated numeric id
and **no name field at all**. The two id spaces do not overlap. `player_profiles.csv`
was the bridge: it carries the same numeric id used in `player_performances.txt`
alongside a player name and date of birth, which can be matched against
`players.csv`.

## 3. Cross-dataset player linkage

We built a crosswalk between the two id systems by joining on **normalized
full name + exact date of birth**:

1. Names were transliterated to ASCII (`unidecode`) and lowercased, with
   punctuation stripped, to absorb accent/diacritic mismatches (e.g. "Luka
   Modrić" vs. "Luka Modric").
2. A handful of players in `players.csv` use a single mononym (e.g.
   Brazilian players like "Neymar"), stored with a placeholder
   `given_name = "not applicable"`; these were detected and normalized to use
   only the surname field before matching, otherwise they would never match.
3. Records were joined on `(name_key, date_of_birth)` — a combination that is
   effectively unique globally. Verified directly against known players
   (e.g. Lionel Messi: `P-14758` in `players.csv` ↔ numeric id `28003` in
   `player_profiles.csv`, both listing DOB `1987-06-24`, with performance rows
   correctly showing his Barcelona/La Liga career).

**Match-rate caveat:** this join only succeeds if the player exists in
`player_profiles.csv`, which is a transfermarkt-style scrape with materially
weaker historical depth before the 1990s. We validated this directly by
confirming that even legendary, extensively-documented 1980s players (Diego
Maradona, Michel Platini, Franz Beckenbauer) are entirely absent from the
file — proof that early gaps reflect **source-data coverage**, not football
history (foreign-player counts in top leagues were lower pre-Bosman (1995) but
not to the degree implied by a ~0% match rate). Match rate climbs from 0%
(pre-1986) to ~79% by the 2022 World Cup. **For this reason, only World Cups
from 1998 onward are retained in the final feature table.**

## 4. Defining "top-5 league"

Rather than match on the free-text `competition_name` field (which is
ambiguous — dozens of countries have a competition literally named "Premier
League" or "Serie A"), we matched on the structured `competition_id` code,
which is stable across name changes (e.g. Ligue 1 was historically labeled
"Division 1" under the same id):

| League | `competition_id` |
|---|---|
| Premier League (England) | `GB1` |
| LaLiga (Spain) | `ES1` |
| Serie A (Italy) | `IT1` |
| Bundesliga (Germany) | `L1` |
| Ligue 1 (France) | `FR1` |

## 5. Determining the relevant club season

European club seasons are labeled by split years (e.g. `22/23`). To decide
which season should be treated as "current" for a given World Cup, we used the
tournament's actual start month (derived from the earliest match date per
year in `results.csv`, tournament == `FIFA World Cup`):

```
if start_month <= 7:      # most WCs: June/July, after the season just ended
    season = f"{(year-1)%100:02d}/{year%100:02d}"
else:                      # e.g. Qatar 2022 (November): season in progress
    season = f"{year%100:02d}/{(year+1)%100:02d}"
```

## 6. Feature formulas

Let `S` be a national squad (one team, one tournament), and for each player
`p` in `S`, let `clubs(p)` be the set of club teams `p` appeared for in a
top-5 league during the tournament's target season (from Section 5).

**Top-5-league count:**

```
top5_league_count(S) = |{ p ∈ S : clubs(p) ≠ ∅ }|
```

i.e. the number of distinct squad members with at least one top-5-league
appearance that season.

**Connectivity:** group squad members by shared club, and count the unique
teammate pairs formed at each club:

```
connectivity(S) = Σ_c  C(n_c, 2) = Σ_c  n_c(n_c - 1) / 2
```

where the sum runs over every top-5-league club `c` that has `n_c ≥ 2` squad
members from `S` playing there that season, and `C(n_c, 2)` is the number of
unique pairs among them. For example, if 6 of a country's players were all at
the same club, that club alone contributes `C(6,2) = 15` connectivity points.

## 7. Automated pipeline (World Cups 1998–2022)

For tournaments already covered by `squads.csv` (all men's World Cups,
1930–2022; retained subset 1998–2022 per the coverage caveat above), the two
features were computed with a fully automated `pandas` pipeline
(`build_features.py`):

1. Load and normalize `players.csv`, `player_profiles.csv`; build the id
   crosswalk (Section 3).
2. Filter `squads.csv` to men's tournaments, map each `tournament_id` to its
   target club season (Section 5).
3. Filter `player_performances.txt` to rows where `competition_id` is in the
   top-5 set; join squad rosters to this filtered performance table on
   `(profile_id, season_name)`.
4. Group and aggregate per `(tournament_id, team_id)` using the formulas in
   Section 6.
5. Write the result to `team_tournament_features.csv`, and (optionally) join
   it back onto `results.csv` for rows where `tournament == "FIFA World Cup"`.

This produced 224 team/tournament rows (32 teams × 7 tournaments, 1998–2022),
with an overall player-linkage rate of 61% within that window.

## 8. Manual data collection for the 2026 World Cup

`squads.csv` does not yet include the 2026 World Cup (the dataset predates
the tournament), so its 48 teams' rosters had to be sourced independently
rather than through the structured pipeline:

1. **Roster source**: Wikipedia's "2026 FIFA World Cup squads" article. The
   combined page is large enough that a single fetch truncates before
   reaching all 48 teams, so each team's squad table was retrieved
   individually via the MediaWiki API (`action=parse&section=N&prop=wikitext`),
   targeting the wikitext section for that specific team to get a complete,
   untruncated table of every player, position, caps, and current club.
2. **League classification**: each player's listed club was manually
   classified into one of the five target leagues (or "none"), using each
   league's confirmed 2025/26 promotion/relegation outcomes (e.g. Leeds,
   Burnley, and Sunderland promoted to the Premier League; Saint-Étienne
   remaining in Ligue 2 after losing its promotion playoff) to correctly
   classify borderline clubs.
3. **Feature computation**: the same formulas from Section 6 were applied by
   hand to each team's classified roster — grouping players by club and
   summing `C(n_c, 2)` for any club with 2+ international teammates.
4. **Team id assignment**: the 43 returning nations were matched to their
   existing `team_id` from `squads.csv` for continuity; the 5 debutant
   nations in the expanded 48-team format (Curaçao, Cape Verde, Jordan, DR
   Congo, Uzbekistan) received newly assigned sequential ids.
5. Results were appended to `team_tournament_features.csv` as 48 additional
   rows (`tournament_id = "WC-2026"`).

**Confidence**: 39 of 48 teams are high-confidence (complete official squad
tables, unambiguous club classification). 9 teams (Qatar, Uzbekistan, Jordan,
Iraq, Cape Verde, Curaçao, Panama, New Zealand) are flagged medium-confidence,
generally due to messier squad-announcement timelines or a preponderance of
lesser-documented domestic clubs — though this does not affect their
connectivity scores, since none of these squads had any top-5-league
clustering regardless.

## 9. Known limitations

- **Historical coverage**: pre-1998 World Cups are excluded because the
  underlying player-profile source has near-zero coverage of that era,
  producing artificially deflated feature values rather than a genuine
  historical signal.
- **Multi-club-season edge case**: a player transferred mid-season between two
  top-5-league clubs will be counted in both clubs' groups, very slightly
  inflating connectivity in rare cases.
- **2026 data provenance**: unlike 1998–2022 (fully reproducible from the
  provided CSVs), the 2026 rows were built from a one-time manual/AI-assisted
  web research pass and are not re-derivable by re-running
  `build_features.py`; they should be treated as a fixed, hand-verified
  supplement to the automated pipeline rather than part of its regular
  output.
