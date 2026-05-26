---
title: "Data Stores"
subtitle: "Netball codebase reference"
theme: neutral
h2_page_break: true
toc: true
---

This document describes the three data stores in the netball codebase: where each
one lives, what it contains, how it's populated, and how the stores relate to
each other.

## Overview

| Store | Location | Format | Source | Coverage |
|-------|----------|--------|--------|----------|
| **Regrading** | `data/` | JSON (raw API) | Netball Connect API | All teams in a competition, 2022--present |
| **Reporting** | `reporting/data/` | YAML (per-club) | Derived from regrading JSON + historical rosters | 11 clubs, 1998--present |
| **Tracking** | `tracking/` | YAML (per-player) | Pointers to reporting data | 2 players, selected teams |

All three stores ultimately trace back to the same Netball Connect data for
recent seasons (2022+). Pre-2022 reporting data comes from historical roster
records and does not include game results.

---

## 1. Regrading Store (`data/`)

**Purpose:** Raw competition data for grading analysis and recommendations.

**Structure:** One directory per competition snapshot, named by season and
competition type (e.g. `2025_spring_full`, `2024_autumn_thu_rep_full`).
Tournament data also stored here (e.g. `2025_ariels_invitational`,
`2026_ariels_invitational`).

```
data/
  2025_spring_full/
    meta.json                         # competition metadata
    team_ids.json                     # team ID -> name mapping
    matches_26122_15u_sec_1.json      # all matches for a division
    ladder_26122_15u_sec_1.json       # ladder standings
    ladder_computed_26117_9u_blue.json # recomputed ladder (9U special case)
    ...
  competitions.json                   # registry of all competitions
```

**Scale:** 50+ competition snapshots (domestic, rep, and tournament), 800+
match files, 800+ ladder files.

**Data granularity:** This is the most detailed store. Match records include:
- Scores, team IDs, venue/court details, start/end times
- Match status, result status, finals flags
- Penalty scores, lineup confirmation, livestream URLs

Ladder records include: rank, P, W, L, D, B, FW, FL, F, A, PTS, GA%.

**Populated by:** `nc/fetch.py` and `nc/client.py` pulling from the Netball
Connect API. The `competitions.json` registry tracks which competitions have
been fetched and their current status.

**Consumers:**
- `regrading/` package -- loading, analysis, candidate detection, report generation
- `regrading/retrospective.py` -- historical prediction accuracy analysis
- `nc/reporting_adapter.py` -- generates reporting YAML from stored data (via `build_club_season()`)
- `nc/store.py` -- `find_competition_finals()` scans all divisions for cross-pool finals
- `nc/ladder_merge.py` -- `load_merged_ladder()` rebuilds a division's ladder by computing each team's stats from the union of their rounds across every division they played in, partitioning teams to the section where their most recent match was played. Mirrors how Netball Connect's website carries a regraded team's record forward into the new section.
- `tracking/loader.py` -- `generate_all_section()` reads match data to auto-generate all-section results

**Overrides:** Manual corrections can be stored in `data/<comp_dir>/overrides.yaml`,
keyed by team_id. Applied by `nc/overrides.py` when reading through the reporting
adapter. See `docs/unified_data_store_plan.md` for format.

---

## 2. Reporting Store (`reporting/data/`)

**Purpose:** Per-club season data for club reports, comparison reports, and
trend analysis.

**Structure:** One YAML file per club per season, named
`{club}_{year}_{period}.yaml`.

```
reporting/data/
  warrandyte_2025_spring.yaml
  warrandyte_2024_autumn.yaml
  eastern_united_2025_spring.yaml
  ...
  warrandyte_netball_games.csv        # historical game log (supplementary)
  warrandyte_heritage.yaml            # rosters, coaches, premierships
```

**Scale:** 128+ YAML files across 11 clubs, spanning 1998--2026.

**Data granularity depends on era:**

| Era | Teams | Rosters | Rounds | Ladders | Finals |
|-----|-------|---------|--------|---------|--------|
| Pre-2022 | Division + players only | Yes | No | No | No |
| 2022+ | Full team records | Heritage only | Yes (per-round scores) | Yes | Yes |

