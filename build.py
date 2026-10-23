#!/usr/bin/env python3
"""
build.py — zet de Word-hoofdstukken in docs/ om naar een statische website in site/.

Gebruik:
    python build.py                 # bouwt site/ en dist/cursus-offline.zip
    python build.py --preview       # idem, met stijlkiezer (voor het kiezen van een stijl)
    python build.py --stijl blauwdruk

Nieuw hoofdstuk toevoegen: zet "<nummer> <titel>.docx" in docs/ en draai het script opnieuw.
Vereist: Python 3.9+ en python-docx (pip install python-docx).
"""
import argparse, html, json, os, re, shutil, sys, zipfile
from pathlib import Path

import docx
sys.stdout.reconfigure(encoding="utf-8")
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
OUT = ROOT / "site"
TEMPLATE = ROOT / "template"
DIST = ROOT / "dist"

# Toestel voor commando's zonder prompt (Andrii: "alles op de RHEL VM, behalve de Windows host").
STANDAARD_TOESTEL = "RHEL VM · serverXX"

SITE_TITLE = "Containers op RHEL 10"
SITE_SUB = "Docker · Podman · Kubernetes"
MONO_FONTS = ("cascadia", "courier", "consolas", "menlo", "monaco", "lucida console", "source code")
EMU_PER_PX = 9525

# Plaatsen waar het toestel niet uit de prompt volgt, maar wel ondubbelzinnig uit de koptekst.
# (hoofdstuknummer, regex op de huidige kop) -> prefix voor het label
SECTIE_LABELS = [
    (7, re.compile(r"terminal", re.I), "VS Code-terminal → "),
]

# ---------------------------------------------------------------- helpers

def esc(s):
    return html.escape(s, quote=True)

def slugify(s):
    s = s.lower()
    s = (s.replace("ë", "e").replace("é", "e").replace("è", "e").replace("ï", "i")
           .replace("ö", "o").replace("ü", "u").replace("’", "").replace("'", ""))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "sectie"

def is_true(el, tag):
    """w:b / w:i etc.: aanwezig en niet uitgeschakeld."""
    x = el.find(qn(tag)) if el is not None else None
    if x is None:
        return False
    v = x.get(qn("w:val"))
    return v not in ("0", "false", "none")

# ---------------------------------------------------------------- prompts & toestellen

RE_UNIX_A = re.compile(r"^(?P<prompt>(?P<user>[\w.-]+)@(?P<host>[\w.-]+):(?P<path>[^\s$#]*)(?P<sig>[$#]))(?P<rest>.*)$")
RE_UNIX_B = re.compile(r"^(?P<prompt>\[(?P<user>[\w.-]+)@(?P<host>[\w.-]+)(?: (?P<path>[^\]]*))?\](?P<sig>[$#]))(?P<rest>.*)$")
RE_PS = re.compile(r"^(?P<prompt>PS (?P<path>[A-Za-z]:\\[^>]*)>)(?P<rest>.*)$")
RE_SQL = re.compile(r"^(?P<prompt>(?P<host>MariaDB|mysql) \[[^\]]*\]>)(?P<rest>.*)$")
RE_CMD = re.compile(r"^(?P<prompt>(?P<path>[A-Za-z]:\\[^>]*)>)(?P<rest>\S.*)$")

def parse_prompt(line):
    line = line.strip()
    for kind, rx in (("unix", RE_UNIX_A), ("unix", RE_UNIX_B), ("ps", RE_PS), ("sql", RE_SQL), ("cmd", RE_CMD)):
        m = rx.match(line)
        if m:
            d = m.groupdict()
            d["kind"] = kind
            return d
    return None

def device_for(p):
    if p["kind"] == "ps":
        return "Windows host · PowerShell", "win"
    if p["kind"] == "cmd":
        return "Windows host · CMD", "win"
    if p["kind"] == "sql":
        return "MariaDB-client", "container"
    host = p["host"]
    h = host.lower()
    if h.startswith("server"):
        return f"RHEL VM · {host}", "server"
    if h.startswith("client"):
        return f"RHEL VM · {host}", "client"
    if h == "localhost":
        return "RHEL VM · localhost", "server"
    return f"Container · {host}", "container"

def toestel_klasse(label):
    l = label.lower()
    if l == "?":
        return "onbekend"
    if l.startswith("bestand"):
        return "bestand"
    if "windows" in l:
        return "win"
    if l.startswith("browser"):
        return "browser"
    if l.startswith("container") or "mariadb" in l:
        return "container"
    if "client" in l and "server" not in l:
        return "client"
    return "server"

# commando's die op schermafbeeldingen staan (overgetypt), zie afbeelding-commandos.json
try:
    AFB_CMDS = {k: v for k, v in json.loads((ROOT / "afbeelding-commandos.json").read_text(encoding="utf-8")).items()
                if not k.startswith("_")}
except FileNotFoundError:
    AFB_CMDS = {}
# bevestigde toestellen voor commando's zonder prompt, zie toestel-correcties.json
try:
    CORRECTIES = {k: v for k, v in json.loads((ROOT / "toestel-correcties.json").read_text(encoding="utf-8")).items()
                  if not k.startswith("_")}
except FileNotFoundError:
    CORRECTIES = {}

def split_comment(cmd):
    """Haal een afsluitend '# commentaar' (buiten quotes) van een commando."""
    q = None
    for i, ch in enumerate(cmd):
        if q:
            if ch == q:
                q = None
        elif ch in "'\"":
            q = ch
        elif ch == "#" and i > 0 and cmd[i - 1] in " \t":
            return cmd[:i].rstrip(), cmd[i:]
    return cmd, ""

EDITOR_RX = re.compile(r"^\s*(sudo\s+)?(nano|vi|vim|gedit)\s+\S+|^\s*cat\s+>{1,2}\s*\S+\s*$")
HEREDOC_RX = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
YAML_RX = re.compile(r"^\s*(- )?[\w.-]+:(\s|$)")
CMD_WORD_RX = re.compile(r"^(sudo|podman|docker|ssh|scp|curl|wget|dnf|yum|systemctl|nmcli|cd|ls|cat|mkdir|rm|cp|mv|nano|vi|echo|git|choco|buildah|skopeo|podman-compose|docker-compose|firewall-cmd|ip|ping|nslookup|dig|kubectl|minikube|exit)(\s|$)")
URL_RX = re.compile(r"^https?://\S+$")
FILE_HINT_RX = re.compile(r"(inhoud|bestand|containerfile|dockerfile|compose|\.ya?ml|\.conf|\.html|ziet er .*uit|als volgt)", re.I)

# ---------------------------------------------------------------- docx-lezer

