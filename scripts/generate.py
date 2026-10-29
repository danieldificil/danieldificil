#!/usr/bin/env python3
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    SAO_PAULO = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:
    # No tzdata on the runner; Brazil has had no daylight saving time since 2019.
    SAO_PAULO = timezone(timedelta(hours=-3))

PHRASES = {
    "franky_fixed": "franky fixed {n} review comments",
    "qa": "chopper caught an issue in QA",
    "delivery": "{agent} shipped a feature",
    "task": "{agent} completed a task",
    "routine": "{agent} ran a scheduled routine",
}
NICKNAMES = {"korosensei": "koro"}
CREW = {"franky", "chopper", "korosensei", "nami", "robin", "vegapunk"}
SECTORS = ("Engineering", "DificilTech")
OUTPUTS = ("profile.svg", "mission-control.svg", "log.svg", "button-linkedin.svg", "button-site.svg")
METRICS = ("tasks", "prs_fixed", "qa_catches", "pre_review_blocks")

MAX_DAYS_ON_DUTY = 1
MAX_EVENTS = 12
WIDTH = 840
HALF = 412
MARGIN = 28
CHAR_WIDTH = 0.6

BACKGROUND = "#07040f"
CARD = "#0c0719"
BORDER = "#2b1660"
UV_BASE = "#5C1FD0"
UV = "#a77bff"
TEXT = "#c9b8ff"
DIM = "#6b5a99"
GREEN = "#3ef0a0"
RAIL = "#1a1030"

FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono','DejaVu Sans Mono',monospace"


def phrase(event):
    template = PHRASES.get(event.get("type"))
    agent = event.get("agent")
    if template is None or agent not in CREW:
        return None
    n = event.get("n")
    if event["type"] == "franky_fixed":
        if not isinstance(n, int) or n <= 0:
            return None
        if n == 1:
            template = template.replace("comments", "comment")
    return template.format(agent=NICKNAMES.get(agent, agent), n=n)


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _day(day):
    return day.strftime("%d/%m")


def _machine(data):
    return str(data.get("machine", "?")).replace("-", " ")


def status(generated_on, now):
    day = _date(generated_on)
    if day is None:
        return ("awaiting", None)
    days = max(0, (now.astimezone(SAO_PAULO).date() - day).days)
    return ("on_duty" if days <= MAX_DAYS_ON_DUTY else "low_orbit", days)