A 2022+ team entry contains:
```yaml
team_name: WNC Emus
team_id: 169339
division: 15U Sec 1
division_id: 26122
record: [10, 0, 0]
goals_for: 459
goals_against: 156
played: 11
final_position: [1, 9]
rounds:
  - {round: 1, date: Jul 26, opponent: Panthers Suns, ha: A, for: 16, against: 1}
  ...
ladder:
  - {rank: 1, team: WNC Emus, p: 11, w: 10, l: 0, d: 0, ...}
  ...
finals:
  semis: [...]
  grand_final: {winner: ..., loser: ..., score: ...}
```

Roster data (players, coaches, managers) is stored separately in heritage files
(`<club>_heritage.yaml`), not in the per-season YAML.

**Populated by:** `reporting/fetch.py`, which can read from either:
- The **JSON store** (preferred) -- via `nc/reporting_adapter.py`, using `--from-store`
  or automatically when store data exists for the competition ID
- The **NC API** directly -- via `--from-api` or as a fallback when no store data exists

Pre-2022 files were created from historical roster records.

**Consumers:** `reporting/reports/` -- club reports, comparison reports, trend
reports, rep comparison reports. Also `reporting/analysis/` for performance,
retention, and roster analysis.

---

## 3. Tracking Store (`tracking/`)

**Purpose:** Per-player season tracking documents showing a player's game
results, ladders, and season history across multiple teams and clubs.

**Structure:** One YAML config file per player.

```
tracking/
  erin_seasons.yaml       # 17 seasons
  aisling_seasons.yaml    # 20 seasons
```

**Data format:** Tracking YAML is a thin configuration layer. Each season entry
uses `source` + `team` to point to reporting data rather than containing inline
game data:

```yaml
- source: warrandyte_2026_autumn.yaml
  team: Warrandyte Magpies
  type: domestic
  live: true
  ladder_updated: Round 3, Feb 28, 2026

- source: eastern_united_2026_autumn.yaml
  team: Eastern United 17-3
  type: rep
  live: true
  summary_note: "Next Game: Round 6 vs Boroondara Power 17U"
```

**Resolution:** `tracking/loader.py` resolves pointers at generation time:
1. Loads reporting YAML, finds team by name -> Team object
2. Looks up competition_id in registry -> store data directory
3. Auto-generates `all_section_results` from stored match data

**Populated by:** Configuration is hand-maintained. Game data is resolved
automatically from reporting YAML and the regrading store.

**Consumers:** `tracking/render.py` generates markdown documents rendered to
PDF via the `pdf/` pipeline.

### What tracking adds that other stores don't

1. **Cross-club view** -- a player on Warrandyte (domestic) and Eastern United
   (rep) sees both in one document. The reporting store has separate files per
   club.

2. **All-section results** -- full scorecard for every match in the division
   that round, not just the player's team. Auto-generated from regrading store
   match data.

3. **Player-specific context** -- notes like call-up status, coaching feedback,
   next game details. This is genuinely unique to tracking.

4. **Reference tracking** -- monitoring a team the player isn't on (e.g.
   tracking the section above to benchmark call-up readiness). The data exists
   in the other stores but the intent is unique.

---

## Data Flow

```
Netball Connect API                    Hand-maintained
        |                                    |
        v                                    v
  nc/fetch.py + nc/client.py        <club>_heritage.yaml
        |                           (rosters, coaches,
        v                            premierships, notes)
  data/ (JSON store)                       |
    matches, ladders, team IDs             |
    overrides.yaml (manual corrections)    |
        |                                  |
        +---> regrading/                   |
        |         used by: regrading pkg   |
        |                                  |
        +---> nc/reporting_adapter.py      |
        |         cross-pool finals        |
        |         club filtering           |
        |         override application     |
        v                                  v
  reporting/data/ (YAML store)  <-- merge --+
    per-club YAML: fixture + heritage
    used by: reporting/ package
        |
        +---> tracking/loader.py
        |         pointer resolution (source + team -> Team)
        |         all_section auto-generation (from data/ store)
        v
  tracking/*.yaml (config only)
    pointers to reporting YAML
    used by: tracking/ package
```

---

## Historical Coverage Summary

| Year Range | Regrading | Reporting | Tracking |
|------------|-----------|-----------|----------|
| 1998--2012 | -- | Rosters only (Warrandyte) | -- |
| 2013--2021 | -- | Rosters only (Warrandyte) | -- |
| 2022--2025 | Full (all competitions) | Full (11 clubs) | Summary (2 players) |
| 2026 | In progress | In progress | Live (2 players) |

Pre-2022 data was sourced from historical club records and contains player
rosters but no game results, ladders, or finals data. Round-level data begins
in 2022 when Netball Connect became the source for all three stores.
