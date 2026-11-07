"""Gera assets/activity.svg com os destaques do perfil no GitHub.

Mostra as contribuicoes dos ultimos 12 meses em destaque, ate tres numeros
positivos (crescimento, melhor mes, sites publicados...) e a divisao de
linguagens dos repositorios. Roda so com a biblioteca padrao. Com
GITHUB_TOKEN usa a API GraphQL; sem token, le o calendario publico.

uso: python activity.py [login] [saida]
"""
import base64
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGIN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GH_LOGIN", "ErikEliasV")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent.parent / "assets" / "activity.svg"
TOKEN = os.environ.get("GITHUB_TOKEN")

PANEL = "#111414"
BAR = "#161A1A"
LINE = "#263133"
PAPER = "#F1F1E8"
ASH = "#8A9192"
ACCENT = "#486466"
ACCENT_HI = "#8FB0B2"
LANG_COLORS = [ACCENT_HI, "#6F9193", ACCENT, "#2E4143"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TZ = dt.timezone(dt.timedelta(hours=-3))


def get(url, data=None):
    headers = {"User-Agent": "erikeliasv-profile-activity", "Accept": "application/vnd.github+json"}
    if TOKEN and "api.github.com" in url:
        headers["Authorization"] = f"bearer {TOKEN}"
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
        return r.read().decode("utf-8")


# ------------------------------------------------------------------ dados
def year_days(year):
    """Contribuicoes por dia num ano civil: {date: count}."""
    if TOKEN:
        q = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
          contributionsCollection(from:$from,to:$to){contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""
        res = json.loads(get("https://api.github.com/graphql", {"query": q, "variables": {
            "login": LOGIN, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"}}))
        weeks = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        return {dt.date.fromisoformat(d["date"]): d["contributionCount"] for w in weeks for d in w["contributionDays"]}
    page = get(f"https://github.com/users/{LOGIN}/contributions?from={year}-01-01&to={year}-12-31")
    tips = {m.group(1): m.group(2) for m in re.finditer(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', page)}
    days = {}
    for m in re.finditer(r"<td[^>]*>", page):
        td = m.group(0)
        date = re.search(r'data-date="([^"]+)"', td)
        if not date:
            continue
        cid = re.search(r'\bid="([^"]+)"', td).group(1)
        n = re.match(r"\s*([\d,]+) contribution", tips.get(cid, ""))
        days[dt.date.fromisoformat(date.group(1))] = int(n.group(1).replace(",", "")) if n else 0
    return days


def repo_stats():
    repos = [r for r in json.loads(get(f"https://api.github.com/users/{LOGIN}/repos?per_page=100&type=owner")) if not r["fork"]]
    live = sum(1 for r in repos if r.get("has_pages") or r.get("homepage"))
    langs = Counter()
    for r in repos:
        langs.update(json.loads(get(r["languages_url"])))
    return len(repos), live, langs


# ------------------------------------------------------------------ texto
def fmt(n):
    return f"{n:,}".replace(",", ".")


def font_face(family, filename):
    b64 = base64.b64encode((HERE / "fonts" / filename).read_bytes()).decode()
    return f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{b64}) format('woff2');}}"


SILK_ADV = {"1": 750, ".": 500, ",": 625, "x": 1000, "%": 1000}  # Silkscreen Bold, unidades/1000


def silk_w(text, size, trk):
    return sum(SILK_ADV.get(c, 875) for c in text) / 1000 * size + trk * (len(text) - 1)


def build():
    today = dt.datetime.now(TZ).date()
    days = {}
    for y in range(today.year - 2, today.year + 1):
        days.update(year_days(y))
    last12 = sum(c for d, c in days.items() if today - dt.timedelta(days=365) < d <= today)
    prev12 = sum(c for d, c in days.items() if today - dt.timedelta(days=730) < d <= today - dt.timedelta(days=365))
    months = Counter()
    for d, c in days.items():
        if today - dt.timedelta(days=365) < d <= today:
            months[(d.year, d.month)] += c
    (by, bm), best_month = months.most_common(1)[0] if months else ((today.year, today.month), 0)

    n_repos, live, langs = repo_stats()

    highlights = []
    if prev12 > 0 and last12 / prev12 >= 1.5:
        highlights.append((f"{int(last12 / prev12)}x", "mais que nos 12 meses anteriores"))
    if best_month > 0:
        highlights.append((fmt(best_month), f"no melhor mês, {MESES[bm - 1]}/{by}"))
    if live > 0:
        highlights.append((fmt(live), "sites publicados" if live > 1 else "site publicado"))
    if len(highlights) < 3 and n_repos > 0:
        highlights.append((fmt(n_repos), "repositórios públicos"))
    highlights = highlights[:3]

    total_bytes = sum(langs.values()) or 1
    top = langs.most_common(3)
    parts = [(name, v / total_bytes) for name, v in top]
    rest = 1 - sum(p for _, p in parts)
    if rest > 0.005:
        parts.append(("outros", rest))
    return last12, highlights, parts, today


def render(last12, highlights, parts, today):
    W, H, pad, bar = 1280, 392, 32, 40
    hero = fmt(last12)
    hero_size = 112

    hl = []
    for k, (num, label) in enumerate(highlights):
        y = 112 + k * 52
        x = 700
        hl.append(f'<text class="silk" x="{x}" y="{y}" font-size="36" letter-spacing="-1" fill="{PAPER}">{num}</text>')
        hl.append(f'<text class="mono" x="{x + silk_w(num, 36, -1) + 16:.0f}" y="{y - 2}" font-size="18" fill="{ASH}">{label}</text>')

    lead_name, lead_pct = parts[0] if parts else ("", 0)
    blocks, n_blocks, bw, gap = [], 64, 17, 2
    counts = [round(p * n_blocks) for _, p in parts]
    counts[0] += n_blocks - sum(counts)
    i = 0
    for k, n in enumerate(counts):
        for _ in range(max(n, 0)):
            blocks.append(f'<rect x="{pad + i * (bw + gap)}" y="302" width="{bw}" height="20" fill="{LANG_COLORS[k % 4]}"/>')
            i += 1
    legend, lx = [], pad
    for k, (name, p) in enumerate(parts):
        label = f"{name} {round(p * 100)}%"
        legend.append(f'<rect x="{lx}" y="{348}" width="12" height="12" fill="{LANG_COLORS[k % 4]}"/>')
        legend.append(f'<text class="mono" x="{lx + 20}" y="{359}" font-size="16" fill="{ASH}">{label}</text>')
        lx += 20 + len(label) * 9.6 + 32

    alt = f"{hero} contribuições no GitHub nos últimos 12 meses. " + ". ".join(f"{n} {l}" for n, l in highlights) + f". {lead_name} em {round(lead_pct * 100)}% do código."
    css = font_face("Silk", "silkscreen-digits.woff2") + font_face("Geist", "geist-mono.woff2")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{alt}">
<style>{css}
.silk{{font-family:'Silk',ui-monospace,monospace;font-weight:700}}
.mono{{font-family:'Geist',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
</style>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="{PANEL}" stroke="{LINE}"/>
<rect x="1" y="1" width="{W - 2}" height="{bar - 1}" fill="{BAR}"/>
<rect x="0" y="{bar}" width="{W}" height="1" fill="{LINE}"/>
<rect x="18" y="15" width="10" height="10" fill="{ACCENT}"/>
<rect x="34" y="15" width="10" height="10" fill="#33393A"/>
<rect x="50" y="15" width="10" height="10" fill="#33393A"/>
<text class="mono" x="{W - 18}" y="25" font-size="14" fill="{ASH}" text-anchor="end">github.com/{LOGIN}</text>
<text class="silk" x="{pad - 4}" y="170" font-size="{hero_size}" letter-spacing="-4" fill="{PAPER}">{hero}</text>
<text class="mono" x="{pad}" y="212" font-size="20" fill="{ASH}">contribuições nos últimos 12 meses</text>
{chr(10).join(hl)}
<rect x="{pad}" y="244" width="{W - 2 * pad}" height="1" fill="{LINE}"/>
<text class="mono" x="{pad}" y="284" font-size="18" fill="{PAPER}">{lead_name} em {round(lead_pct * 100)}% do código dos meus repositórios</text>
{chr(10).join(blocks)}
{chr(10).join(legend)}
</svg>'''
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(alt.encode("ascii", "replace").decode())


if __name__ == "__main__":
    render(*build())
