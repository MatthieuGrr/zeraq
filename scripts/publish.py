#!/usr/bin/env python3
"""Publie une veille quotidienne (site MkDocs Material).

Usage :
    python3 scripts/publish.py AAAA-MM-JJ < veille.txt          # écrit, commit, push
    python3 scripts/publish.py AAAA-MM-JJ --dry-run < veille.txt # affiche seulement
    python3 scripts/publish.py AAAA-MM-JJ --delete               # retire une page
    python3 scripts/publish.py --rebuild                         # régénère tout le site

Le texte (format WhatsApp ou Markdown) est lu sur stdin. Le script retire les
parties personnelles (« pour toi », tutoiement, mentions privées), convertit en
Markdown et écrit docs/AAAA/MM/AAAA-MM-JJ.md. Il régénère ensuite tout ce qui en
dépend : mise en forme des pages de jour, thèmes de chaque actu, accueil, archives,
pages de thèmes, flux Atom, navigation et liens précédente/suivante, puis fait
git add/commit/push. Relancer le même jour remplace la page (idempotent).

Ce fichier est identique sur tous les sites de veille : ce qui est propre à un site
(nom, règles de thèmes, noms des sources) est dans scripts/site_config.py.
Aucune dépendance hors bibliothèque standard.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

import site_config as S

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
MKDOCS_YML = REPO / "mkdocs.yml"
THEMES_DIR = "themes"

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
               "sept.", "oct.", "nov.", "déc."]

# Paragraphes d'avis personnel à supprimer entièrement.
OPINION_RE = re.compile(
    r"^(pour toi|pour vous|ce que (j'en|tu en|j’en|tu en) retiens|à retenir|a retenir|"
    r"pourquoi (ça|ca) compte|à creuser|a creuser|ce qu'il faut retenir|mon avis|"
    r"en pratique)\b",
    re.IGNORECASE,
)
# Phrases à retirer : tutoiement, première personne de l'assistant, mentions privées.
PERSONAL_RE = re.compile(
    r"\b(tu|toi|ton|ta|tes|te|tien|tiens|vous|votre|vos|je|moi|mon|ma|mes)\b|\b[tjm]['’]",
    re.IGNORECASE,
)
PRIVATE_RE = re.compile(
    r"\bPHARE\b|\bMatthieu\b|\bRosetta\b|\bMARS\b|\bLUNE\b|"
    r"\+\d{2}[\s.]?\d([\s.]?\d{2}){4}|\b0[1-9]([\s.]?\d{2}){4}\b"
)
# Lignes de fin de message sans contenu.
CHATTER_RE = re.compile(
    r"^(rien de (neuf|nouveau)|bon(ne)? (samedi|dimanche|lundi|mardi|mercredi|jeudi|"
    r"vendredi|week-end|journée|lecture)|papiers? .* lus? au niveau)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>()\[\]]+[^\s<>()\[\].,;:!?…'\"»]")


# --------------------------------------------------------------------------- utils

def fr_date(d, weekday=True):
    s = f"{d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]} {d.year}"
    return f"{JOURS[d.weekday()]} {s}" if weekday else s


def date_label(d):
    return fr_date(d).capitalize()


def short_date(d):
    return f"{d.day}{'er' if d.day == 1 else ''} {MOIS_COURTS[d.month - 1]}"


def count_label(n):
    return f"{n} actu{'s' if n > 1 else ''}"


def strip_accents(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def slugify(value, separator="-"):
    """Même algorithme que markdown.extensions.toc.slugify (ancres MkDocs)."""
    value = re.sub(r"[*_`]", "", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = strip_accents(value)
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[{}\s]+".format(separator), separator, value)


def plain(md):
    """Texte brut d'un fragment Markdown simple."""
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"<(https?://[^>]+)>", r"\1", md)
    md = re.sub(r"(?<!\w)_|_(?!\w)", "", md)  # garde les _ au milieu d'un mot
    return re.sub(r"[*`]", "", md)


def clean_title(title):
    """Retire l'attribut d'ancre final et une éventuelle puce en tête de titre."""
    title = re.sub(r"\s*\{[^{}]*\}\s*$", "", title)
    return re.sub(r"^\s*[-–—•]\s+", "", title).strip()


def truncate(s, n):
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0].rstrip(" ,;:·") + "…"


