---
title: "About the Regrading Report"
subtitle: "How to read promotion / demotion recommendations"
theme: regrading
h2_page_break: true
toc: false
tables:
  risk-promotion:
    css_class: risk-promotion
    columns:
      - {name: Boundary}
      - {name: 11U, align: right}
      - {name: 13U, align: right}
      - {name: 15U, align: right}
      - {name: 17U, align: right}
      - {name: Open, align: right}
risk_tables:
  - {class: risk-promotion, columns: all}
---

## What this report does

The regrading report analyses match results across all age groups and identifies teams that appear too strong or too weak for their current section. When it finds a promotion candidate in one section and a demotion candidate above, it recommends swapping them.

It uses the same Netball Connect data visible on the app — win-loss records, scores, and ladders — and nothing else. The committee has context the system doesn't (roster changes, player absences, section size preferences), so the report is a decision-support tool, not a directive.

## The data behind it

**Current season recommendations** use match data from this competition only — the report header states how many rounds were analysed (typically 3–4 at regrading time). Each team is scored on win-loss record, goal average percentage, average margin, and how they compare to teams in adjacent sections.

**Historical figures** (accuracy, likelihood, risk, and outcome tracking) draw on a larger dataset: 40 completed seasons from 2022–2025 across four associations — Manningham (8 seasons), Melbourne East (8 seasons), Lilydale & Yarra Valley (8 seasons), and Waverley Night (16 representative seasons). This covers 5,700+ teams and 813 performance-based committee moves.

**Risk figures specifically** (the Risk column and S1 warnings) use a narrower pool: Manningham and Melbourne East domestic competitions only. These two associations have comparable competition structures. Lilydale & Yarra Valley is excluded from risk calculations because its structurally different competition (more sections per age group, narrower gaps between levels) produces much lower S1 struggle rates that would distort the figures for Manningham.

## Reading the summary table

Each age group has a swap summary with five columns. **Sections** and team names are self-explanatory. The other three:

**Likelihood** — how often committees historically act on similar recommendations. **Likely** means about 70% are actioned; **Possible** means about 40%.

**Risk** — the historical struggle rate when teams are promoted at this age group and boundary. Colour-coded: red (≥50%), amber (25–49%), green (<25%). Higher risk doesn't mean "don't do it" — it means the decision deserves more scrutiny.

## Promotion risk by age and boundary

Based on approximately 180 tracked promotions across Manningham and Melbourne East (2022–2025):

| Boundary | 11U | 13U | 15U | 17U | Open |
|----------|-----|-----|-----|------|------|
| Into S1 | 58% | 55% | 71% | 80% | 67% |
| Into S2 | 21% | 21% | 27% | 33% | 20% |
| Into S3 | 27% | 0% | 33% | 33% | 0% |

The S1 boundary is consistently the hardest — the gap between S1 and S2 is structural, not random. 15U and 17U promotions into S1 are particularly risky.

**Demotions carry no risk.** Across 266 recorded demotions at every boundary and age group, every demoted team settled or thrived. Demoting a struggling S1 team is always safe.

## How outcomes are measured

When we say a move "worked" or a team "struggled", those are based on where the team finished the season in their new section:

| Outcome | What it means | Default threshold |
|---------|---------------|-------------------|
| **Thriving** | Promoted team finished near the top of their new section | Top 40% of section |
| **Competitive** | Holding their own — mid-table in the new section | — |
| **Struggling** | Promoted team finished near the bottom with a poor win rate — both have to be true | Bottom 25% AND ≤30% win rate |
| **Settled** | Demoted team finished in the lower half of their new section — found their level | Bottom 40% of section |
| **Too strong** | Demoted team finished near the top with a dominant win rate — over-demoted | Top 25% AND ≥70% win rate |

"Struggling" and "too strong" are deliberately hard to trigger — both ladder position and win rate must agree. A team that finishes low on the ladder but wins 40% of games is classified as competitive, not struggling. These thresholds are configurable per profile — see [THRESHOLDS.md](THRESHOLDS.md) for the full list.

## How well do recommendations work?

Across 40 seasons, when the system and the committee agreed on a move:

**Promotions:** 83% of promoted teams were competitive or thrived in their new section. The remaining 17% struggled — concentrated at the S1 boundary as shown above.

**Demotions:** 100% success — every demoted team settled or was competitive.

**Recommendations committees didn't act on:** 48% of those teams were still clearly misplaced at season end, confirming the system identified a real problem even when the committee chose not to move them.

Only strong-confidence recommendations appear in the summary tables — these have an **83% correct placement rate** historically (435 moves across 40 seasons). Moderate candidates are highlighted on section ladders (lighter shading) for reference but not listed as recommendations.

## Reading the ladder pages

Below each recommendation is a one-line summary per team:

> ▼ **Team Name** — 4th of 4 · 0W–3L · GA% 40 · +/- -18 · Lost to 1st, 2nd, 3rd

This shows rank, record, goal average percentage, average margin per game, and results by opponent rank — all separated by middots. For S1 boundaries, a detailed risk warning appears with the age-specific figures from the table above.

The system identifies about **91% of teams** that committees eventually move (737 of 813 across 40 seasons). The moves it misses tend to be demotions at deeper section boundaries.
