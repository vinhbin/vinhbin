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
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      nodes {
        name
        pushedAt
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


TOP_REPOS = 10  # languages are computed from this many most-recently-pushed public repos

# Coursework / scaffolding repos: excluded so the bar reflects real projects.
EXCLUDE = ("ai110-", "cw", "inclass", "hw0", "matching_card", "flutter", "digital_pet",
           "statemanagement", "mobile-inclass", "free-tailwind")
EXCLUDE_SUFFIX = ("-starter", "-starter2", "-template")


def is_project(name):
    n = name.lower()
    if n.startswith(EXCLUDE) or n.endswith(EXCLUDE_SUFFIX):
        return False
    return True


def compute_languages(repos):
    # Sort locally instead of relying on the API's ordering: the Actions token and a user
    # token return different orders for the same query.
    picked = sorted(
        (r for r in repos if r["name"].lower() != USER.lower() and is_project(r["name"])),
        key=lambda r: r.get("pushedAt") or "",
        reverse=True,
    )[:TOP_REPOS]
    print("language repos:", ", ".join(r["name"] for r in picked))
    # Equal weight per project: average each repo's own language mix, so one huge repo
    # (e.g. notebooks, which embed their image output) can't dominate the bar.
    totals = {}
    for repo in picked:
        edges = repo["languages"]["edges"]
        size = sum(e["size"] for e in edges)
        if not size:
            continue
        for e in edges:
            name = e["node"]["name"]
            totals[name] = totals.get(name, 0) + e["size"] / size
    total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return [(n, 100 * v / total) for n, v in ranked]


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
    parts.append(f'<text x="{rx}" y="{row_y[0]-18}" font-family="{SERIF}" font-size="14" fill="{TEXT}">Top languages · 10 recent projects</text>')
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


def ball_shape(r, top, bottom_op=1.0):
    band = max(1.2, r * 0.3)
    return (
        f'<path d="M{-r} 0 A{r} {r} 0 0 1 {r} 0 Z" fill="{top}"/>'
        f'<path d="M{-r} 0 A{r} {r} 0 0 0 {r} 0 Z" fill="{TEXT}" fill-opacity="{bottom_op}"/>'
        f'<rect x="{-r}" y="{-band/2:.2f}" width="{2*r}" height="{band:.2f}" fill="{BG}"/>'
        f'<circle r="{r*0.36:.2f}" fill="{BG}"/>'
        f'<circle r="{r*0.2:.2f}" fill="{top}"/>'
    )


def creature(r, level):
    """Original tiny monsters drawn from primitives (no third-party sprites).
    Level 1 blob · 2 bird · 3 flame · 4 ghost, colored by intensity."""
    col = [RED, ORANGE, AMBER, TEXT][level - 1]
    eye = BG
    k = r / 6.0  # scale unit (r=7 → k≈1.17)
    if level == 1:  # round blob with ears
        return (
            f'<path d="M{-4.2*k} {-2.5*k} L{-3*k} {-6*k} L{-1.2*k} {-3.6*k} Z" fill="{col}"/>'
            f'<path d="M{4.2*k} {-2.5*k} L{3*k} {-6*k} L{1.2*k} {-3.6*k} Z" fill="{col}"/>'
            f'<circle r="{4.6*k:.2f}" cy="{0.6*k:.2f}" fill="{col}"/>'
            f'<circle cx="{-1.7*k:.2f}" cy="{-0.2*k:.2f}" r="{0.9*k:.2f}" fill="{eye}"/>'
            f'<circle cx="{1.7*k:.2f}" cy="{-0.2*k:.2f}" r="{0.9*k:.2f}" fill="{eye}"/>'
        )
    if level == 2:  # bird: body, beak, wing
        return (
            f'<ellipse rx="{4.4*k:.2f}" ry="{3.8*k:.2f}" cy="{0.8*k:.2f}" fill="{col}"/>'
            f'<circle r="{2.8*k:.2f}" cx="{1.2*k:.2f}" cy="{-2.6*k:.2f}" fill="{col}"/>'
            f'<path d="M{3.6*k} {-2.8*k} L{6.2*k} {-2*k} L{3.6*k} {-1.4*k} Z" fill="{BG}"/>'
            f'<circle cx="{1.6*k:.2f}" cy="{-3.2*k:.2f}" r="{0.8*k:.2f}" fill="{eye}"/>'
            f'<path d="M{-4.2*k} {0.6*k} Q{-2*k} {-1.6*k} {0.4*k} {0.8*k} Z" fill="{BG}" fill-opacity=".45"/>'
        )
    if level == 3:  # flame: teardrop with a tip
        return (
            f'<path d="M0 {-6.4*k} Q{4.8*k} {-1.6*k} {3.2*k} {3.4*k} A{3.4*k} {3.4*k} 0 0 1 {-3.2*k} {3.4*k} Q{-4.8*k} {-1.6*k} 0 {-6.4*k} Z" fill="{col}"/>'
            f'<path d="M{0.4*k} {-2.4*k} Q{2.4*k} {0.2*k} {1.2*k} {2.8*k} A{1.6*k} {1.6*k} 0 0 1 {-1.4*k} {2.6*k} Q{-1.6*k} {0.4*k} {0.4*k} {-2.4*k} Z" fill="{BG}" fill-opacity=".35"/>'
            f'<circle cx="{-1.5*k:.2f}" cy="{0.6*k:.2f}" r="{0.85*k:.2f}" fill="{eye}"/>'
            f'<circle cx="{1.5*k:.2f}" cy="{0.6*k:.2f}" r="{0.85*k:.2f}" fill="{eye}"/>'
        )
    # level 4 ghost: dome top, wavy skirt
    return (
        f'<path d="M{-4.6*k} {4.2*k} L{-4.6*k} {-0.6*k} A{4.6*k} {4.6*k} 0 0 1 {4.6*k} {-0.6*k} L{4.6*k} {4.2*k} '
        f'L{3*k} {2.6*k} L{1.5*k} {4.2*k} L0 {2.6*k} L{-1.5*k} {4.2*k} L{-3*k} {2.6*k} Z" fill="{col}"/>'
        f'<circle cx="{-1.7*k:.2f}" cy="{-0.6*k:.2f}" r="{1*k:.2f}" fill="{eye}"/>'
        f'<circle cx="{1.7*k:.2f}" cy="{-0.6*k:.2f}" r="{1*k:.2f}" fill="{eye}"/>'
    )


def pokeball(cx, cy, r, level, i=0):
    """Grid cell. Level 0 = dim empty slot. Contribution cells show a creature that gets
    hit by the thrown ball, vanishes, and is replaced by a wobbling Pokéball (caught).
    Timing lives in per-cell keyframes (m{i}/b{i}) on the global clock — no animation-delay,
    so every cell resets exactly when the loop restarts."""
    if level == 0:
        return f'<circle cx="{cx}" cy="{cy}" r="{r-0.5}" fill="none" stroke="{SURFACE}" stroke-width="1"/>'
    top = [RED, ORANGE, AMBER, TEXT][level - 1]
    return (
        f'<g class="mon m{i}" transform="translate({cx} {cy})">{creature(r, level)}</g>'
        f'<g class="cb b{i}" transform="translate({cx} {cy})">{ball_shape(r, top)}</g>'
    )


def trainer_ball(r):
    """The ball that gets thrown at the grid."""
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


THROW = 0.9  # seconds per throw


def build_pokegrid(weeks):
    cell, gap = 14, 3
    step = cell + gap
    left, top = 34, 24
    cols = len(weeks)
    W = left + cols * step - gap + 12
    H = top + 7 * step - gap + 12          # bordered grid box
    PAD = 52                                # launch area below the box (outside the border)
    HT = H + PAD
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
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{HT}" viewBox="0 0 {W} {HT}" '
        f'role="img" aria-label="Contribution calendar for {escape(USER)}">',
        "<!-- Each cell is a tiny Pokéball drawn with primitives -->",
        "<!-- style injected below once timing is known -->",
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
    # Contribution cells in chronological order; each gets one throw
    targets = []
    for ci, w in enumerate(weeks):
        for d in w["contributionDays"]:
            wd = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7  # Sunday = 0
            lv = level(d["contributionCount"])
            cx = left + ci * step + r
            cy = top + wd * step + r
            if lv == 0:
                parts.append(pokeball(cx, cy, r, 0))
            else:
                targets.append((cx, cy, lv))
    n = max(1, len(targets))
    DUR = n * THROW + 1.6
    land_frac = 0.78
    for i, (cx, cy, lv) in enumerate(targets):
        parts.append(pokeball(cx, cy, r, lv, i))

    # Throw keyframes: start big at the launch pad (outside the box, bottom-right), arc up and
    # shrink toward the target (fake depth), vanish on impact, reappear at the pad for the next throw.
    sx, sy = W - 36, HT - 22
    kf = []
    def key(t, x, y, sc, op):
        kf.append(f"{100*t/DUR:.3f}%{{transform:translate({x:.1f}px,{y:.1f}px) scale({sc:.2f});opacity:{op}}}")
    for i, (cx, cy, lv) in enumerate(targets):
        t0 = i * THROW
        mx, my = (sx + cx) / 2, min(sy, cy) - 60
        key(t0, sx, sy, 2.3, 1)
        key(t0 + 0.42 * THROW, mx, my, 1.6, 1)
        key(t0 + land_frac * THROW, cx, cy, 0.95, 1)
        key(t0 + (land_frac + 0.04) * THROW, cx, cy, 0.6, 0)
        key(t0 + THROW - 0.02, sx, sy, 2.3, 0)
    key(DUR, sx, sy, 2.3, 1)
    c = lambda sec: f"{100*sec/DUR:.3f}%"
    # Per-cell keyframes on the global clock. Hit time h_i = i*THROW + land_frac*THROW.
    P = lambda sec: f"{100*max(0.0, min(DUR, sec))/DUR:.3f}%"
    reset = DUR - 0.5
    cell_css = []
    for i in range(len(targets)):
        h = i * THROW + land_frac * THROW
        cell_css.append(
            f"@keyframes m{i}{{0%{{transform:scale(1);opacity:1}}{P(h)}{{transform:scale(1);opacity:1}}"
            f"{P(h+0.05)}{{transform:scale(1.5);opacity:1}}{P(h+0.16)}{{transform:scale(.15);opacity:0}}"
            f"{P(reset)}{{transform:scale(.15);opacity:0}}100%{{transform:scale(1);opacity:1}}}}"
            f".m{i}{{animation:m{i} {DUR:.2f}s linear infinite}}"
            f"@keyframes b{i}{{0%{{transform:scale(.3) rotate(0deg);opacity:0}}{P(h+0.14)}{{transform:scale(.3) rotate(0deg);opacity:0}}"
            f"{P(h+0.20)}{{transform:scale(1.4) rotate(0deg);opacity:1}}{P(h+0.30)}{{transform:scale(1.1) rotate(-24deg)}}"
            f"{P(h+0.40)}{{transform:scale(1.1) rotate(24deg)}}{P(h+0.50)}{{transform:scale(1.05) rotate(-14deg)}}"
            f"{P(h+0.60)}{{transform:scale(1) rotate(0deg);opacity:1}}{P(reset)}{{transform:scale(1) rotate(0deg);opacity:1}}"
            f"100%{{transform:scale(.3) rotate(0deg);opacity:0}}}}"
            f".b{i}{{animation:b{i} {DUR:.2f}s linear infinite}}"
        )
    parts.append(
        "<style>"
        ".mon,.cb{transform-box:fill-box;transform-origin:center}.cb{opacity:0}"
        + "".join(cell_css) +
        "@keyframes spin{to{transform:rotate(360deg)}}"
        ".spin{animation:spin .6s linear infinite;transform-box:fill-box;transform-origin:center}"
        f"@keyframes throw{{{''.join(kf)}}}"
        f".throw{{animation:throw {DUR:.2f}s linear infinite}}"
        "</style>"
    )
    # launch pad marker + ball
    parts.append(f'<ellipse cx="{sx}" cy="{sy+16}" rx="18" ry="4" fill="{SURFACE}"/>')
    parts.append(f'<g class="throw" transform="translate({sx} {sy}) scale(2.3)">{trainer_ball(r)}</g>')
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