def decoration_strip(s):
    """Retire puces, emojis et marques de mise en forme en tête de ligne."""
    return re.sub(r"^[\s*_👉•\-–—>💡🔹▶️➡️]+", "", s)


def is_bare_url(line):
    return bool(re.fullmatch(r"<?(https?://\S+?)>?", line.strip()))


def convert_inline(text):
    """*gras* WhatsApp -> **gras**, _italique_ -> *italique*, en protégeant code et URL."""
    protected = []

    def keep(m, fmt="{}"):
        protected.append(fmt.format(m.group(0)))
        return f"\x00{len(protected) - 1}\x00"

    text = re.sub(r"`[^`]+`", keep, text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", keep, text)
    text = re.sub(r"<https?://[^>]+>", keep, text)
    text = re.sub(r"\*\*[^*]+\*\*", keep, text)  # déjà en Markdown
    text = URL_RE.sub(lambda m: keep(m, "<{}>"), text)
    text = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"**\1**", text)
    text = re.sub(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])", r"*\1*", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], text)


def clean_sentences(text):
    """Supprime les phrases personnelles ou privées d'un paragraphe."""
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ«\"(*_0-9])", text.strip())
    kept = [p for p in parts
            if p and not PERSONAL_RE.search(re.sub(r"«[^»]*»|\"[^\"]*\"|`[^`]*`", "", p))
            and not PRIVATE_RE.search(p)
            and not CHATTER_RE.match(decoration_strip(p))]
    return " ".join(kept).strip()


# --------------------------------------------------- lecture du texte brut (stdin)

HEADER_RE = re.compile(r"^(?P<pre>[^\w*]*)\*(?P<bold>[^*]+)\*(?P<rest>.*)$")


def parse_header(line):
    """Renvoie (titre, reste) si la ligne est un titre d'actu, sinon None."""
    s = line.strip()
    if s.startswith("## "):
        return s[3:].strip(), ""
    m = HEADER_RE.match(s)
    if not m or len(m.group("pre")) > 4:
        return None
    bold, rest = m.group("bold").strip(), m.group("rest").strip()
    if OPINION_RE.match(decoration_strip(bold)):
        return None
    if bold.endswith(":") and len(rest) > 40:
        return (m.group("pre") + bold.rstrip(" :")).strip(), rest
    if len(rest) > 60:
        return None
    return (m.group("pre") + bold + (" " + rest if rest else "")).strip(), ""


def parse(text):
    """Découpe le texte en actus : liste de dicts {titre, paras, liens}."""
    lines = text.replace("\r\n", "\n").split("\n")
    # Front-matter Markdown éventuel
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
            lines = lines[end + 1:]
        except ValueError:
            pass
    # Préambule avant le titre « Veille du … »
    for i, line in enumerate(lines):
        if re.search(r"veille du", line, re.IGNORECASE) and (
                line.lstrip().startswith(("#", "*", "🛰")) or "🛰" in line):
            lines = lines[i + 1:]
            break

    items, cur = [], None
    for raw in lines:
        line = raw.rstrip()
        if line.lstrip().startswith("# "):
            continue
        header = parse_header(line)
        if header:
            title, rest = header
            title = re.sub(r"^(\W*?)\d+[.)]\s*", r"\1", title).strip()
            cur = {"titre": title, "paras": [], "liens": []}
            items.append(cur)
            if rest:
                cur["paras"].append(rest)
            continue
        if cur is None or not line.strip():
            if cur is not None and cur["paras"] and cur["paras"][-1] != "":
                cur["paras"].append("")
            continue
        s = line.strip()
        if is_bare_url(s):
            cur["liens"].append(s.strip("<>"))
            continue
        md_link = re.fullmatch(r"(?:[^\[]*)\[([^\]]+)\]\((https?://[^)]+)\)(\{[^}]*\})?", s)
        if md_link and len(s) < len(md_link.group(2)) + 60 and re.match(
                r"^[^\w]*(source|lien|sources)\b|^\[", s, re.IGNORECASE):
            cur["liens"].append(md_link.group(2))
            continue
        cur["paras"].append(s)
    return items


def bullet_or_para(s):
    m = re.match(r"^[•\-–]\s+(.*)", s)
    return ("- ", m.group(1)) if m else ("", s)


