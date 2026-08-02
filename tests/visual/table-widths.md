---
title: "Synthetic table-width acceptance"
subtitle: "Invented content only - no consumer data"
lang: en-AU
theme: neutral
h2_page_break: true
risk_tables: [risk]
direction_markers: true
---

## Automatic ladders and shared widths

<table id="ladder-primary">
<caption>Primary synthetic ladder</caption>
<thead><tr><th id="lp-team" scope="col">Team</th><th id="lp-p" scope="col">P</th><th id="lp-w" scope="col">W</th><th id="lp-l" scope="col">L</th><th id="lp-d" scope="col">D</th><th id="lp-gf" scope="col">GF</th><th id="lp-ga" scope="col">GA</th><th id="lp-pct" scope="col">%</th></tr></thead>
<tbody>
<tr><th id="lp-r1" scope="row">North Comets</th><td headers="lp-r1 lp-p">12</td><td headers="lp-r1 lp-w">10</td><td headers="lp-r1 lp-l">2</td><td headers="lp-r1 lp-d">0</td><td headers="lp-r1 lp-gf">286</td><td headers="lp-r1 lp-ga">193</td><td headers="lp-r1 lp-pct">148.2%</td></tr>
<tr><th id="lp-r2" scope="row">River Kites</th><td headers="lp-r2 lp-p">12</td><td headers="lp-r2 lp-w">7</td><td headers="lp-r2 lp-l">4</td><td headers="lp-r2 lp-d">1</td><td headers="lp-r2 lp-gf">241</td><td headers="lp-r2 lp-ga">220</td><td headers="lp-r2 lp-pct">109.5%</td></tr>
</tbody>
</table>

<table id="ladder-secondary">
<caption>Secondary synthetic ladder</caption>
<thead><tr><th scope="col">Team</th><th scope="col">P</th><th scope="col">W</th><th scope="col">L</th><th scope="col">D</th><th scope="col">GF</th><th scope="col">GA</th><th scope="col">%</th></tr></thead>
<tbody>
<tr><th scope="row">Harbour Owls</th><td>9</td><td>6</td><td>3</td><td>0</td><td>198</td><td>177</td><td>111.9%</td></tr>
<tr><th scope="row">Forest Rays</th><td>9</td><td>4</td><td>5</td><td>0</td><td>164</td><td>189</td><td>86.8%</td></tr>
</tbody>
</table>

## Schedules and summaries

<table id="schedule-morning">
<caption>Morning schedule</caption>
<thead><tr><th scope="col">Time</th><th scope="col">Court</th><th scope="col">Home</th><th scope="col">Away</th><th scope="col">Date</th></tr></thead>
<tbody>
<tr><td>09:00</td><td>1</td><td>North Comets</td><td>River Kites</td><td>14 Jun</td></tr>
<tr><td>10:15</td><td>12</td><td>Harbour Owls</td><td>Forest Rays</td><td>14 Jun</td></tr>
</tbody>
</table>

<table id="schedule-evening">
<caption>Evening schedule</caption>
<thead><tr><th scope="col">Time</th><th scope="col">Court</th><th scope="col">Home</th><th scope="col">Away</th><th scope="col">Date</th></tr></thead>
<tbody>
<tr><td>18:30</td><td>3</td><td>Valley Larks</td><td>Coastal Wren Collective</td><td>2026-06-21</td></tr>
<tr><td>19:45</td><td>4</td><td>Summit Foxes</td><td>Garden Stars</td><td>2026-06-21</td></tr>
</tbody>
</table>

<table id="summary-risk" class="risk">
<caption>Synthetic risk summary</caption>
<thead><tr><th scope="col">Section</th><th scope="col">Team</th><th scope="col">Status</th><th scope="col">Risk</th></tr></thead>
<tbody>
<tr><td>11U A</td><td>North Comets</td><td>READY</td><td>12%</td></tr>
<tr><td>13U B</td><td>River Kites</td><td>WATCH</td><td>37%</td></tr>
<tr><td>15U C</td><td>Forest Rays</td><td>REVIEW</td><td>68%</td></tr>
</tbody>
</table>

## Prose, wrapping, and semantic states

<table id="prose-table">
<caption>Prose wrapping sentinels</caption>
<thead><tr><th scope="col">Item</th><th scope="col">Owner</th><th scope="col">Notes</th></tr></thead>
<tbody>
<tr><td>SingleLineSentinel</td><td>North Comets</td><td>Short text remains calm and readable.</td></tr>
<tr><td>WrapSentinel</td><td>Coastal Wren Collective</td><td>This deliberately longer sentence must wrap inside the notes cell without clipping or crossing its border.</td></tr>
<tr><td>LongToken</td><td>Garden Stars</td><td>https://example.invalid/synthetic/averyveryveryvery<wbr>veryveryveryveryveryvery<wbr>veryveryveryveryveryvery<wbr>veryveryveryveryveryvery<wbr>longsegmentthatmustwrap</td></tr>
</tbody>
</table>

<table id="semantic-states">
<caption>Redundant semantic state cues</caption>
<thead><tr><th scope="col">State</th><th scope="col">Result</th><th scope="col">Cue</th></tr></thead>
<tbody>
<tr class="tl-green verdict-success"><td>GREEN</td><td>PASS</td><td>✓ ready</td></tr>
<tr class="tl-amber verdict-warning"><td>AMBER</td><td>WATCH</td><td>! review</td></tr>
<tr class="tl-red verdict-failure"><td>RED</td><td>STOP</td><td>× blocked</td></tr>
<tr class="highlight-up"><td>UP</td><td>IMPROVING</td><td>▲ rising</td></tr>
<tr class="highlight-down"><td>DOWN</td><td>DECLINING</td><td>▼ falling</td></tr>
</tbody>
</table>

## Intentionally wide table

<table id="overwide-table">
<caption>Portrait and landscape width comparison</caption>
<thead><tr><th scope="col">Date</th><th scope="col">Time</th><th scope="col">Court</th><th scope="col">Home</th><th scope="col">Away</th><th scope="col">P</th><th scope="col">W</th><th scope="col">L</th><th scope="col">GF</th><th scope="col">GA</th><th scope="col">%</th><th scope="col">Notes</th></tr></thead>
<tbody>
<tr><td>2026-07-18</td><td>09:00</td><td>12</td><td>Coastal Wren Collective</td><td>Metropolitan Aurora Ensemble</td><td>12</td><td>10</td><td>2</td><td>286</td><td>193</td><td>148.2%</td><td>Long landscape comparison note with deliberate wrapping.</td></tr>
<tr><td>2026-07-25</td><td>10:15</td><td>3</td><td>North Comets</td><td>River Kites</td><td>12</td><td>7</td><td>5</td><td>241</td><td>220</td><td>109.5%</td><td>Second synthetic comparison row.</td></tr>
</tbody>
</table>
