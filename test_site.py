#!/usr/bin/env python3
"""test_site.py — controleert de gebouwde site/ (links, ankers, afbeeldingen, kopieerknoppen, noindex).
Gebruik: python test_site.py   (na python build.py)"""
import html, re, sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

sys.stdout.reconfigure(encoding="utf-8")
SITE = Path(__file__).resolve().parent / "site"
pages = sorted(SITE.glob("*.html"))
fouten, waarsch = [], []
ids = {}
for p in pages:
    s = p.read_text(encoding="utf-8")
    ids[p.name] = set(re.findall(r'\sid="([^"]+)"', s))

PROMPT_RX = re.compile(r"^(\S+@\S+[:\s].*[$#]\s|\[\S+@\S+ [^\]]*\][$#]|PS [A-Za-z]:\\|[A-Za-z]:\\[^>]*>|\$ |# |MariaDB \[)")
n_links = n_img = n_copy = 0
for p in pages:
    s = p.read_text(encoding="utf-8")
    if 'name="robots" content="noindex' not in s:
        fouten.append(f"{p.name}: geen noindex")
    for attr, url in re.findall(r'\s(href|src)="([^"]+)"', s):
        url = html.unescape(url)
        if url.startswith(("http://", "https://", "mailto:", "data:")):
            continue
        parts = urlsplit(url)
        doel = p.name if not parts.path else unquote(parts.path)
        pad = (SITE / doel)
        if attr == "src" or parts.path:
            if not pad.exists():
                fouten.append(f"{p.name}: ontbrekend bestand {url}")
                continue
        if attr == "src":
            n_img += 1
        else:
            n_links += 1
        if parts.fragment and doel.endswith(".html"):
            if parts.fragment not in ids.get(Path(doel).name, set()):
                fouten.append(f"{p.name}: anker bestaat niet: {url}")
    for soort, c in re.findall(r'data-soort="(\w+)">.*?data-copy="([^"]*)"', s, re.S):
        n_copy += 1
        c = html.unescape(c)
        if not c.strip():
            fouten.append(f"{p.name}: lege kopieerknop")
        elif soort != "bestand" and PROMPT_RX.match(c):
            fouten.append(f"{p.name}: kopieertekst begint met prompt: {c[:70]}")
        elif "…" in c:
            waarsch.append(f"{p.name}: '…' in kopieertekst: {c[:70]}")
    dub = [i for i in re.findall(r'\sid="([^"]+)"', s)]
    if len(dub) != len(set(dub)):
        fouten.append(f"{p.name}: dubbele id's")

for f in ("robots.txt", ".nojekyll", "assets/site.css", "assets/site.js", "assets/zoekindex.js"):
    if not (SITE / f).exists():
        fouten.append(f"ontbreekt: {f}")

print(f"Pagina's: {len(pages)} · interne links: {n_links} · afbeeldingen: {n_img} · kopieerknoppen: {n_copy}")
print(f"Fouten: {len(fouten)}")
for f in fouten[:60]:
    print("  ✗", f)
print(f"Waarschuwingen: {len(waarsch)}")
for w in waarsch[:30]:
    print("  !", w)
sys.exit(1 if fouten else 0)