def clean_item(item):
    """Nettoie une actu brute : renvoie {titre, corps, liens} ou None si elle est vide."""
    title = clean_title(convert_inline(item["titre"]).replace("**", ""))
    if not title or PRIVATE_RE.search(title):
        return None
    blocks, para = [], []

    def flush():
        if para:
            blocks.append(" ".join(para))
            para.clear()

    for p in item["paras"] + [""]:
        if not p:
            flush()
            continue
        if OPINION_RE.match(decoration_strip(p)) or CHATTER_RE.match(decoration_strip(p)):
            flush()
            continue
        prefix, body = bullet_or_para(p)
        body = clean_sentences(body)
        if not body:
            continue
        body = convert_inline(body)
        if prefix:
            flush()
            blocks.append(prefix + body)
        else:
            para.append(body)
    # Les puces consécutives forment une liste
    out, prev_bullet = [], False
    for b in blocks:
        bullet = b.startswith("- ")
        if out and not (bullet and prev_bullet):
            out.append("")
        out.append(b)
        prev_bullet = bullet
    links = [u for u in dict.fromkeys(item["liens"]) if not PRIVATE_RE.search(u)]
    if not out and not links:
        return None
    return {"titre": title, "corps": "\n".join(out), "liens": links}


def items_from_text(text):
    items = parse(text)
    if S.SOURCE_OBLIGATOIRE:
        unsourced = [i["titre"] for i in items if not i["liens"]]
        if unsourced:
            raise SystemExit("Actus sans source (au moins un lien requis) :\n- "
                             + "\n- ".join(unsourced))
    cleaned = [c for c in (clean_item(i) for i in items) if c]
    if not cleaned:
        raise SystemExit("Aucune actu exploitable trouvée dans le texte fourni.")
    return cleaned


# ----------------------------------------------------- lecture des pages publiées

FRONT_RE = re.compile(r"\A---\n.*?\n---\n", re.S)
GENERATED_RE = re.compile(
    r"\n*<!-- BEGIN (META|NAV-VEILLES) -->.*?<!-- END \1 -->\n*", re.S)
FOOT_MARKS = ("{ .source-link }", "{ .actu-foot }")


def parse_day(text):
    """Relit une page de jour (ancien ou nouveau gabarit) : liste de {titre, corps, liens}."""
    text = FRONT_RE.sub("", text, count=1)
    text = GENERATED_RE.sub("\n\n", text)
    items, cur = [], None
    for line in text.split("\n"):
        if line.startswith("## "):
            cur = {"titre": clean_title(line[3:]), "lines": [], "liens": []}
            items.append(cur)
        elif cur is not None and not re.fullmatch(r"</?section\b[^>]*>", line.strip()):
            cur["lines"].append(line)
    for it in items:
        body = []
        for line in it.pop("lines"):
            if line.strip() in FOOT_MARKS:
                foot = body.pop() if body else ""
                it["liens"] += re.findall(r"\]\((https?://[^)\s]+)\)", foot)
            else:
                body.append(line)
        it["corps"] = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()
    return items


def read_pages():
    """Toutes les veilles, de la plus récente à la plus ancienne."""
    pages = []
    for p in sorted(DOCS.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.md"), reverse=True):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.md", p.name)
        if not m:
            continue
        items = parse_day(p.read_text(encoding="utf-8"))
        pages.append(make_page(dt.date.fromisoformat(m.group(1)), items))
    return pages


# ------------------------------------------------------------- modèle d'une veille

def anchors(titles):
    seen, out = {}, []
    for n, t in enumerate(titles, 1):
        s = slugify(t) or f"actu-{n}"
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 0
        out.append(s)
    return out


def item_tags(item):
    """Thèmes d'une actu : les règles les plus présentes (le titre compte triple)."""
    if is_concept(item) and "concept" in S.TAG_RULES:
        return ["concept"]
    title = plain(item["titre"]).lower()
    rest = (plain(item["corps"]) + "\n" + " ".join(item["liens"])).lower()
    scored = []
    for order, (tag, rx) in enumerate(S.TAG_RULES.items()):
        score = 3 * len(re.findall(rx, title)) + len(re.findall(rx, rest))
        if score:
            scored.append((-score, order, tag))
    return [t for _, _, t in sorted(scored)[:S.MAX_TAGS_ACTU]] or [S.TAG_DEFAUT]