class Chapter:
    def __init__(self, num, path):
        self.num = num
        self.path = path
        self.doc = docx.Document(str(path))
        self.title = None
        self.slug = None
        self.html = []
        self.toc = []             # (niveau, id, tekst)
        self.search = []          # zoekindex-items
        self.unknown = []         # plaatsen met '?'
        self.aangenomen = []      # commando's zonder prompt → standaardtoestel
        self.afb_sleutels = []    # afbeeldingen (geen iconen), voor --ocr
        self.waarschuwingen = []  # dingen in de docx die het nakijken waard zijn
        self.img_count = 0
        self.cmd_count = 0
        self._ids = set()
        self._cur_heading = ""
        self._cur_id = ""
        self._sec_text = []
        self._sec_cmds = []
        self._last_text = ""
        self._last_cmd = ""
        self._counters = {}
        self._kopnr = {}
        self._numbering = self._load_numbering()
        self._style_num = self._load_style_numbering()
        self._style_mono = self._load_style_mono()

    # -- numbering
    def _load_numbering(self):
        res = {}
        try:
            np = self.doc.part.numbering_part.element
        except Exception:
            return res
        abstract = {}
        for a in np.findall(qn("w:abstractNum")):
            aid = a.get(qn("w:abstractNumId"))
            lv = {}
            for l in a.findall(qn("w:lvl")):
                f = l.find(qn("w:numFmt"))
                lv[l.get(qn("w:ilvl"))] = f.get(qn("w:val")) if f is not None else "bullet"
            abstract[aid] = lv
        for n in np.findall(qn("w:num")):
            a = n.find(qn("w:abstractNumId"))
            if a is not None:
                res[n.get(qn("w:numId"))] = abstract.get(a.get(qn("w:val")), {})
        return res

    def _load_style_numbering(self):
        res = {}
        for st in self.doc.styles.element.findall(qn("w:style")):
            sid = st.get(qn("w:styleId"))
            ppr = st.find(qn("w:pPr"))
            if ppr is not None and ppr.find(qn("w:numPr")) is not None:
                nid = ppr.find(qn("w:numPr")).find(qn("w:numId"))
                il = ppr.find(qn("w:numPr")).find(qn("w:ilvl"))
                if nid is not None:
                    res[sid] = (nid.get(qn("w:val")), il.get(qn("w:val")) if il is not None else "0")
        return res

    def _load_style_mono(self):
        res = set()
        for st in self.doc.styles.element.findall(qn("w:style")):
            rpr = st.find(qn("w:rPr"))
            if rpr is not None and rpr.find(qn("w:rFonts")) is not None:
                f = (rpr.find(qn("w:rFonts")).get(qn("w:ascii")) or "").lower()
                if any(m in f for m in MONO_FONTS):
                    res.add(st.get(qn("w:styleId")))
        return res

    def list_info(self, p):
        ppr = p.find(qn("w:pPr"))
        style = ""
        if ppr is not None:
            ps = ppr.find(qn("w:pStyle"))
            style = ps.get(qn("w:val")) if ps is not None else ""
            npr = ppr.find(qn("w:numPr"))
            if npr is not None:
                nid = npr.find(qn("w:numId"))
                il = npr.find(qn("w:ilvl"))
                if nid is not None and nid.get(qn("w:val")) != "0":
                    nid = nid.get(qn("w:val"))
                    ilv = il.get(qn("w:val")) if il is not None else "0"
                    fmt = self._numbering.get(nid, {}).get(ilv, "bullet")
                    return (nid, int(ilv), fmt)
                if nid is not None:
                    return None
        if style in self._style_num:
            nid, ilv = self._style_num[style]
            fmt = self._numbering.get(nid, {}).get(ilv, "bullet")
            return (nid, int(ilv), fmt)
        return None

    # -- ids
    def uid(self, text):
        base = slugify(text)[:60]
        i, cand = 1, base
        while cand in self._ids:
            i += 1
            cand = f"{base}-{i}"
        self._ids.add(cand)
        return cand

    # -- runs -> segmenten
    def runs(self, p):
        """Geeft lijst segmenten: ('t', tekst, fmt) of ('img', info) of ('br',)."""
        segs = []
        fld_url = None
        fld_state = None
        for el in p.iter():
            tag = el.tag
            if tag == qn("w:fldChar"):
                t = el.get(qn("w:fldCharType"))
                if t == "begin":
                    fld_state, fld_url = "instr", None
                elif t == "separate":
                    fld_state = "result"
                elif t == "end":
                    fld_state, fld_url = None, None
            elif tag == qn("w:instrText") and fld_state == "instr":
                m = re.search(r'HYPERLINK\s+"([^"]+)"', el.text or "")
                if m:
                    fld_url = m.group(1)
            elif tag == qn("w:r"):
                if fld_state == "instr":
                    continue
                rpr = el.find(qn("w:rPr"))
                fmt = {"b": is_true(rpr, "w:b"), "i": is_true(rpr, "w:i"), "mono": False, "href": None}
                if rpr is not None:
                    rf = rpr.find(qn("w:rFonts"))
                    if rf is not None:
                        f = (rf.get(qn("w:ascii")) or rf.get(qn("w:hAnsi")) or "").lower()
                        fmt["mono"] = any(m in f for m in MONO_FONTS)
                    rs = rpr.find(qn("w:rStyle"))
                    if rs is not None and rs.get(qn("w:val")) in self._style_mono:
                        fmt["mono"] = True
                # hyperlink-voorouder
                anc = el.getparent()
                while anc is not None and anc.tag != qn("w:p"):
                    if anc.tag == qn("w:hyperlink"):
                        rid = anc.get(qn("r:id"))
                        if rid and rid in self.doc.part.rels:
                            fmt["href"] = self.doc.part.rels[rid].target_ref
                        elif anc.get(qn("w:anchor")):
                            fmt["href"] = None
                        break
                    anc = anc.getparent()
                if fld_state == "result" and fld_url:
                    fmt["href"] = fld_url
                for c in el:
                    if c.tag == qn("w:t"):
                        segs.append(("t", c.text or "", dict(fmt)))
                    elif c.tag == qn("w:tab"):
                        segs.append(("t", "\t", dict(fmt)))
                    elif c.tag in (qn("w:br"), qn("w:cr")):
                        if c.get(qn("w:type")) == "page":
                            continue
                        segs.append(("br",))
                    elif c.tag == qn("w:sym"):
                        segs.append(("t", "•", dict(fmt)))
                    elif c.tag in (qn("w:drawing"), qn("w:pict"), "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"):
                        for info in self.images_in(c):
                            segs.append(("img", info))
        return segs

    def images_in(self, el):
        found = []
        seen = set()
        for blip in el.iter(qn("a:blip")):
            rid = blip.get(qn("r:embed"))
            if rid and rid not in seen:
                seen.add(rid)
                found.append(self._img(rid, blip))
        if not found:
            for im in el.iter("{urn:schemas-microsoft-com:vml}imagedata"):
                rid = im.get(qn("r:id"))
                if rid and rid not in seen:
                    seen.add(rid)
                    found.append(self._img(rid, im))
        return [f for f in found if f]

    def _img(self, rid, node):
        rel = self.doc.part.rels.get(rid)
        if rel is None or rel.is_external:
            return None
        part = rel.target_part
        ext = os.path.splitext(part.partname)[1].lower().replace(".jpeg", ".jpg")
        # afmetingen + alt-tekst uit wp:inline / wp:anchor
        cx, alt = None, ""
        anc = node
        while anc is not None:
            if anc.tag in (qn("wp:inline"), qn("wp:anchor")):
                e = anc.find(qn("wp:extent"))
                if e is not None:
                    cx = int(e.get("cx"))
                dp = anc.find(qn("wp:docPr"))
                if dp is not None:
                    alt = dp.get("descr") or ""
                break
            anc = anc.getparent()
        self.img_count += 1
        name = f"{self.num}-{self.img_count:03d}{ext}"
        dest = OUT / "img" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(part.blob)
        w = round(cx / EMU_PER_PX) if cx else None
        key = f"{self.num}-{self.img_count:03d}"
        if not w or w > 120:
            self.afb_sleutels.append(key)
        return {"src": f"img/{name}", "w": w, "alt": alt, "key": key}

    # -- inline-html
    def inline_html(self, segs, inline_icons=True):
        out = []
        buf = []  # (tekst, fmt)

        def flush():
            # groepeer opeenvolgende runs met dezelfde opmaak
            groups = []
            for t, f in buf:
                key = (f["b"], f["i"], f["mono"], f["href"])
                if groups and groups[-1][0] == key:
                    groups[-1][1].append(t)
                else:
                    groups.append([key, [t]])
            for (b, i, mono, href), ts in groups:
                s = esc("".join(ts))
                if not s:
                    continue
                if mono and s.strip():
                    s = f"<code>{s}</code>"
                if b and s.strip():
                    s = f"<strong>{s}</strong>"
                if i and s.strip():
                    s = f"<em>{s}</em>"
                if href:
                    s = f'<a href="{esc(href)}" target="_blank" rel="noopener">{s}</a>'
                out.append(s)
            buf.clear()

        for s in segs:
            if s[0] == "t":
                buf.append((s[1], s[2]))
            elif s[0] == "br":
                flush()
                out.append("<br>")
            elif s[0] == "img" and inline_icons:
                flush()
                info = s[1]
                out.append(f'<img class="icoon" src="{info["src"]}" alt="{esc(info["alt"] or "icoon")}" loading="lazy">')
        flush()
        return "".join(out).replace("\t", " ")

    # -- hoofdroutine
    def convert(self):
        body = self.doc.element.body
        blocks = list(self.iter_blocks(body))
        # titel: eerste Kop1, anders bestandsnaam
        fname_title = re.sub(r"^\d+\s+", "", self.path.stem)
        fname_title = re.sub(r"\s*\(\d+\)$", "", fname_title)
        self.title = fname_title
        for kind, el in blocks:
            if kind == "p" and self.style(el) == "Kop1":
                self.title = self.text_of(el).strip()
                break
        self.slug = f"{self.num:02d}-{slugify(self.title)}"
        self._cur_heading = self.title
        self._cur_id = ""
        self.render_blocks(blocks, top=True)
        self.flush_search()

    def iter_blocks(self, parent):
        for el in parent:
            if el.tag == qn("w:p"):
                yield ("p", el)
            elif el.tag == qn("w:tbl"):
                yield ("tbl", el)
            elif el.tag == qn("w:sdt"):
                c = el.find(qn("w:sdtContent"))
                if c is not None:
                    yield from self.iter_blocks(c)

    def style(self, p):
        ppr = p.find(qn("w:pPr"))
        if ppr is not None and ppr.find(qn("w:pStyle")) is not None:
            return ppr.find(qn("w:pStyle")).get(qn("w:val"))
        return ""

    def text_of(self, p):
        return "".join(t.text or "" for t in p.iter(qn("w:t")))

    def code_lines(self, p, segs):
        """Is deze alinea code? Zo ja: lijst regels."""
        texts = [s for s in segs if s[0] == "t" and s[1].strip()]
        if not texts:
            return None
        style_mono = self.style(p) in self._style_mono
        if not (style_mono or all(s[2]["mono"] for s in texts)):
            # Windows-commando in gewone tekst: C:\Users\x>commando
            plain = "".join(s[1] for s in segs if s[0] == "t")
            if RE_CMD.match(plain.strip()):
                return [plain.strip()]
            return None
        lines, cur = [], []
        for s in segs:
            if s[0] == "t":
                cur.append(s[1])
            elif s[0] == "br":
                lines.append("".join(cur)); cur = []
        lines.append("".join(cur))
        return [l.replace("\t", "    ").rstrip() for l in lines]

    def render_blocks(self, blocks, top=False):
        out = self.html if top else []
        code_buf = []          # regels
        code_imgs = []         # afbeeldingen in code-alinea's
        list_stack = []        # [(tag, nid)]
        first_heading_done = False

        counters = self._counters

        def close_lists():
            while list_stack:
                tag, _ = list_stack.pop()
                out.append(f"</li></{tag}>")

        def flush_code():
            nonlocal code_buf, code_imgs
            if code_buf:
                close_lists()
                out.append(self.render_code(code_buf))
                code_buf = []
            for info in code_imgs:
                out.append(self.figure(info))
            code_imgs = []

        for kind, el in blocks:
            if kind == "tbl":
                flush_code(); close_lists()
                out.append(self.render_table(el))
                continue
            p = el
            st = self.style(p)
            segs = self.runs(p)
            lines = self.code_lines(p, segs)
            if lines is not None:
                code_buf.extend(lines)
                code_imgs.extend(s[1] for s in segs if s[0] == "img")
                continue
            flush_code()
            text = "".join(s[1] for s in segs if s[0] == "t").strip()
            imgs = [s[1] for s in segs if s[0] == "img"]

            # koppen
            m = re.match(r"Kop(\d)(Romeins)?$", st)
            if m and text and not (m.group(2) and self.list_info(p)) and not (m.group(2) and first_heading_done):
                close_lists()
                lvl = int(m.group(1))
                first_heading_done = True
                if lvl == 1:
                    if text == self.title:
                        continue
                    lvl = 2
                lvl = min(lvl, 5)
                vorig = max([l for l in range(2, 6) if self._kopnr.get(l)] or [1])
                if lvl > vorig + 1:
                    self.waarschuwingen.append(f"kop '{text[:60]}' springt van niveau {vorig} naar {lvl} (stijl {st})")
                # nummering zoals in Word: 2.1, 2.6.1 …
                self._kopnr[lvl] = self._kopnr.get(lvl, 0) + 1
                for deeper in range(lvl + 1, 6):
                    self._kopnr[deeper] = 0
                nr = ".".join([str(self.num)] + [str(self._kopnr.get(l, 0)) for l in range(2, lvl + 1)])
                hid = self.uid(text)
                if lvl <= 3:
                    self.flush_search()
                    self._cur_heading, self._cur_id = f"{nr} {text}", hid
                    self.toc.append((lvl, hid, f"{nr} {text}"))
                out.append(f'<h{lvl} id="{hid}"><a class="anker" href="#{hid}" aria-label="Link naar deze sectie">#</a>'
                           f'<span class="kopnr">{nr}</span> {esc(text)}</h{lvl}>')
                for info in imgs:
                    out.append(self.figure(info))
                continue

            if text:
                self._sec_text.append(text)
                self._last_text = text

            # grote afbeeldingen als figuur, kleine (iconen) inline
            big = [i for i in imgs if not (text and i["w"] and i["w"] <= 60)]
            small_ok = bool(text)
            body_html = self.inline_html([s for s in segs if s[0] != "img" or (small_ok and s[1] not in big)])

            li = self.list_info(p)
            if li and (text or imgs):
                nid, ilvl, fmt = li
                tag = "ul" if fmt in ("bullet", "none") else "ol"
                # Word-nummering: diepere niveaus herbeginnen, dit niveau telt door
                for key in [k for k in counters if k[0] == nid and k[1] > ilvl]:
                    del counters[key]
                counters[(nid, ilvl)] = counters.get((nid, ilvl), 0) + 1
                while list_stack and list_stack[-1][1] > ilvl:
                    t, _ = list_stack.pop()
                    out.append(f"</li></{t}>")
                if list_stack and list_stack[-1][1] == ilvl:
                    out.append("</li><li>")
                else:
                    typ = {"lowerLetter": ' type="a"', "upperLetter": ' type="A"',
                           "lowerRoman": ' type="i"', "upperRoman": ' type="I"'}.get(fmt, "")
                    start = counters[(nid, ilvl)]
                    st_attr = f' start="{start}"' if tag == "ol" and start > 1 else ""
                    indent = f' style="margin-left:{1.4 * ilvl:.1f}em"' if not list_stack and ilvl else ""
                    out.append(f"<{tag}{typ}{st_attr}{indent}><li>")
                    list_stack.append((tag, ilvl))
                for info in big:
                    out.append(self.figure(info))
                if body_html.strip():
                    out.append(f"<p>{body_html}</p>")
                continue
            close_lists()
            for info in big:
                out.append(self.figure(info))
            if body_html.strip():
                out.append(f"<p>{body_html}</p>")
        flush_code()
        close_lists()
        return "".join(out)

    def figure(self, info):
        w = f' style="--w:{info["w"]}px"' if info["w"] else ""
        extra = ""
        cmds = AFB_CMDS.get(info.get("key"), [])
        if cmds:
            blokken = []
            for cmd, label in cmds:
                dclass = toestel_klasse(label)
                if dclass == "onbekend":
                    self.unknown.append({"sectie": self._cur_heading, "id": self._cur_id,
                                         "tekst": f"(afbeelding {info['key']}) {cmd}", "context": ""})
                blokken.append(self.cmd_block("", cmd, [], label, dclass, False))
            n = len(cmds)
            extra = (f'<details class="afb-cmds"><summary>Commando{"" if n == 1 else "&#39;s"} uit deze afbeelding ({n})</summary>'
                     + "".join(blokken) + "</details>")
        return (f'<figure class="fig"{w}><a href="{info["src"]}" class="zoom" target="_blank">'
                f'<img src="{info["src"]}" alt="{esc(info["alt"] or "Schermafbeelding")}" loading="lazy"></a>{extra}</figure>')

    def render_table(self, tbl):
        rows = []
        for tr in tbl.findall(qn("w:tr")):
            cells = []
            for tc in tr.findall(qn("w:tc")):
                inner = self.render_blocks(list(self.iter_blocks(tc)))
                cells.append(f"<td>{inner}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return '<div class="tabel"><table>' + "".join(rows) + "</table></div>"

    # -- codeblokken
    def section_prefix(self):
        for num, rx, prefix in SECTIE_LABELS:
            if num == self.num and rx.search(self._cur_heading):
                return prefix
        return ""

    def render_code(self, lines):
        while lines and not lines[0].strip():
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        if not lines:
            return ""
        # gemeenschappelijke inspringing weghalen
        ind = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        lines = [l[ind:] for l in lines]
        out = []
        i = 0
        while i < len(lines):
            p = parse_prompt(lines[i])
            if p and p["rest"].strip():
                rest = p["rest"]
                spill = []
                if "…" in rest:  # uitvoer die in hetzelfde Word-regeltje staat
                    rest, extra = rest.split("…", 1)
                    spill = ["…" + extra] if extra.strip() else ["…"]
                cmd = rest.strip()
                j = i + 1
                while cmd.endswith("\\") and j < len(lines):
                    cmd += "\n" + lines[j]; j += 1
                hd = HEREDOC_RX.search(cmd)
                if hd:
                    term = hd.group(1)
                    while j < len(lines):
                        cmd += "\n" + lines[j]; j += 1
                        if lines[j - 1].strip() == term:
                            break
                outp = list(spill)
                while j < len(lines):
                    q = parse_prompt(lines[j])
                    if q and q["rest"].strip():
                        break
                    outp.append(lines[j]); j += 1
                while outp and not outp[-1].strip():
                    outp.pop()
                label, dclass = device_for(p)
                label = self.section_prefix() + label
                is_file = bool(EDITOR_RX.match(cmd))
                out.append(self.cmd_block(p["prompt"], cmd, outp, label, dclass, is_file))
                self._last_cmd = cmd
                i = j
            else:
                j = i
                buf = []
                while j < len(lines):
                    q = parse_prompt(lines[j])
                    if q and q["rest"].strip():
                        break
                    buf.append(lines[j]); j += 1
                out.append(self.plain_block(buf))
                i = j
        return "".join(out)

    def cmd_block(self, prompt, cmd, outp, label, dclass, out_is_file):
        self.cmd_count += 1
        copy_lines = []
        disp_lines = []
        for k, ln in enumerate(cmd.split("\n")):
            c, comment = split_comment(ln)
            copy_lines.append(c)
            pr = f'<span class="pr">{esc(prompt)} </span>' if k == 0 and prompt else ""
            cm = f' <span class="cm">{esc(comment)}</span>' if comment else ""
            disp_lines.append(f'{pr}<span class="cmd">{esc(c)}</span>{cm}')
        copy = "\n".join(copy_lines).strip()
        self._sec_cmds.append(copy)
        if re.search(r"[0-9a-f]{40,}", copy):
            self.waarschuwingen.append(f"{self._cur_heading}: uitvoer lijkt aan het commando vast te plakken in Word: `{copy[:90]}`")
        # Label alleen waar het iets toevoegt: Windows host, of als de prompt niet zichtbaar is
        # en het niet de gewone RHEL VM is (container, client, '?'). Anders zegt de prompt het al.
        toon = dclass in ("win", "browser") or (not prompt and dclass in ("container", "client", "onbekend", "bestand"))
        kort = label.replace("RHEL VM · ", "")
        kop = (f'<div class="blok-kop"><span class="toestel t-{dclass}">{esc(label)}</span>' if toon
               else '<div class="blok-kop">')
        h = [f'<div class="blok{"" if toon else " zonder-label"}" data-toestel="{esc(kort)}" data-soort="{dclass}">',
             kop + f'<button class="kopieer" type="button" data-copy="{esc(copy)}">Kopieer</button></div>',
             f'<pre class="invoer"><code>{"<br>".join(disp_lines)}</code></pre>']
        if outp:
            if out_is_file:
                h.append(f'<div class="bestand"><span class="sub">Inhoud van het bestand</span>'
                         f'<pre><code>{esc(chr(10).join(outp))}</code></pre></div>')
            else:
                n = sum(1 for l in outp if l.strip())
                h.append(f'<details class="uitvoer"><summary><span class="sub">Toon uitvoer</span>'
                         f'<span class="aantal">{n} regel{"" if n == 1 else "s"}</span></summary>'
                         f'<pre><code>{esc(chr(10).join(outp))}</code></pre></details>')
        h.append("</div>")
        return "".join(h)

    def plain_block(self, buf):
        text = "\n".join(buf).strip("\n")
        if not text.strip():
            return ""
        rows = [l for l in text.split("\n") if l.strip()]
        first = rows[0].strip()
        for begin, label in CORRECTIES.items():
            if first.startswith(begin):
                return self.cmd_block("", text.strip(), [], label, toestel_klasse(label), False)
        yaml_rows = sum(1 for l in rows if YAML_RX.match(l))
        is_yaml = yaml_rows >= max(1, len(rows) // 2) and not first.startswith("{")
        if is_yaml or FILE_HINT_RX.search(self._last_text or ""):
            kind = "bestand"
        elif CMD_WORD_RX.match(first) or URL_RX.match(first):
            # commando zonder prompt: standaard op de server-VM (afspraak met Andrii), maar wel melden
            label = ("Browser · serverXX" if URL_RX.match(first) else STANDAARD_TOESTEL)
            self.aangenomen.append({"sectie": self._cur_heading, "id": self._cur_id, "tekst": first[:150], "label": label})
            return self.cmd_block("", text.strip(), [], label, toestel_klasse(label), False)
        else:
            kind = "uitvoer"
        self._sec_cmds.append(text)
        if kind == "uitvoer":
            n = sum(1 for l in text.split("\n") if l.strip())
            return (f'<div class="blok blok-los"><details class="uitvoer"><summary><span class="sub">Toon uitvoer</span>'
                    f'<span class="aantal">{n} regel{"" if n == 1 else "s"}</span></summary>'
                    f'<pre><code>{esc(text)}</code></pre></details></div>')
        if kind == "bestand":
            return (f'<div class="blok blok-bestand" data-toestel="bestand" data-soort="bestand">'
                    f'<div class="blok-kop"><span class="toestel t-bestand">Bestandsinhoud</span>'
                    f'<button class="kopieer" type="button" data-copy="{esc(text)}">Kopieer</button></div>'
                    f'<pre class="invoer"><code>{esc(text)}</code></pre></div>')
        self.cmd_count += 1
        self.unknown.append({"sectie": self._cur_heading, "id": self._cur_id,
                             "tekst": text if len(text) < 160 else text[:157] + "…",
                             "context": self._last_text[-160:]})
        copy = "\n".join(split_comment(l)[0] for l in text.split("\n")).strip()
        return (f'<div class="blok blok-onbekend" data-toestel="?" data-soort="onbekend">'
                f'<div class="blok-kop"><span class="toestel t-onbekend">?</span>'
                f'<button class="kopieer" type="button" data-copy="{esc(copy)}">Kopieer</button></div>'
                f'<pre class="invoer"><code>{esc(text)}</code></pre></div>')

    def flush_search(self):
        if self._sec_text or self._sec_cmds:
            self.search.append({
                "h": self._cur_heading, "id": self._cur_id,
                "x": " ".join(self._sec_text)[:4000],
                "k": "\n".join(self._sec_cmds)[:4000],
            })
        self._sec_text, self._sec_cmds = [], []


# ---------------------------------------------------------------- pagina's

WEERGAVE_BALK = (
    '<div class="weergave" role="toolbar" aria-label="Weergave">'
    '<button type="button" class="wg-knop" id="alleen-cmd" aria-pressed="false">Alleen commando\'s</button>'
    '<div class="wg-groep" role="group" aria-label="Toestel">'
    '<span class="wg-lbl">Toestel</span>'
    '<button type="button" class="wg-chip actief" data-filter="alle">Alle</button>'
    '<button type="button" class="wg-chip" data-filter="server">serverXX</button>'
    '<button type="button" class="wg-chip" data-filter="client">clientXX</button>'
    '<button type="button" class="wg-chip" data-filter="container">Container</button>'
    '<button type="button" class="wg-chip" data-filter="win">Windows</button>'
    '</div>'
    '<label class="wg-init"><span class="wg-lbl">Mijn initialen</span>'
    '<input id="initialen" type="text" maxlength="6" placeholder="XX" autocomplete="off" spellcheck="false"'
    ' title="Vervangt XX in de gekopieerde commando\'s (serverXX → serverAB). De tekst zelf blijft XX."></label>'
    '<button type="button" class="wg-knop" id="afdrukken">Afdrukken / PDF</button>'
    '</div>'
)

KLAP = '<button class="klap" type="button" aria-expanded="{open}" aria-label="Uitklappen"></button>'

def toc_boom(ch, prefix=""):
    """Kopjes van een hoofdstuk als in-/uitklapbare boom (h2 > h3), zoals het navigatievenster van Word."""
    groepen = []
    for lvl, hid, t in ch.toc:
        if lvl == 2 or not groepen:
            groepen.append([(hid, t), []])
        else:
            groepen[-1][1].append((hid, t))
    def split(t):
        nr, _, rest = t.partition(" ")
        return f'<span class="knr">{esc(nr)}</span><span class="tt">{esc(rest)}</span>'
    out = []
    for (hid, t), subs in groepen:
        link = f'<a href="{prefix}#{hid}">{split(t)}</a>'
        if subs:
            sub = "".join(f'<li><div class="rij"><span class="klap-leeg"></span><a href="{prefix}#{h}">{split(s)}</a></div></li>' for h, s in subs)
            out.append(f'<li class="tak"><div class="rij">{KLAP.format(open="false")}{link}</div><ul class="subboom">{sub}</ul></li>')
        else:
            out.append(f'<li><div class="rij"><span class="klap-leeg"></span>{link}</div></li>')
    return '<ul class="boom">' + "".join(out) + "</ul>"

HEEFT_SPIEKBRIEF = False

def nav_html(chapters, active):
    items = []
    if HEEFT_SPIEKBRIEF:
        cur = ' aria-current="page"' if active == "spiekbrief" else ""
        items.append(f'<li class="hfd sb-link"><div class="rij"><span class="klap-leeg"></span><a href="spiekbrief.html"{cur}>'
                     f'<span class="nr">★</span><span class="tt">Spiekbrief (examen)</span></a></div></li>')
    for c in chapters:
        is_cur = c is active
        cur = ' aria-current="page"' if is_cur else ""
        link = f'<a href="{c.slug}.html"{cur}><span class="nr">{c.num}</span><span class="tt">{esc(c.title)}</span></a>'
        boom = toc_boom(c, "" if is_cur else f"{c.slug}.html") if c.toc else ""
        open_ = "true" if is_cur else "false"
        cls = "hfd tak open" if (is_cur and boom) else ("hfd tak" if boom else "hfd")
        knop = KLAP.format(open=open_) if boom else '<span class="klap-leeg"></span>'
        items.append(f'<li class="{cls}"><div class="rij">{knop}{link}</div>{boom}</li>')
    return '<ol class="hoofdstukken">' + "".join(items) + "</ol>"

def toc_html(ch):
    if not ch.toc:
        return ""
    return (f'<nav class="toc" aria-label="Op deze pagina"><p class="toc-titel">Op deze pagina</p>'
            f'{toc_boom(ch)}</nav>')

def page(tpl, *, title, body, nav, toc, stijl, preview, prevnext=""):
    return (tpl.replace("{{TITEL}}", esc(title))
               .replace("{{SITE}}", esc(SITE_TITLE))
               .replace("{{SUB}}", esc(SITE_SUB))
               .replace("{{NAV}}", nav)
               .replace("{{TOC}}", toc)
               .replace("{{INHOUD}}", body)
               .replace("{{VORIGE_VOLGENDE}}", prevnext)
               .replace("{{STIJL}}", stijl)
               .replace("{{PREVIEW}}", "1" if preview else "0")
               # versie achter de bestanden, zodat browsers na een nieuwe build niet de oude versie tonen
               .replace('assets/site.css"', f'assets/site.css?v={BUILD_ID}"')
               .replace('assets/site.js"', f'assets/site.js?v={BUILD_ID}"')
               .replace('assets/zoekindex.js"', f'assets/zoekindex.js?v={BUILD_ID}"')
               .replace('assets/extra.js"', f'assets/extra.js?v={BUILD_ID}"'))

BUILD_ID = __import__("time").strftime("%Y%m%d%H%M%S")

def spiekbrief_html(chapters):
    """Spiekbrief uit spiekbrief/deel_*.json (per hoofdstuk: kern, secties met items, examenvragen)."""
    delen = []
    for f in sorted((ROOT / "spiekbrief").glob("deel_*.json")):
        try:
            delen += json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as e:
            print(f"  ! spiekbrief: {f.name} overgeslagen ({e})")
    if not delen:
        return None
    delen.sort(key=lambda d: d.get("hoofdstuk", 99))
    slug = {c.num: c.slug for c in chapters}
    LBL = {"serverxx": ("RHEL VM · serverXX", "server"), "clientxx": ("RHEL VM · clientXX", "client"),
           "container": ("Container", "container"), "windows host": ("Windows host", "win"),
           "bestand": ("Bestandsinhoud", "bestand")}
    def ster(it):
        return '<span class="ster" title="Belangrijk voor het examen">★</span>' if it.get("belangrijk") else ""
    def item_html(it):
        t = it.get("type")
        if t == "cmd":
            lab, kl = LBL.get(str(it.get("toestel", "")).strip().lower(), (it.get("toestel") or STANDAARD_TOESTEL, "server"))
            return (f'<li class="sb-cmd{" sb-b" if it.get("belangrijk") else ""}">'
                    f'<div class="blok zonder-label sb-blok" data-toestel="{esc(lab.replace("RHEL VM · ", ""))}" data-soort="{kl}">'
                    f'<div class="blok-kop"><button class="kopieer" type="button" data-copy="{esc(it.get("cmd", ""))}">Kopieer</button></div>'
                    f'<pre class="invoer"><code><span class="cmd">{esc(it.get("cmd", ""))}</span></code></pre></div>'
                    f'<p class="sb-uitleg">{ster(it)}{esc(it.get("uitleg", ""))}'
                    + (f' <span class="sb-toestel t-{kl}">{esc(lab)}</span>' if kl not in ("server",) else "") + '</p></li>')
        if t == "optie":
            return f'<li class="sb-optie">{ster(it)}<code>{esc(it.get("naam", ""))}</code> — {esc(it.get("uitleg", ""))}</li>'
        if t == "fout":
            return (f'<li class="sb-fout">{ster(it)}<span class="sb-probleem">✗ {esc(it.get("probleem", ""))}</span>'
                    f'<span class="sb-oplossing">→ {esc(it.get("oplossing", ""))}</span></li>')
        if t == "vergelijk":
            rijen = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in it.get("rijen", []))
            return (f'<li class="sb-vgl"><table><tr><th>{esc(it.get("links", ""))}</th><th>{esc(it.get("rechts", ""))}</th></tr>'
                    f'{rijen}</table></li>')
        return f'<li class="sb-feit">{ster(it)}{esc(it.get("tekst", ""))}</li>'
    toc, delen_html = [], []
    for d in delen:
        n = d.get("hoofdstuk")
        hid = f"sb-h{n}"
        toc.append((2, hid, f"{n} {d.get('titel', '')}"))
        s = [f'<section class="sb-hfd" id="{hid}"><h2><span class="kopnr">{n}</span> {esc(d.get("titel", ""))}'
             + (f' <a class="sb-naar" href="{slug[n]}.html">naar hoofdstuk →</a>' if n in slug else "") + '</h2>']
        if d.get("kern"):
            s.append('<div class="sb-kern"><p class="sb-lbl">In het kort</p><ul>'
                     + "".join(f"<li>{esc(k)}</li>" for k in d["kern"]) + "</ul></div>")
        s.append('<div class="sb-raster">')
        for k, sec in enumerate(d.get("secties", [])):
            sid = f"{hid}-{k + 1}"
            toc.append((3, sid, f"{n}.{k + 1} {sec.get('titel', '')}"))
            s.append(f'<div class="sb-sectie"><h3 id="{sid}">{esc(sec.get("titel", ""))}</h3><ul class="sb-items">'
                     + "".join(item_html(i) for i in sec.get("items", [])) + "</ul></div>")
        s.append("</div>")
        if d.get("vragen"):
            vid = f"{hid}-vragen"
            toc.append((3, vid, f"{n} Examenvragen"))
            s.append(f'<div class="sb-vragen"><h3 id="{vid}">Test jezelf — hoofdstuk {n}</h3><ol>'
                     + "".join(f'<li><details><summary>{esc(v.get("vraag", ""))}</summary><p>{esc(v.get("antwoord", ""))}</p></details></li>'
                               for v in d["vragen"]) + "</ol></div>")
        s.append("</section>")
        delen_html.append("".join(s))
    intro = ('<header class="hfd-kop"><p class="hfd-nr">Permanente evaluatie · hoofdstukken '
             + esc(f"{delen[0].get('hoofdstuk')}–{delen[-1].get('hoofdstuk')}") + '</p><h1 id="top">Spiekbrief</h1>'
             '<p class="intro">Alles wat je moet kennen, per hoofdstuk: de kern, de commando\'s (met Kopieer), '
             'opties, paden en poorten, typische fouten en hun oplossing, en vragen om jezelf te testen. '
             '<span class="ster">★</span> = komt waarschijnlijk op het examen.</p>'
             '<div class="weergave"><button type="button" class="wg-knop" id="sb-alleen-ster" aria-pressed="false">Alleen ★</button>'
             '<button type="button" class="wg-knop" id="sb-antwoorden">Alle antwoorden tonen</button>'
             '<button type="button" class="wg-knop" id="afdrukken">Afdrukken / PDF</button></div></header>')
    return intro + "".join(delen_html), toc


def ocr_voorstellen(chapters, overnemen=False):
    """Leest schermafbeeldingen zonder overgetypte commando's met de ingebouwde OCR van Windows
    en zoekt regels met een prompt (student@serverXX:~$ …). Resultaat: afbeelding-commandos.voorstel.json."""
    import subprocess, tempfile
    zonder = [k for ch in chapters for k in ch.afb_sleutels if k not in AFB_CMDS]
    if not zonder:
        print("  OCR: alle afbeeldingen hebben al commando's (of geen terminal).")
        return
    if os.name != "nt":
        print("  OCR: werkt alleen op Windows (Windows.Media.Ocr). Overgeslagen.")
        return
    tmp = Path(tempfile.mkdtemp())
    for k in zonder:
        for ext in (".png", ".jpg"):
            src = OUT / "img" / f"{k}{ext}"
            if src.exists():
                shutil.copy(src, tmp / src.name)
    uit = tmp / "ocr.json"
    print(f"  OCR: {len(zonder)} afbeeldingen lezen…")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "ocr.ps1"),
                    "-Dir", str(tmp), "-Out", str(uit)], capture_output=True, text=True)
    if not uit.exists():
        print("  OCR mislukt (geen uitvoer).")
        return
    data = json.loads(uit.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = [data]
    voorstel = {}
    for item in data:
        regels = item.get("lines") or []
        if isinstance(regels, str):
            regels = [regels]
        cmds = []
        schoon = lambda s: re.sub(r"(\w)\. (\w)", r"\1.\2", s.replace("—", "-").replace("–", "-").replace("•", "")).strip()
        alleen_prompt = re.compile(r"^(?:\[)?(?P<user>[\w.-]+)@(?P<host>[\w.-]+)[^\s]*?(?:\s*[:~\]—-]*\s*\S*)?\s*[$#~—]?\s*$")
        vorige_host = None
        for r in regels:
            r0 = r.replace("�", "~").replace(" : ", ":").replace(":N$", ":~$").replace(":N/", ":~/").strip()
            p = parse_prompt(schoon(r0))
            if p and p["rest"].strip():
                label, _ = device_for(p)
                cmds.append([split_comment(schoon(p["rest"]))[0], label])
                vorige_host = None
                continue
            m = alleen_prompt.match(r0)
            if m and len(r0) < 60:
                vorige_host = m.group("host")        # Windows-OCR zet prompt en commando op twee regels
                continue
            if vorige_host and CMD_WORD_RX.match(schoon(r0)):
                label, _ = device_for({"kind": "unix", "host": vorige_host})
                cmds.append([split_comment(schoon(r0))[0], label])
            vorige_host = None
        if cmds:
            voorstel[item["file"].rsplit(".", 1)[0]] = cmds
    pad = ROOT / "afbeelding-commandos.voorstel.json"
    pad.write_text(json.dumps(voorstel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  OCR: {sum(len(v) for v in voorstel.values())} commando's op {len(voorstel)} afbeeldingen → {pad.name}")
    print("       Controleer ze (OCR maakt soms fouten: 0/O, l/1, - / —) en kopieer ze naar afbeelding-commandos.json,")
    print("       of draai `python build.py --ocr --ocr-overnemen` om ze meteen over te nemen.")
    if overnemen and voorstel:
        hoofd = json.loads((ROOT / "afbeelding-commandos.json").read_text(encoding="utf-8"))
        hoofd.update({k: v for k, v in voorstel.items() if k not in hoofd})
        (ROOT / "afbeelding-commandos.json").write_text(json.dumps(hoofd, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  OCR: overgenomen → opnieuw bouwen…")
        subprocess.run([sys.executable, str(ROOT / "build.py")] + [x for x in sys.argv[1:] if not x.startswith("--ocr")])
        sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="toon stijlkiezer")
    ap.add_argument("--stijl", default="blauwdruk", choices=["werkboek", "blauwdruk", "signaal"])
    ap.add_argument("--geen-zip", action="store_true")
    ap.add_argument("--ocr", action="store_true",
                    help="lees commando's van schermafbeeldingen (Windows-OCR) → afbeelding-commandos.voorstel.json")
    ap.add_argument("--ocr-overnemen", action="store_true",
                    help="met --ocr: voorstellen meteen toevoegen aan afbeelding-commandos.json en opnieuw bouwen")
    a = ap.parse_args()

    # inhoud leegmaken (niet de map zelf: een lokale webserver kan die open hebben)
    OUT.mkdir(exist_ok=True)
    for f in OUT.iterdir():
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    (OUT / "img").mkdir(parents=True)
    shutil.copytree(TEMPLATE / "assets", OUT / "assets")

    files, nummers = [], {}
    for f in sorted(DOCS.glob("*.docx")):
        if f.name.startswith("~$"):
            print(f"  ! overgeslagen: {f.name} (tijdelijk Word-bestand; sluit Word)")
            continue
        m = re.match(r"^(\d+)\s", f.name)
        if not m:
            print(f"  ! overgeslagen: {f.name} — naam moet beginnen met een nummer en een spatie, bv. '9 Titel.docx'")
            continue
        n = int(m.group(1))
        if n in nummers:
            sys.exit(f"FOUT: twee hoofdstukken met nummer {n}: '{nummers[n]}' en '{f.name}'. Hernoem er één.")
        nummers[n] = f.name
        files.append((n, f))
    files.sort()
    if not files:
        sys.exit(f"FOUT: geen hoofdstukken gevonden in {DOCS}")
    chapters = []
    for num, f in files:
        try:
            ch = Chapter(num, f)
            ch.convert()
        except Exception as e:
            sys.exit(f"FOUT bij het lezen van '{f.name}': {e}\n"
                     f"→ Open het in Word, kies 'Opslaan als' .docx (niet .doc/.odt) en probeer opnieuw.")
        chapters.append(ch)
        print(f"  {num}: {ch.title}  ({ch.img_count} afb., {ch.cmd_count} commando's"
              + (f", {len(ch.aangenomen)} zonder prompt" if ch.aangenomen else "")
              + (f", {len(ch.waarschuwingen)} waarschuwing(en)" if ch.waarschuwingen else "") + ")")

    tpl = (TEMPLATE / "page.html").read_text(encoding="utf-8")
    global HEEFT_SPIEKBRIEF
    sb = spiekbrief_html(chapters)
    HEEFT_SPIEKBRIEF = bool(sb)
    if sb:
        sb_body, sb_toc = sb
        sb_ch = type("SB", (), {"toc": sb_toc})()
        (OUT / "spiekbrief.html").write_text(
            page(tpl, title="Spiekbrief", body=sb_body, nav=nav_html(chapters, "spiekbrief"), toc=toc_html(sb_ch),
                 stijl=a.stijl, preview=a.preview).replace('<body>', '<body class="spiekbrief">', 1), encoding="utf-8")
        print(f"  spiekbrief: {len(sb_toc)} kopjes")

    # zoekindex als JS (werkt ook via file://)
    idx = []
    for ch in chapters:
        for s in ch.search:
            idx.append({"c": ch.num, "ct": ch.title, "u": f"{ch.slug}.html" + (f"#{s['id']}" if s["id"] else ""),
                        "h": s["h"], "x": s["x"], "k": s["k"]})
    (OUT / "assets" / "zoekindex.js").write_text("window.ZOEKINDEX=" + json.dumps(idx, ensure_ascii=False) + ";", encoding="utf-8")

    for k, ch in enumerate(chapters):
        prev = chapters[k - 1] if k > 0 else None
        nxt = chapters[k + 1] if k + 1 < len(chapters) else None
        pn = '<nav class="vv" aria-label="Hoofdstukken">'
        pn += (f'<a class="vorige" href="{prev.slug}.html"><span>Vorige</span>{prev.num} · {esc(prev.title)}</a>' if prev else "<span></span>")
        pn += (f'<a class="volgende" href="{nxt.slug}.html"><span>Volgende</span>{nxt.num} · {esc(nxt.title)}</a>' if nxt else "<span></span>")
        pn += "</nav>"
        body = (f'<header class="hfd-kop"><p class="hfd-nr">Hoofdstuk {ch.num}</p><h1 id="top">{esc(ch.title)}</h1></header>'
                + WEERGAVE_BALK
                + "".join(ch.html))
        (OUT / f"{ch.slug}.html").write_text(
            page(tpl, title=f"{ch.num} · {ch.title}", body=body, nav=nav_html(chapters, ch), toc=toc_html(ch),
                 stijl=a.stijl, preview=a.preview, prevnext=pn), encoding="utf-8")

    # startpagina
    cards = "".join(
        f'<li><a href="{c.slug}.html"><span class="nr">{c.num}</span><span class="tt">{esc(c.title)}</span>'
        f'<span class="meta">{len(c.toc)} secties · {c.cmd_count} commando\'s</span></a></li>' for c in chapters)
    home = (f'<header class="hfd-kop start"><p class="hfd-nr">{esc(SITE_SUB)}</p><h1 id="top">{esc(SITE_TITLE)}</h1>'
            f'<p class="intro">Alle hoofdstukken van de cursus, met commando\'s die je met één klik kopieert. '
            f'Elk commando toont op welk toestel je het uitvoert.</p></header>'
            + (f'<a class="sb-kaart" href="spiekbrief.html"><span class="ster">★</span> <b>Spiekbrief</b> — alles voor de permanente evaluatie op één pagina</a>' if HEEFT_SPIEKBRIEF else "")
            + f'<ol class="kaarten">{cards}</ol>'
            f'<section class="legende" aria-label="Legende"><h2 id="legende">Waar voer je een commando uit?</h2><ul>'
            f'<li><span class="toestel t-server">RHEL VM · serverXX</span> op de server-VM</li>'
            f'<li><span class="toestel t-client">RHEL VM · clientXX</span> op de client-VM</li>'
            f'<li><span class="toestel t-container">Container · …</span> in een container (na <code>podman run -it</code> / <code>exec</code>)</li>'
            f'<li><span class="toestel t-win">Windows host · …</span> op je eigen Windows-pc</li>'
            f'<li><span class="toestel t-bestand">Bestandsinhoud</span> tekst die in een bestand komt</li>'
            f'<li><span class="toestel t-onbekend">?</span> niet duidelijk uit de cursus</li></ul></section>')
    (OUT / "index.html").write_text(
        page(tpl, title=SITE_TITLE, body=home, nav=nav_html(chapters, None), toc="", stijl=a.stijl, preview=a.preview),
        encoding="utf-8")

    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    # rapport: wat nakijken?
    rap = [f"# Bouwrapport — {__import__('time').strftime('%d/%m/%Y %H:%M')}", ""]
    rap.append("## Commando's zonder prompt → standaardtoestel (controleer of dat klopt)")
    rap.append(f"Standaard: `{STANDAARD_TOESTEL}`. Anders? Zet het in `toestel-correcties.json`.\n")
    for ch in chapters:
        for u in ch.aangenomen:
            rap.append(f"- H{ch.num} › {u['sectie']} — `{u['tekst']}` → {u['label']}  ({ch.slug}.html#{u['id']})")
    rap += ["", "## Toestel onbekend ('?')", ""]
    for ch in chapters:
        for u in ch.unknown:
            rap.append(f"- H{ch.num} › {u['sectie']} — `{u['tekst'].splitlines()[0]}`  ({ch.slug}.html#{u['id']})")
    rap += ["", "## Waarschuwingen uit de Word-bestanden", ""]
    for ch in chapters:
        for w in ch.waarschuwingen:
            rap.append(f"- H{ch.num}: {w}")
    zonder = [k for ch in chapters for k in ch.afb_sleutels if k not in AFB_CMDS]
    rap += ["", "## Afbeeldingen zonder overgetypte commando's",
            f"{len(zonder)} afbeeldingen. Draai `python build.py --ocr` om voorstellen te laten maken "
            "(afbeelding-commandos.voorstel.json).", ""]
    (ROOT / "bouwrapport.md").write_text("\n".join(rap) + "\n", encoding="utf-8")
    (ROOT / "onduidelijke-toestellen.md").write_text(
        "\n".join(["# Toestel onbekend ('?')", ""] + [f"- H{ch.num} › {u['sectie']} — `{u['tekst'].splitlines()[0]}`"
                                                  for ch in chapters for u in ch.unknown]) + "\n", encoding="utf-8")
    print(f"  zonder prompt: {sum(len(c.aangenomen) for c in chapters)} · '?': {sum(len(c.unknown) for c in chapters)}"
          f" · waarschuwingen: {sum(len(c.waarschuwingen) for c in chapters)} → bouwrapport.md")

    if a.ocr:
        ocr_voorstellen(chapters, overnemen=a.ocr_overnemen)

    # automatische controle van de gebouwde site
    try:
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "test_site.py")], capture_output=True, text=True, encoding="utf-8")
        print("  test: " + " | ".join(l.strip() for l in r.stdout.splitlines()[:2]))
        if r.returncode:
            print(r.stdout)
            print("  ⚠ De controle vond fouten — zie hierboven.")
    except Exception as e:
        print(f"  (controle overgeslagen: {e})")

    if not a.geen_zip:
        DIST.mkdir(exist_ok=True)
        zp = DIST / "cursus-offline.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in OUT.rglob("*"):
                if f.is_file():
                    z.write(f, Path("cursus") / f.relative_to(OUT))
        print(f"  ZIP: {zp} ({zp.stat().st_size // 1024} kB)")
    print("Klaar:", OUT)

if __name__ == "__main__":
    main()