def load(data_dir):
    sectors = dict.fromkeys(SECTORS)
    for path in sorted(Path(data_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("sector") in sectors:
            sectors[data["sector"]] = data
    return sectors


def log_events(sectors):
    valid = []
    for name, data in sectors.items():
        events = (data or {}).get("events")
        for event in events if isinstance(events, list) else []:
            if isinstance(event, dict) and _date(event.get("on")) and phrase(event):
                valid.append((name, event))
    valid.sort(key=lambda pair: _date(pair[1]["on"]), reverse=True)
    return valid[:MAX_EVENTS]


def _integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _plural(n, singular, plural):
    return singular if n == 1 else plural


def _text(x, y, content, css_class, **attrs):
    extras = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<text x="{x}" y="{y}" class="{css_class}"{extras}>{escape(str(content))}</text>'


def _svg(width, height, title, css, body):
    style = f"""
text{{font-family:{FONT}}}
.t{{fill:{TEXT}}}.uv{{fill:{UV}}}.ok{{fill:{GREEN}}}.dim{{fill:{DIM}}}.w{{fill:#fff}}
.hd{{font-size:13px;font-weight:700;letter-spacing:2.5px}}.hdr{{font-size:11px;font-weight:700;letter-spacing:2px}}
.pulse{{animation:p 2s ease-in-out infinite}}@keyframes p{{50%{{opacity:.3}}}}
.scan{{animation:s 3.2s linear infinite}}@keyframes s{{from{{transform:translateY(-40px)}}to{{transform:translateY({height}px)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
{css}"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<style>{style}</style>
<defs>
<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#140c28" stroke-width="1"/></pattern>
<linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="{UV_BASE}" stop-opacity="0"/><stop offset=".5" stop-color="{UV}"/><stop offset="1" stop-color="{UV_BASE}" stop-opacity="0"/></linearGradient>
<linearGradient id="trail" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{UV_BASE}" stop-opacity="0"/><stop offset="1" stop-color="{UV_BASE}" stop-opacity=".16"/></linearGradient>
<linearGradient id="track" x1="0" x2="1"><stop offset="0" stop-color="{UV_BASE}"/><stop offset="1" stop-color="{UV}"/></linearGradient>
<linearGradient id="track-ok" x1="0" x2="1"><stop offset="0" stop-color="#1f8f63"/><stop offset="1" stop-color="{GREEN}"/></linearGradient>
<clipPath id="frame"><rect width="{width}" height="{height}" rx="10"/></clipPath>
</defs>
<g clip-path="url(#frame)">
<rect width="{width}" height="{height}" fill="{BACKGROUND}"/>
<rect width="{width}" height="{height}" fill="url(#grid)" opacity=".7"/>
{body}
<g class="scan"><rect y="0" width="{width}" height="40" fill="url(#trail)"/><rect y="39" width="{width}" height="1.5" fill="url(#beam)"/></g>
</g>
<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="10" fill="none" stroke="{BORDER}"/>
{_corners(width, height)}
</svg>
"""


def _corners(width, height, arm=14, inset=7):
    d, r = arm, inset
    paths = [
        f"M{r} {r + d}V{r}H{r + d}",
        f"M{width - r - d} {r}H{width - r}V{r + d}",
        f"M{r} {height - r - d}V{height - r}H{r + d}",
        f"M{width - r - d} {height - r}H{width - r}V{height - r - d}",
    ]
    return "".join(f'<path d="{p}" fill="none" stroke="{UV_BASE}" stroke-width="2"/>' for p in paths)


def _header(title, right, right_class, width=WIDTH):
    return (
        _text(MARGIN, 36, title, "uv hd")
        + _text(width - MARGIN, 36, right, f"{right_class} hdr", text_anchor="end")
        + f'<path d="M{MARGIN} 50H{width - MARGIN}" stroke="{BORDER}"/>'
        + f'<path d="M{MARGIN} 50H{MARGIN + 120}" stroke="{UV_BASE}" stroke-width="2"/>'
    )


def _cell(x, y, label, value_svg):
    return (
        _text(x, y, label, "dim", font_size="9.5", letter_spacing="1.2")
        + f'<text x="{x}" y="{y + 25}">{value_svg}</text>'
    )


def _number(key, n, unit):
    return (
        f'<tspan class="w" font-size="23" font-weight="700" data-metric="{key}">{n}</tspan>'
        f'<tspan class="dim" font-size="11" dx="7">{escape(unit)}</tspan>'
    )


def _sector_card(x, y, width, height, name, data, now):
    state, days = status((data or {}).get("generated_on"), now)
    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="6" fill="{CARD}" fill-opacity=".85" stroke="{BORDER}"/>',
        f'<path d="M{x} {y + 18}V{y + 6}Q{x} {y} {x + 6} {y}H{x + 40}" fill="none" stroke="{UV}" stroke-width="1.5"/>',
        _text(x + 18, y + 30, f"SECTOR {name.upper()}", "w", font_size="13.5", font_weight="700", letter_spacing="1.8"),
    ]
    right = x + width - 18
    if state == "awaiting":
        cx, cy = x + width / 2, y + height / 2 + 14
        parts += [
            _text(right, y + 30, "◌ NO SIGNAL", "dim", text_anchor="end", font_size="11", letter_spacing="1"),
            f'<path d="M{x + 18} {y + 58}H{right}" stroke="{BORDER}" stroke-dasharray="2 4"/>',
            f'<circle cx="{cx}" cy="{cy - 26}" r="6" fill="none" stroke="{UV}" stroke-width="1.5">'
            '<animate attributeName="r" values="6;34" dur="2.4s" repeatCount="indefinite"/>'
            '<animate attributeName="opacity" values="1;0" dur="2.4s" repeatCount="indefinite"/></circle>',
            f'<circle cx="{cx}" cy="{cy - 26}" r="3.5" fill="{UV}" class="pulse"/>',
            _text(cx, cy + 22, "AWAITING FIRST CONTACT", "uv pulse", text_anchor="middle", font_size="12", font_weight="700", letter_spacing="2"),
            _text(cx, cy + 42, "this sector hasn't transmitted yet", "dim", text_anchor="middle", font_size="10.5"),
        ]
        return "".join(parts)

    if state == "on_duty":
        parts.append(_text(right, y + 30, "● ON DUTY", "ok pulse", text_anchor="end", font_size="11.5", font_weight="700", letter_spacing="1.5"))
        contact = f"transmitted {_day(_date(data['generated_on']))}"
    else:
        parts.append(_text(right, y + 30, "◌ LOW ORBIT", "uv", text_anchor="end", font_size="11.5", font_weight="700", letter_spacing="1.5"))
        contact = f"last transmission {days} days ago"

    sub = [_machine(data), contact]
    clients = _integer(data.get("active_clients"))
    if clients:
        sub.append(f"{clients} {_plural(clients, 'active client', 'active clients')}")
    parts += [
        _text(x + 18, y + 48, " · ".join(sub), "dim", font_size="10.5"),
        f'<path d="M{x + 18} {y + 60}H{right}" stroke="{BORDER}"/>',
    ]

    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    m = {k: _integer(metrics.get(k)) for k in METRICS}
    agents = data.get("agents")
    crew = len(agents) if isinstance(agents, list) else 0
    window = _integer(data.get("window_days")) or 7

    last = data.get("last_action") if isinstance(data.get("last_action"), dict) else {}
    on = _date(last.get("on"))
    if last.get("agent") in CREW and on:
        nickname = NICKNAMES.get(last["agent"], last["agent"])
        last_svg = f'<tspan class="ok" font-size="13" font-weight="700">{escape(nickname)} · {escape(_day(on))}</tspan>'
    else:
        last_svg = '<tspan class="dim" font-size="13">—</tspan>'

    cells = [
        ("AI CREW", _number("crew", crew, _plural(crew, "agent", "agents"))),
        ("TASKS", _number("tasks", m["tasks"], f"in {window} days")),
        ("PRs FIXED", _number("prs_fixed", m["prs_fixed"], "by franky")),
        ("BUGS CAUGHT IN QA", _number("qa_catches", m["qa_catches"], "by chopper")),
        ("BLOCKED IN PRE-REVIEW", _number("pre_review_blocks", m["pre_review_blocks"], "before push")),
        ("LAST ACTION", last_svg),
    ]
    column = (width - 36) / 2
    for i, (label, value) in enumerate(cells):
        cx = x + 18 + (i % 2) * column
        cy = y + 84 + (i // 2) * 47
        parts.append(f'<rect x="{cx - 8}" y="{cy - 9}" width="2" height="34" fill="{UV_BASE}" opacity=".7"/>')
        parts.append(_cell(cx, cy, label, value))
    return "".join(parts)


def mission_control(sectors, now):
    height = 306
    card_width = (WIDTH - 2 * MARGIN - 16) / 2
    window = next((_integer(d.get("window_days")) for d in sectors.values() if d), 0) or 7
    body = _header("◢ MISSION CONTROL", f"TELEMETRY · LAST {window} DAYS", "dim")
    for i, name in enumerate(SECTORS):
        x = MARGIN + i * (card_width + 16)
        body += _sector_card(x, 66, card_width, 216, name, sectors.get(name), now)
    body += _text(WIDTH / 2, height - 9, "hermes · AI agent crew across two ships", "dim", text_anchor="middle", font_size="9", letter_spacing="1.5", opacity=".8")
    return _svg(WIDTH, height, "Mission Control: telemetry from the AI agent crew", "", body)


def ships_log(sectors, height):
    step, top, bottom = 42, 66, 18
    visible = (height - top - bottom) // step
    window = height - top - bottom
    events = log_events(sectors)
    body = _header("◢ SHIP'S LOG", "● LIVE", "ok pulse", HALF)

    if not events:
        middle = top + window / 2
        body += _text(HALF / 2, middle, "◌ crew at rest", "uv pulse", text_anchor="middle", font_size="14", font_weight="700", letter_spacing="1.5")
        body += _text(HALF / 2, middle + 22, "no actions logged in the window", "dim", text_anchor="middle", font_size="10.5")
        return _svg(HALF, height, "Ship's log of the AI agent crew", "", body)

    rows = []
    for name, event in events:
        head, _, rest = phrase(event).partition(" ")
        day = _day(_date(event["on"]))
        rows.append(
            f'<path d="M{MARGIN} {{y0}}V{{y1}}" stroke="{UV_BASE}" stroke-width="2" opacity=".7"/>'
            f'<text y="{{y0}}" dy="9" font-size="9.5" letter-spacing="1.2"><tspan x="{MARGIN + 12}" class="dim">{escape(day)}</tspan>'
            f'<tspan x="{HALF - MARGIN}" text-anchor="end" class="dim">{escape(name.upper())}</tspan></text>'
            f'<text x="{MARGIN + 12}" y="{{y0}}" dy="27" font-size="12.5"><tspan class="uv" font-weight="700">{escape(head)}</tspan>'
            f'<tspan class="t"> {escape(rest)}</tspan></text>'
        )

    # With few rows, the duplicated list would show the same event twice inside the window.
    scrolls = len(rows) > visible
    first = top + 12
    copies = rows * 2 if scrolls else rows
    feed = "".join(
        template.replace("{y0}", str(first + i * step)).replace("{y1}", str(first + i * step + 30))
        for i, template in enumerate(copies)
    )
    css = ""
    if scrolls:
        cycle = len(rows) * step
        css = f".feed{{animation:f {len(rows) * 2.4:.1f}s linear infinite}}@keyframes f{{to{{transform:translateY(-{cycle}px)}}}}"
        body += (
            f'<defs><clipPath id="window"><rect x="0" y="{top}" width="{HALF}" height="{window}"/></clipPath>'
            f'<linearGradient id="fog" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{BACKGROUND}"/><stop offset=".06" stop-color="{BACKGROUND}" stop-opacity="0"/>'
            f'<stop offset=".92" stop-color="{BACKGROUND}" stop-opacity="0"/><stop offset="1" stop-color="{BACKGROUND}"/></linearGradient></defs>'
            f'<g clip-path="url(#window)"><g class="feed">{feed}</g></g>'
            f'<rect x="0" y="{top}" width="{HALF}" height="{window}" fill="url(#fog)"/>'
        )
    else:
        body += feed
    return _svg(HALF, height, "Ship's log of the AI agent crew", css, body)


def _flight_path(cfg):
    return [r for r in cfg.get("flight_path", []) if isinstance(r, dict) and isinstance(r.get("year"), int)]


def profile_height(cfg):
    return 176 + 23 * len(_flight_path(cfg)) + 4 + 78


def profile(cfg):
    path = _flight_path(cfg)
    start = min((r["year"] for r in path), default=2020)
    end = max((r["year"] for r in path), default=start) + 1
    left, right = MARGIN + 4, HALF - MARGIN - 44
    scale = (right - left) / (end - start)
    top, step = 176, 23
    axis = top + step * len(path) + 4
    height = profile_height(cfg)

    subtitle = cfg.get("subtitle", "")
    first, _, second = subtitle.rpartition(" · ")
    body = _header("◢ COMMANDER PROFILE", "◈ DIFICILTECH", "uv", HALF)
    body += _text(MARGIN, 88, cfg.get("name", ""), "w", font_size="26", font_weight="700", letter_spacing="3")
    body += _text(MARGIN, 110, first or second, "dim", font_size="11.5")
    if first:
        body += _text(MARGIN, 126, second, "dim", font_size="11.5")
    body += _text(MARGIN, 156, "FLIGHT PATH", "dim", font_size="10", letter_spacing="2.5")
    body += _text(MARGIN + 112, 156, f"{start} → today", "dim", font_size="9.5", opacity=".75")

    for year in range(start, end):
        x = left + (year - start) * scale
        body += f'<path d="M{x:.1f} {top - 12}V{axis}" stroke="{BORDER}" stroke-dasharray="1 4"/>'
        body += _text(f"{x:.1f}", axis + 18, year, "dim", font_size="10.5", text_anchor="middle")
    body += f'<path d="M{left} {axis}H{right}" stroke="{BORDER}" stroke-width="1.5"/>'
    body += f'<path d="M{right} {top - 14}V{axis}" stroke="{GREEN}" stroke-opacity=".5" stroke-dasharray="3 3"/>'
    body += _text(right, axis + 18, "today", "ok", font_size="10.5", text_anchor="middle", font_weight="700")

    # Stagger by duration, not delay: with fill-mode backwards the bar vanishes when the reader does not animate.
    css = (
        ".seg{transform-box:fill-box;transform-origin:0 50%;animation:g 1s cubic-bezier(.2,.7,.2,1)}"
        "@keyframes g{from{transform:scaleX(0)}}"
    )
    for i, item in enumerate(path):
        x = left + (item["year"] - start) * scale
        y = top + i * step
        highlight = bool(item.get("highlight"))
        css_class = "ok" if highlight else "t"
        fill = "url(#track-ok)" if highlight else "url(#track)"
        duration = f"animation-duration:{0.9 + i * 0.12:.2f}s"
        tech = item.get("tech", "")
        # At half-column width, a track that starts late has no room for the label right of its dot.
        if x + len(tech) * 11 * CHAR_WIDTH > right:
            body += _text(f"{x - 8:.1f}", y + 4, tech, css_class, font_size="11", font_weight="700" if highlight else "400", text_anchor="end")
        else:
            body += _text(f"{x:.1f}", y, tech, css_class, font_size="11", font_weight="700" if highlight else "400")
        body += f'<rect x="{left}" y="{y + 5}" width="{right - left}" height="3" rx="1.5" fill="{RAIL}" opacity=".6"/>'
        body += f'<rect class="seg" style="{duration}" x="{x:.1f}" y="{y + 4}" width="{right - x:.1f}" height="5" rx="2.5" fill="{fill}"/>'
        body += f'<circle cx="{x:.1f}" cy="{y + 6.5}" r="2.5" fill="{BACKGROUND}" stroke="{GREEN if highlight else UV}" stroke-width="1.5"/>'
        if highlight:
            body += f'<circle cx="{right}" cy="{y + 6.5}" r="4" fill="{GREEN}" class="pulse"/>'
            body += _text(right + 12, y + 10, "↑ new", "ok", font_size="10")

    footer = axis + 54
    body += f'<path d="M{MARGIN} {footer - 20}H{HALF - MARGIN}" stroke="{BORDER}"/>'
    body += _text(MARGIN, footer, cfg.get("status", ""), "ok pulse", font_size="13", font_weight="700", letter_spacing="1.2")
    body += _text(HALF - MARGIN, footer, "open channel ▾", "dim", font_size="10.5", text_anchor="end", letter_spacing="1")
    return _svg(HALF, height, f"Commander profile: {cfg.get('name', '')}", css, body)


def button(label):
    height = 44
    width = int(56 + len(label) * 8.6)
    css = (
        ".shine{animation:b 4s ease-in-out infinite}"
        f"@keyframes b{{0%,55%{{transform:translateX(-80px)}}100%{{transform:translateX({width + 80}px)}}}}"
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">
<title>{escape(label)}</title>
<style>text{{font-family:{FONT}}}{css}@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}</style>
<defs>
<linearGradient id="light" x1="0" x2="1"><stop offset="0" stop-color="{UV}" stop-opacity="0"/><stop offset=".5" stop-color="{UV}" stop-opacity=".35"/><stop offset="1" stop-color="{UV}" stop-opacity="0"/></linearGradient>
<clipPath id="body"><rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="5"/></clipPath>
</defs>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="5" fill="#140a2b"/>
<g clip-path="url(#body)"><rect class="shine" x="0" y="0" width="60" height="{height}" fill="url(#light)" transform="skewX(-20)"/></g>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="5" fill="none" stroke="{UV_BASE}" stroke-width="1.5"/>
<path d="M6 12V6H12M{width - 12} {height - 6}H{width - 6}V{height - 12}" fill="none" stroke="{UV}" stroke-width="1.5"/>
<text x="{width / 2}" y="{height / 2 + 4.5}" text-anchor="middle" font-size="13" font-weight="700" letter-spacing="1"><tspan fill="{UV}">▸ </tspan><tspan fill="#fff">{escape(label)}</tspan></text>
</svg>
"""


def main(root=Path("."), now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    sectors = load(root / "data")
    cfg = json.loads((root / "config" / "profile.json").read_text(encoding="utf-8"))
    contents = dict(zip(OUTPUTS, (
        profile(cfg),
        mission_control(sectors, now),
        ships_log(sectors, profile_height(cfg)),
        button("LinkedIn"),
        button("dificiltech.com"),
    )))
    out = root / "svg"
    out.mkdir(exist_ok=True)
    for name, svg in contents.items():
        (out / name).write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