def is_concept(item):
    return bool(re.match(r"^\W*concept du jour\b", item["titre"], re.IGNORECASE))


def make_page(date, items):
    for it, anchor in zip(items, anchors([i["titre"] for i in items])):
        it["id"] = anchor
        it["tags"] = item_tags(it)
    counts = {}
    for it in items:
        for t in it["tags"]:
            counts[t] = counts.get(t, 0) + 1
    order = list(S.TAG_RULES) + [S.TAG_DEFAUT]
    tags = sorted(counts, key=lambda t: (-counts[t], order.index(t)))
    words = sum(len(plain(i["titre"] + " " + i["corps"]).split()) for i in items)
    return {"date": date, "items": items, "tags": tags,
            "path": f"{date:%Y}/{date:%m}/{date.isoformat()}.md",
            "url": f"{date:%Y}/{date:%m}/{date.isoformat()}/",
            "minutes": max(1, round(words / 220))}


def source_label(url):
    host = re.sub(r"^www\.", "", (urlsplit(url).hostname or url).lower())
    for known, label in S.SOURCES.items():
        if host == known or host.endswith("." + known):
            return label
    return host


def source_links(item):
    seen, out = {}, []
    for u in item["liens"]:
        label = source_label(u)
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} ({seen[label]})"
        out.append((label, u))
    return out


def theme_path(tag):
    return f"{THEMES_DIR}/{slugify(tag)}.md"


def rel(target, from_dir):
    return os.path.relpath(DOCS / target, DOCS / from_dir).replace(os.sep, "/")


def meta_line(page):
    return (f"**{count_label(len(page['items']))}** · "
            f"{page['minutes']} min de lecture\n{{ .veille-meta }}")


def tag_chips(tags, from_dir):
    return " ".join(f"[{t}]({rel(theme_path(t), from_dir)}){{ .tag }}" for t in tags)


def render_item(item, from_dir, level=2, fav=None):
    """Bloc Markdown d'une actu (page de jour : ##, accueil : ### avec data-fav)."""
    attrs = f"#{item['id']}" + (f' data-fav="{fav}"' if fav else "")
    cls = "actu actu--concept" if is_concept(item) else "actu"
    out = [f'<section class="{cls}" markdown>', "",
           f"{'#' * level} {item['titre']} {{ {attrs} }}", ""]
    if item["corps"]:
        out += [item["corps"], ""]
    foot = [f'[{label}]({u}){{ .src target="_blank" rel="noopener" }}'
            for label, u in source_links(item)]
    foot.append(tag_chips(item["tags"], from_dir))
    out += [" ".join(foot), "{ .actu-foot }", "", "</section>"]
    return "\n".join(out)


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)


def render_day(page, prev=None, nxt=None):
    """Page de jour complète. prev/nxt : veilles voisines (ou None)."""
    d = page["date"]
    here = os.path.dirname(page["path"])
    title = f"Veille du {fr_date(d)}"
    sommaire = truncate(" · ".join(plain(i["titre"]) for i in page["items"]), 220)
    out = ["---", f"date: {d.isoformat()}", f"title: {yaml_str(title)}",
           f"description: {yaml_str(sommaire)}", "tags:"]
    out += [f"  - {t}" for t in page["tags"]]
    out += ["hide:", "  - navigation", "---", "", f"# {title}", "",
            "<!-- BEGIN META -->", meta_line(page), "",
            tag_chips(page["tags"], here), "{ .veille-tags }", "<!-- END META -->", ""]
    for it in page["items"]:
        out += [render_item(it, here), ""]
    links = []
    if prev:
        links.append(f"[← {date_label(prev['date'])}]({rel(prev['path'], here)})"
                     "{ .veille-prev }")
    if nxt:
        links.append(f"[{date_label(nxt['date'])} →]({rel(nxt['path'], here)})"
                     "{ .veille-next }")
    if links:
        out += ["<!-- BEGIN NAV-VEILLES -->", '<div class="veille-nav" markdown>', "",
                "\n\n".join(links), "", "</div>", "<!-- END NAV-VEILLES -->", ""]
    return "\n".join(out)


# ------------------------------------------------------------------ pages générées

