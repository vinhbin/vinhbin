#!/usr/bin/env python3
"""Build Ember-themed profile SVGs (stats card + Pokéball contribution grid) from GitHub data.

Stdlib only. Requires GITHUB_TOKEN; GITHUB_USER defaults to "vinhbin".
Writes dist/stats.svg and dist/pokegrid.svg.
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

# Ember palette
BG = "#0D0D0F"
SURFACE = "#1A1A1F"
ORANGE = "#FF6B35"
AMBER = "#FFB347"
RED = "#E63946"
TEXT = "#F5F5F5"
MUTED = "#8A8A8F"

SERIF = "Georgia, 'Times New Roman', serif"
MONO = "ui-monospace, Menlo, Consolas, monospace"

USER = os.environ.get("GITHUB_USER", "vinhbin")
TOKEN = os.environ.get("GITHUB_TOKEN")

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 10, ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def graphql(query, variables):
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is required")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "build_profile.py",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        sys.exit("GraphQL errors: " + json.dumps(payload["errors"], indent=2))
    return payload["data"]


def fetch():
    now = dt.datetime.now(dt.timezone.utc)
    frm = now - dt.timedelta(days=365)
    data = graphql(QUERY, {"login": USER, "from": frm.isoformat(), "to": now.isoformat()})
    return data["user"]


def compute_streak(days):
    """Current streak: consecutive days with contributions ending today (or yesterday)."""
    counts = [d["contributionCount"] for d in days]
    # Today may be zero so far; allow the streak to end yesterday.
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1
    streak = 0
    while i >= 0 and counts[i] > 0:
        streak += 1
        i -= 1
    return streak


def compute_languages(repos):
    totals = {}
    for repo in repos:
        if repo["name"].lower() == USER.lower():  # skip the profile README repo itself
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:5]
    return [(name, size / grand * 100) for name, size in ranked]


def fmt(n):
    return f"{n:,}"


def build_stats(user, streak, langs):
    cc = user["contributionsCollection"]
    total = cc["contributionCalendar"]["totalContributions"]
    stats = [
        (fmt(total), "Contributions"),
        (fmt(cc["totalCommitContributions"]), "Commits"),
        (fmt(cc["totalPullRequestContributions"]), "Pull requests"),
        (f"{streak}d", "Current streak"),
    ]
    W, H = 495, 200
    lang_colors = [RED, ORANGE, AMBER, TEXT, MUTED]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="GitHub stats for {escape(USER)}">',
        f'<rect width="{W}" height="{H}" rx="10" fill="{BG}"/>',
        f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="9" fill="{SURFACE}"/>',
        f'<path d="M14 1.5 H{W-14}" stroke="{ORANGE}" stroke-width="2"/>',
        f'<text x="24" y="34" font-family="{SERIF}" font-size="17" fill="{TEXT}">'
        f'{escape(USER)} <tspan fill="{MUTED}">&#183; last 365 days</tspan></text>',
    ]
    # Left column: 2x2 grid of numbers
    col_x = [24, 140]
    row_y = [78, 146]
    for i, (num, label) in enumerate(stats):
        x = col_x[i % 2]
        y = row_y[i // 2]
        parts.append(
            f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="26" font-weight="bold" fill="{ORANGE}">{num}</text>'
        )
        parts.append(
            f'<text x="{x}" y="{y+18}" font-family="{MONO}" font-size="10.5" fill="{MUTED}">{label.upper()}</text>'
        )
    # Divider
    parts.append(f'<path d="M262 56 V178" stroke="{BG}" stroke-width="1.5"/>')
    # Right column: languages
    rx, bar_y, bar_w, bar_h = 284, 70, 187, 8
    parts.append(f'<text x="{rx}" y="{row_y[0]-18}" font-family="{SERIF}" font-size="14" fill="{TEXT}">Top languages</text>')
    parts.append(f'<clipPath id="bar"><rect x="{rx}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="4"/></clipPath>')
    parts.append(f'<rect x="{rx}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="4" fill="{BG}"/>')
    cursor = rx
    covered = sum(p for _, p in langs)
    for i, (name, pct) in enumerate(langs):
        w = bar_w * pct / 100
        parts.append(f'<rect clip-path="url(#bar)" x="{cursor:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{lang_colors[i]}"/>')
        cursor += w
    for i, (name, pct) in enumerate(langs):
        y = 98 + i * 17
        parts.append(f'<circle cx="{rx+4}" cy="{y-4}" r="4" fill="{lang_colors[i]}"/>')
        parts.append(f'<text x="{rx+14}" y="{y}" font-family="{MONO}" font-size="11.5" fill="{TEXT}">{escape(name)}</text>')
        parts.append(f'<text x="{rx+bar_w}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="11.5" fill="{MUTED}">{pct:.1f}%</text>')
    if not langs:
        parts.append(f'<text x="{rx}" y="98" font-family="{MONO}" font-size="11.5" fill="{MUTED}">no language data</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def pokeball(cx, cy, r, level, idx, n, dur):
    """A tiny Pokéball built from primitives (no sprites). Contribution cells get a
    'catch' animation timed to when the trainer ball passes (idx/n of the loop)."""
    if level == 0:
        return f'<circle cx="{cx}" cy="{cy}" r="{r-0.5}" fill="none" stroke="{SURFACE}" stroke-width="1"/>'
    top = [RED, ORANGE, AMBER, TEXT][level - 1]
    bottom_op = [0.35, 0.55, 0.8, 1.0][level - 1]
    delay = dur * idx / n
    band = max(1.2, r * 0.3)
    return (
        f'<g class="c" style="animation-delay:{delay:.2f}s" transform="translate({cx} {cy})">'
        f'<path d="M{-r} 0 A{r} {r} 0 0 1 {r} 0 Z" fill="{top}"/>'
        f'<path d="M{-r} 0 A{r} {r} 0 0 0 {r} 0 Z" fill="{TEXT}" fill-opacity="{bottom_op}"/>'
        f'<rect x="{-r}" y="{-band/2:.2f}" width="{2*r}" height="{band:.2f}" fill="{BG}"/>'
        f'<circle r="{r*0.36:.2f}" fill="{BG}"/>'
        f'<circle r="{r*0.2:.2f}" fill="{top}"/>'
        f'</g>'
    )


def trainer_ball(r):
    """The big ball that rolls through the grid."""
    band = r * 0.22
    return (
        f'<g class="spin">'
        f'<circle r="{r+1.5}" fill="{BG}"/>'
        f'<path d="M{-r} 0 A{r} {r} 0 0 1 {r} 0 Z" fill="{RED}"/>'
        f'<path d="M{-r} 0 A{r} {r} 0 0 0 {r} 0 Z" fill="{TEXT}"/>'
        f'<rect x="{-r}" y="{-band/2:.2f}" width="{2*r}" height="{band:.2f}" fill="{BG}"/>'
        f'<circle r="{r*0.38:.2f}" fill="{BG}"/>'
        f'<circle r="{r*0.24:.2f}" fill="{TEXT}"/>'
        f'</g>'
    )


DUR = 26  # seconds per full lap of the trainer ball


def build_pokegrid(weeks):
    cell, gap = 12, 3
    step = cell + gap
    left, top = 34, 24
    cols = len(weeks)
    W = left + cols * step - gap + 12
    H = top + 7 * step - gap + 12
    r = cell / 2

    counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    positive = sorted(c for c in counts if c > 0)

    def level(c):
        if c == 0 or not positive:
            return 0
        q = [positive[int(len(positive) * f)] for f in (0.25, 0.5, 0.75)]
        if c <= q[0]:
            return 1
        if c <= q[1]:
            return 2
        if c <= q[2]:
            return 3
        return 4

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Contribution calendar for {escape(USER)}">',
        "<!-- Each cell is a tiny Pokéball drawn with primitives -->",
        "<style>"
        f"@keyframes catch{{0%{{transform:scale(1);opacity:1}}0.6%{{transform:scale(1.9);opacity:1}}1.6%{{transform:scale(1);opacity:.28}}99.2%{{opacity:.28}}100%{{opacity:1}}}}"
        f".c{{animation:catch {DUR}s linear infinite;transform-box:fill-box;transform-origin:center}}"
        "@keyframes spin{to{transform:rotate(360deg)}}"
        ".spin{animation:spin 1.1s linear infinite;transform-box:fill-box;transform-origin:center}"
        "</style>",
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="8" fill="none" stroke="{SURFACE}"/>',
    ]
    # Month labels
    last_month = None
    for ci, w in enumerate(weeks):
        first = dt.date.fromisoformat(w["contributionDays"][0]["date"])
        if first.month != last_month:
            if last_month is not None or first.day <= 7:
                x = left + ci * step
                if x + 24 < W - 4:
                    parts.append(f'<text x="{x}" y="{top-9}" font-family="{MONO}" font-size="9" fill="{MUTED}">{first.strftime("%b")}</text>')
            last_month = first.month
    # Weekday labels
    for wd, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = top + wd * step + cell / 2 + 3
        parts.append(f'<text x="{left-8}" y="{y:.1f}" text-anchor="end" font-family="{MONO}" font-size="9" fill="{MUTED}">{name}</text>')
    # Cells, visited in a serpentine order (down col 0, up col 1, ...) by the trainer ball
    order = []  # (cx, cy) in visit order
    cells = {}
    for ci, w in enumerate(weeks):
        for d in w["contributionDays"]:
            wd = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7  # Sunday = 0
            cells[(ci, wd)] = d["contributionCount"]
    for ci in range(cols):
        rows = range(7) if ci % 2 == 0 else range(6, -1, -1)
        for wd in rows:
            order.append((ci, wd))
    n = len(order)
    for idx, (ci, wd) in enumerate(order):
        if (ci, wd) not in cells:
            continue
        cx = left + ci * step + r
        cy = top + wd * step + r
        parts.append(pokeball(cx, cy, r, level(cells[(ci, wd)]), idx, n, DUR))
    # Trainer ball path as a CSS keyframe list (no SMIL: it leaves a static ghost at the origin in some renderers)
    pts = [(left + ci*step + r, top + wd*step + r) for ci, wd in order]
    pts.append(pts[0])
    frames = "".join(f"{100*i/(len(pts)-1):.3f}%{{transform:translate({x:.1f}px,{y:.1f}px)}}" for i, (x, y) in enumerate(pts))
    parts.append(f"<style>@keyframes roll{{{frames}}}.roll{{animation:roll {DUR}s linear infinite}}</style>")
    x0, y0 = pts[0]
    parts.append(f'<g class="roll" transform="translate({x0:.1f} {y0:.1f})">{trainer_ball(r + 2.5)}</g>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    user = fetch()
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    streak = compute_streak(days)
    langs = compute_languages(user["repositories"]["nodes"])

    os.makedirs("dist", exist_ok=True)
    with open("dist/stats.svg", "w", encoding="utf-8") as f:
        f.write(build_stats(user, streak, langs))
    with open("dist/pokegrid.svg", "w", encoding="utf-8") as f:
        f.write(build_pokegrid(weeks))

    cc = user["contributionsCollection"]
    print(f"contributions={cc['contributionCalendar']['totalContributions']} commits={cc['totalCommitContributions']} "
          f"prs={cc['totalPullRequestContributions']} issues={cc['totalIssueContributions']} "
          f"restricted={cc['restrictedContributionsCount']} streak={streak}")
    print("languages:", ", ".join(f"{n} {p:.1f}%" for n, p in langs))


if __name__ == "__main__":
    main()
