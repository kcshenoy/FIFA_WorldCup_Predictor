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

Both features live in `team_tournament_features.csv`, one row per
`(tournament_id, team_id)`.

## 2. Data sources

| File | Role | Grain |
|---|---|---|
| `world_cup_top5_league_players_2002.csv` | Hand-compiled World Cup roster + club assignment, manually classified into a top-5 league (or none) | 1 row per player per tournament |
| `team_tournament_features.csv` | Output feature table (also the base file that manual rebuilds read and patch) | 1 row per team per tournament |

Earlier work also used an automated crosswalk pipeline (`build_features.py`)
driven by `results.csv`, `squads.csv`, `players.csv`, `player_performances.txt`,
and `player_profiles.csv` to compute 2006–2022 automatically. Those files and
that script have since been removed from the repo (they were large — over
150MB combined — and the project has moved to manually-compiled per-tournament
CSVs instead, per Section 6's linkage-rate findings). The 2006–2022 rows they
produced are still present in `team_tournament_features.csv`, but that
methodology is no longer runnable from this repo; see Section 6 for a summary
of how those rows were originally derived.

## 3. Defining "top-5 league"

The five target leagues:

| League | Country |
|---|---|
| Premier League | England |
| La Liga | Spain |
| Serie A | Italy |
| Bundesliga | Germany |
| Ligue 1 | France |

## 4. Feature formulas

Let `S` be a national squad (one team, one tournament), and for each player
`p` in `S`, let `clubs(p)` be the set of club teams `p` appeared for in a
top-5 league during the tournament's target season.

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

## 5. Manual rebuild of the 2002 World Cup

2002's automated linkage rate (42.7%, see Section 6) was low enough to
materially understate `top5_league_count`/`connectivity` for that tournament
(e.g. Italy's automated `top5_league_count` was 20 vs. 23 once manually
verified). Rather than drop 2002 like 1998, its squads were manually
re-sourced and re-classified, following the same manual methodology later
reused for 2026 (Section 7):

1. **Roster + club data**: compiled by hand into
   `world_cup_top5_league_players_2002.csv`, one row per player per squad,
   with columns `World Cup, Country, Player, Position, Club, Club Association,
   Top-5 League, Counted?` — `Top-5 League` names the specific league (or is
   blank) and `Counted?` is the boolean top-5-league flag used downstream.
2. **Feature computation** (`rebuild_2002_features.py`): filter to
   `Counted? == True`, then apply the Section 4 formulas directly — group by
   `Country` for `top5_league_count` (distinct counted players) and by
   `(Country, Club)` for `connectivity` (`C(n_c, 2)` summed per country).
   Countries with zero counted players (e.g. China, Saudi Arabia in 2002) are
   reindexed to 0/0 rather than silently dropped by the groupby.
3. **Merge**: these 32 rows replace the WC-2002 `top5_league_count`/
   `connectivity` values in `team_tournament_features.csv` (matched on
   `team_name`, with a manual alias for `China PR` → `China`); all other years
   are left untouched, and WC-1998 rows are dropped entirely.

## 6. History: automated pipeline (World Cups 2006–2022, now removed)

Before switching to manually-compiled rosters, `top5_league_count` and
`connectivity` for 2006–2022 were computed by joining World Cup squads to
each player's club/league history for the season immediately surrounding the
tournament. The key obstacle was that squads were identified with one id
system (name + birth date) while club/league history used a completely
separate numeric id with no name field; a crosswalk was built by joining the
two on normalized full name + exact birth date.

That crosswalk's match rate is the reason 1998 and 2002 aren't part of the
automated output — historical coverage was materially weaker for older
tournaments:

| World Cup | Linkage rate |
|---|---|
| 1998 | 29.6% |
| 2002 | 42.7% |
| 2006 | 55.4% |
| 2010 | 66.3% |
| 2014 | 73.4% |
| 2018 | 73.8% |
| 2022 | 81.6% |

1998 was dropped entirely, and 2002 was replaced with a manually-compiled
roster (Section 5). 2006–2022 kept the automated pipeline's output as-is;
those 160 rows (32 teams × 5 tournaments) are still in
`team_tournament_features.csv` today, but the pipeline that produced them
(`build_features.py` and its five input files) has since been deleted from
the repo — see Section 2. 2006's own 55.4% linkage rate means it's a
candidate for the same manual treatment as 2002, if/when that data is
compiled.

## 7. Manual data collection for the 2026 World Cup

`squads.csv` never included the 2026 World Cup (that dataset predates the
tournament), so its 48 teams' rosters had to be sourced independently:

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
3. **Feature computation**: the same formulas from Section 4 were applied by
   hand to each team's classified roster — grouping players by club and
   summing `C(n_c, 2)` for any club with 2+ international teammates.
4. **Team id assignment**: the 43 returning nations were matched to their
   existing `team_id` for continuity; the 5 debutant nations in the expanded
   48-team format (Curaçao, Cape Verde, Jordan, DR Congo, Uzbekistan)
   received newly assigned sequential ids.
5. Results were appended to `team_tournament_features.csv` as 48 additional
   rows (`tournament_id = "WC-2026"`).

**Confidence**: 39 of 48 teams are high-confidence (complete official squad
tables, unambiguous club classification). 9 teams (Qatar, Uzbekistan, Jordan,
Iraq, Cape Verde, Curaçao, Panama, New Zealand) are flagged medium-confidence,
generally due to messier squad-announcement timelines or a preponderance of
lesser-documented domestic clubs — though this does not affect their
connectivity scores, since none of these squads had any top-5-league
clustering regardless.

## 8. Known limitations

- **Historical coverage**: pre-2002 World Cups are excluded because the
  underlying player-profile source used by the now-removed automated pipeline
  had near-zero/low coverage of that era (Section 6), producing artificially
  deflated feature values rather than a genuine historical signal. 2002 is
  retained only because it was manually rebuilt (Section 5).
- **Multi-club-season edge case**: a player transferred mid-season between two
  top-5-league clubs would have been counted in both clubs' groups under the
  old automated pipeline (2006–2022), very slightly inflating connectivity in
  rare cases. The manual rosters (2002, 2026) record a player's single
  end-of-season/tournament-time club, so this edge case doesn't apply to them.
- **Non-reproducibility**: 2002 and 2026 were built from one-time
  manual/AI-assisted research passes (`rebuild_2002_features.py` and a manual
  pass respectively) and 2006–2022 was built from a pipeline whose source
  files no longer exist in this repo (Section 2). None of
  `team_tournament_features.csv` can currently be regenerated from scratch —
  it should be treated as a fixed table, hand-verified where noted, rather
  than the output of a rerunnable build step.