def write(path, content):
    path = DOCS / path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def write_days(pages):
    for i, p in enumerate(pages):  # pages : de la plus récente à la plus ancienne
        prev = pages[i + 1] if i + 1 < len(pages) else None
        nxt = pages[i - 1] if i > 0 else None
        write(p["path"], render_day(p, prev, nxt))


def day_card(page):
    titles = [plain(i["titre"]) for i in page["items"] if not is_concept(i)]
    lines = [f"- [**{date_label(page['date'])}**]({page['path']}) "
             f"<span class=\"carte-meta\">{count_label(len(page['items']))} · "
             f"{page['minutes']} min</span>", ""]
    lines += [f"    - {truncate(t, 90)}" for t in titles[:3]]
    if len(titles) > 3:
        lines.append(f"    - *et {len(page['items']) - 3} autres…*")
    return lines + [""]


def write_index(pages):
    out = ["---", f"title: {yaml_str(S.NOM)}", f"description: {yaml_str(S.DESCRIPTION)}",
           "hide:", "  - navigation", "  - toc", "search:", "  exclude: true", "---", "",
           '<div class="hero" markdown>', "", f"# {S.NOM} {S.EMOJI}", "",
           S.BASELINE, "{ .hero-baseline }", ""]
    buttons = []
    if pages:
        buttons.append(f"[Lire la veille du jour]({pages[0]['path']})"
                       "{ .md-button .md-button--primary }")
    buttons += ["[Archives](archives.md){ .md-button }", "[Thèmes](tags.md){ .md-button }",
                "[Flux RSS](feed.xml){ .md-button }"]
    out += [" ".join(buttons), "{ .hero-actions }", "", "</div>", ""]
    if not pages:
        out += ["*Aucune veille publiée pour l'instant.*", ""]
    else:
        last = pages[0]
        out += [f"## [{date_label(last['date'])}]({last['path']}) {{ .jour }}", "",
                meta_line(last), ""]
        for it in last["items"]:
            out += [render_item(it, "", level=3, fav=f"{last['url']}#{it['id']}"), ""]
        if len(pages) > 1:
            out += ["## Veilles précédentes", "", '<div class="cartes" markdown>', ""]
            for p in pages[1:7]:
                out += day_card(p)
            out += ["</div>", "",
                    f"[Les {len(pages)} veilles dans les archives →](archives.md)"
                    "{ .lien-suite }", ""]
    out += ['<p class="a-propos" markdown>', S.PIED, "</p>", ""]
    write("index.md", "\n".join(out))


def write_archives(pages):
    n_items = sum(len(p["items"]) for p in pages)
    out = ["---", "title: Archives", "hide:", "  - navigation", "---", "", "# Archives", "",
           f"{len(pages)} veilles et {n_items} actus, de la plus récente à la plus ancienne.",
           "{ .veille-meta }", ""]
    month = None
    for p in pages:
        key = (p["date"].year, p["date"].month)
        if key != month:
            if month is not None:
                out += ["</div>", ""]
            month = key
            out += [f"## {MOIS[key[1] - 1].capitalize()} {key[0]}", "",
                    '<div class="archives" markdown>', ""]
        titles = " · ".join(truncate(plain(i["titre"]), 70) for i in p["items"]
                            if not is_concept(i))
        out += [f"[**{date_label(p['date'])}**]({p['path']}) "
                f"<span class=\"carte-meta\">{count_label(len(p['items']))}</span>  ",
                titles, ""]
    if month is not None:
        out += ["</div>", ""]
    write("archives.md", "\n".join(out))


def write_themes(pages):
    """Page « Thèmes » (les dernières actus de chaque thème) et une page par thème."""
    by_tag = {}
    for p in pages:
        for it in p["items"]:
            for t in it["tags"]:
                by_tag.setdefault(t, []).append((p, it))
    order = [t for t in list(S.TAG_RULES) + [S.TAG_DEFAUT] if t in by_tag]

    def entry(p, it, from_dir, year=False):
        when = short_date(p["date"]) + (f" {p['date'].year}" if year else "")
        return (f"- [{plain(it['titre'])}]({rel(p['path'], from_dir)}#{it['id']}) "
                f"<span class=\"carte-meta\">{when}</span>")

    out = ["---", "title: Thèmes", "hide:", "  - navigation", "search:", "  exclude: true",
           "---", "", "# Thèmes", "",
           "Chaque actu est rangée dans un ou deux thèmes. Voici les plus récentes de chacun.",
           "{ .veille-meta }", "",
           " ".join(f"[{t} <small>{len(by_tag[t])}</small>](#{slugify(t)}){{ .tag }}"
                    for t in order), "{ .veille-tags }", ""]
    for t in order:
        entries = by_tag[t]
        out += [f"## {t} {{ #{slugify(t)} }}", ""]
        out += [entry(p, it, "") for p, it in entries[:6]]
        out += ["", f"[Les {len(entries)} actus « {t} » →]({theme_path(t)})"
                    "{ .lien-suite }", ""]
    write("tags.md", "\n".join(out))

    keep = set()
    for t in order:
        entries = by_tag[t]
        out = ["---", f"title: {yaml_str('Thème : ' + t)}", "hide:", "  - navigation",
               "search:", "  exclude: true", "---", "", f"# {t}", "",
               f"{count_label(len(entries))} sur ce thème · [tous les thèmes](../tags.md)",
               "{ .veille-meta }", ""]
        month = None
        for p, it in entries:
            key = (p["date"].year, p["date"].month)
            if key != month:
                month = key
                out += ["", f"## {MOIS[key[1] - 1].capitalize()} {key[0]}", ""]
            out.append(entry(p, it, THEMES_DIR))
        write(theme_path(t), "\n".join(out) + "\n")
        keep.add(DOCS / theme_path(t))
    themes = DOCS / THEMES_DIR
    if themes.is_dir():
        for f in themes.glob("*.md"):
            if f not in keep:
                f.unlink()
        if not any(themes.iterdir()):
            themes.rmdir()


# ------------------------------------------------------------------------ flux Atom

def site_url():
    m = re.search(r"^site_url:\s*(\S+)", MKDOCS_YML.read_text(encoding="utf-8"), re.M)
    return (m.group(1).rstrip("/") + "/") if m else "/"


def inline_html(md):
    protected = []

    def keep(value):
        protected.append(value)
        return f"\x00{len(protected) - 1}\x00"

    md = re.sub(r"`([^`]+)`", lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), md)
    md = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)",
                lambda m: keep(f'<a href="{html.escape(m.group(2))}">'
                               f"{html.escape(m.group(1))}</a>"), md)
    md = re.sub(r"<(https?://[^>]+)>",
                lambda m: keep('<a href="{0}">{0}</a>'.format(html.escape(m.group(1)))), md)
    md = html.escape(md, quote=False)
    md = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", md)
    md = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", md)
    return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], md)


def item_html(item, day_url):
    out = [f'<h2><a href="{day_url}#{item["id"]}">{inline_html(item["titre"])}</a></h2>']
    for block in re.split(r"\n\s*\n", item["corps"]):
        lines = [x for x in block.split("\n") if x.strip()]
        if not lines:
            continue
        if all(x.startswith("- ") for x in lines):
            out.append("<ul>" + "".join(f"<li>{inline_html(x[2:])}</li>" for x in lines)
                       + "</ul>")
        else:
            out.append(f"<p>{inline_html(' '.join(lines))}</p>")
    srcs = ", ".join(f'<a href="{html.escape(u)}">{html.escape(label)}</a>'
                     for label, u in source_links(item))
    if srcs:
        out.append(f"<p><small>Source{'s' if len(item['liens']) > 1 else ''} : {srcs}"
                   "</small></p>")
    return "\n".join(out)


def write_feed(pages):
    base = site_url()
    esc = html.escape
    stamp = lambda d: f"{d.isoformat()}T06:00:00Z"
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="fr">',
           f"<title>{esc(S.NOM)}</title>", f"<subtitle>{esc(S.DESCRIPTION)}</subtitle>",
           f'<link href="{base}"/>', f'<link rel="self" href="{base}feed.xml"/>',
           f"<id>{base}</id>", f"<author><name>{esc(S.NOM)}</name></author>",
           f"<updated>{stamp(pages[0]['date']) if pages else '1970-01-01T00:00:00Z'}</updated>"]
    for p in pages[:20]:
        url = base + p["url"]
        summary = " · ".join(plain(i["titre"]) for i in p["items"])
        content = "\n".join(item_html(i, url) for i in p["items"])
        out += ["<entry>", f"<title>Veille du {esc(fr_date(p['date']))}</title>",
                f'<link href="{url}"/>', f"<id>{url}</id>",
                f"<published>{stamp(p['date'])}</published>",
                f"<updated>{stamp(p['date'])}</updated>"]
        out += [f'<category term="{esc(t)}"/>' for t in p["tags"]]
        out += [f"<summary>{esc(summary)}</summary>",
                f'<content type="html">{esc(content)}</content>', "</entry>"]
    out.append("</feed>")
    write("feed.xml", "\n".join(out) + "\n")


def write_nav():
    """Navigation à plat : les pages de jour n'y figurent pas (accès via accueil/archives)."""
    nav = "nav:\n" + "\n".join(f"  - {label}: {path}" for label, path in S.NAV)
    yml = MKDOCS_YML.read_text(encoding="utf-8")
    new = re.sub(r"# BEGIN NAV\n.*?# END NAV",
                 lambda m: "# BEGIN NAV\n" + nav + "\n# END NAV", yml, flags=re.DOTALL)
    if new != yml:
        MKDOCS_YML.write_text(new, encoding="utf-8")


def rebuild():
    pages = read_pages()
    write_days(pages)
    write_index(pages)
    write_archives(pages)
    write_themes(pages)
    write_feed(pages)
    write_nav()
    return pages


# ------------------------------------------------------------------------------ git

def git(*args, check=True):
    return subprocess.run(["git", "-C", str(REPO), *args], check=check,
                          capture_output=True, text=True)


def commit_and_push(message, push=True):
    if git("remote", check=False).stdout.strip() and push:
        git("pull", "--rebase", "--autostash", "-q", check=False)
    git("add", "-A", "docs", "mkdocs.yml")
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        print("Rien de nouveau à publier (page identique).")
        return
    git("commit", "-q", "-m", message)
    print(f"Commit : {message}")
    if push:
        r = git("push", "-q", "origin", "HEAD:main", check=False)
        if r.returncode:
            raise SystemExit(f"Échec du push :\n{r.stderr}")
        print("Poussé sur origin/main.")


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("date", nargs="?", help="date de la veille, AAAA-MM-JJ")
    ap.add_argument("--dry-run", action="store_true",
                    help="affiche la page générée sans rien écrire ni committer")
    ap.add_argument("--no-push", action="store_true", help="commit local sans push")
    ap.add_argument("--no-git", action="store_true", help="écrit les fichiers sans git")
    ap.add_argument("--delete", action="store_true", help="supprime la page de cette date")
    ap.add_argument("--rebuild", action="store_true",
                    help="régénère pages de jour, accueil, archives, thèmes et flux")
    a = ap.parse_args()

    if a.rebuild and not a.date:
        rebuild()
        print("Pages de jour, accueil, archives, thèmes, flux et navigation régénérés.")
        if not a.no_git and not a.dry_run:
            commit_and_push("Régénère le site", push=not a.no_push)
        return
    if not a.date:
        ap.error("date requise (AAAA-MM-JJ)")
    try:
        date = dt.date.fromisoformat(a.date)
    except ValueError:
        ap.error(f"date invalide : {a.date}")
    target = DOCS / f"{date:%Y}" / f"{date:%m}" / f"{date.isoformat()}.md"

    if a.delete:
        if a.dry_run:
            print(f"[dry-run] supprimerait {target.relative_to(REPO)}")
            return
        if target.exists():
            target.unlink()
            for d in (target.parent, target.parent.parent):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
        rebuild()
        if not a.no_git:
            commit_and_push(f"Retire la veille du {date.isoformat()}", push=not a.no_push)
        return

    text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("Texte de veille vide sur stdin.")
    page = make_page(date, items_from_text(text))
    n, tags = len(page["items"]), ", ".join(page["tags"])
    if a.dry_run:
        print(render_day(page))
        print(f"[dry-run] {target.relative_to(REPO)} : {n} actus, thèmes {tags}",
              file=sys.stderr)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(render_day(page), encoding="utf-8")
    rebuild()
    print(f"{'Remplacée' if existed else 'Écrite'} : {target.relative_to(REPO)} "
          f"({n} actus ; thèmes : {tags})")
    if not a.no_git:
        commit_and_push(f"Veille du {date.isoformat()}", push=not a.no_push)


if __name__ == "__main__":
    main()
