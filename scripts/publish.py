#!/usr/bin/env python3
"""Publie une veille quotidienne sur Zeraq (géopolitique et défense).

Usage :
    python3 scripts/publish.py AAAA-MM-JJ < veille.txt          # écrit, commit, push
    python3 scripts/publish.py AAAA-MM-JJ --dry-run < veille.txt # affiche seulement
    python3 scripts/publish.py AAAA-MM-JJ --delete               # retire une page
    python3 scripts/publish.py --rebuild                         # régénère accueil/archives/liens

Le texte (format WhatsApp ou Markdown) est lu sur stdin. Le script retire les
parties personnelles (« pour toi », tutoiement, mentions privées), convertit en
Markdown, vérifie que chaque actu a au moins une source, déduit des tags, écrit docs/AAAA/MM/AAAA-MM-JJ.md, régénère l'accueil,
les archives, la navigation à plat et les liens précédente/suivante des veilles, puis fait git add/commit/push. Relancer le même
jour remplace la page (idempotent). Aucune dépendance hors bibliothèque standard.
"""

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
MKDOCS_YML = REPO / "mkdocs.yml"

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

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

TAG_RULES = {
    "marine": r"marine|naval|navire|fr[eé]gate|sous-marin|porte-avions|flotte|amiral|"
              r"escadre|corvette|destroyer|patrouilleur|\bsnle\b|\bsna\b|d[eé]troit|"
              r"maritime|\bzee\b|piraterie",
    "défense": r"arm[eé]e|militaire|d[eé]fense|missile|munition|\bdrones?\b|chasseur|"
               r"rafale|\bf-35|blind[eé]|artillerie|\bopex\b|\botan\b|\bnato\b",
    "dissuasion": r"nucl[eé]aire|dissuasion|\bsnle\b|ogive|balistique",
    "industrie": r"industrie de d[eé]fense|\bbitd\b|naval group|thales|\bmbda\b|"
                 r"dassault|safran|\bknds\b|rheinmetall|contrat|commande|exportation",
    "Europe": r"\beurop[eé]|\bue\b|bruxelles|allemagne|royaume-uni|pologne|baltique|"
              r"m[eé]diterran[eé]e",
    "Russie-Ukraine": r"russ|ukrain|kremlin|poutine|zelensky|mer noire|crim[eé]e",
    "Moyen-Orient": r"isra[eë]l|\biran|gaza|liban|syrie|y[eé]men|houthi|arabie|golfe|"
                    r"mer rouge|irak|turquie|qatar",
    "Indo-Pacifique": r"chine|chinois|ta[iï]wan|japon|cor[eé]e|inde\b|indien|australie|"
                      r"philippines|pacifique|mer de chine|p[eé]kin",
    "Afrique": r"afrique|africain|sahel|mali|niger|soudan|somalie|djibouti|congo|"
               r"nig[eé]ria|[eé]thiopie|libye|alg[eé]rie|maroc",
    "Amériques": r"[eé]tats-unis|am[eé]ricain|washington|pentagone|maison blanche|trump|"
                 r"venezuela|br[eé]sil|canada|mexique|arctique",
    "cyber": r"cyber|piratage|ransomware|hacker|\banssi\b|d[eé]sinformation",
}


# --------------------------------------------------------------------------- utils

def fr_date(d, weekday=True):
    s = f"{d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]} {d.year}"
    return f"{JOURS[d.weekday()]} {s}" if weekday else s


def strip_accents(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def slugify(value, separator="-"):
    """Même algorithme que markdown.extensions.toc.slugify (ancres MkDocs)."""
    value = re.sub(r"[*_`]", "", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = strip_accents(value)
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[{}\s]+".format(separator), separator, value)


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


# ------------------------------------------------------------------------- parsing

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


def render_item(item):
    title = convert_inline(item["titre"]).replace("**", "")
    if PRIVATE_RE.search(title):
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
    if links:
        refs = []
        for i, u in enumerate(links):
            host = re.sub(r"^www\.", "", u.split("/")[2])
            label = "Source" if i == 0 else f"Source {i + 1}"
            refs.append(f"[{label} : {host}]({u})")
        out += ["", " · ".join(refs), "{ .source-link }"]
    return "\n".join([f"## {title}", ""] + out)


def deduce_tags(text):
    low = text.lower()
    # Un tag est retenu s'il revient au moins deux fois (une seule pour arXiv).
    tags = [t for t, rx in TAG_RULES.items()
            if len(re.findall(rx, low)) >= (1 if t == "recherche" else 2)]
    return tags or ["géopolitique"]


def build_page(date, text):
    items = parse(text)
    unsourced = [i["titre"] for i in items if not i["liens"]]
    if unsourced:
        raise SystemExit("Actus sans source (au moins un lien requis) :\n- "
                         + "\n- ".join(unsourced))
    rendered = [r for r in (render_item(i) for i in items) if r]
    if not rendered:
        raise SystemExit("Aucune actu exploitable trouvée dans le texte fourni.")
    body = "\n\n".join(rendered)
    tags = deduce_tags(body)
    title = f"Veille du {fr_date(date)}"
    fm = ["---", f"date: {date.isoformat()}", f'title: "{title}"',
          f'description: "{len(rendered)} actus géopolitique et défense du {fr_date(date, False)}"',
          "tags:"] + [f"  - {t}" for t in tags] + ["---", ""]
    return "\n".join(fm + [f"# {title}", "", body, ""]), len(rendered), tags


# --------------------------------------------------------------- index & navigation

def read_pages():
    pages = []
    for p in sorted(DOCS.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.md"), reverse=True):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.md", p.name)
        if not m:
            continue
        d = dt.date.fromisoformat(m.group(1))
        text = p.read_text(encoding="utf-8")
        heads = re.findall(r"^## (.+)$", text, re.MULTILINE)
        tags = re.findall(r"^  - (.+)$", text.split("\n---", 1)[0], re.MULTILINE)
        pages.append({"date": d, "path": p.relative_to(DOCS).as_posix(),
                      "titres": heads, "tags": tags})
    return pages


def anchors(titles):
    seen, out = {}, []
    for t in titles:
        s = slugify(t)
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 0
        out.append(s)
    return out


def date_label(d):
    return fr_date(d).capitalize()


def count_label(n):
    return f"{n} actu{'s' if n > 1 else ''}"


def write_index(pages):
    lines = ["---", "title: Accueil", "hide:", "  - navigation", "  - toc", "---", ""]
    if not pages:
        lines.append("*Aucune veille publiée pour l'instant.*\n")
    else:
        last = pages[0]
        body = (DOCS / last["path"]).read_text(encoding="utf-8")
        body = re.sub(r"^---\n.*?\n---\n", "", body, count=1, flags=re.S)
        body = re.sub(r"^# .*\n", "", body, count=1, flags=re.M)
        # Coupe la navigation précédente/suivante éventuelle de la page du jour
        body = body.split("<!-- BEGIN NAV-VEILLES -->")[0].rstrip()
        # Titres d'actu en ### : les étoiles favoris restent sur la page datée
        body = re.sub(r"^## ", "### ", body, flags=re.M)
        lines += [f"## {date_label(last['date'])}", "", body, ""]
        if len(pages) > 1:
            lines += ["## Veilles précédentes", ""]
            for p in pages[1:8]:
                lines.append(f"- [{date_label(p['date'])}]({p['path']}) — "
                             f"{count_label(len(p['titres']))}")
            lines += ["", "[Toutes les veilles dans les archives →](archives.md)", ""]
    lines += ["", "---", "",
              "<small>Zeraq : une sélection quotidienne d'actus en géopolitique, défense et "
              "affaires maritimes, chacune avec ses sources. "
              "[Voir les sources suivies](sources.md).</small>", ""]
    (DOCS / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_archives(pages):
    lines = ["---", "title: Archives", "hide:", "  - navigation", "---", "",
             "# Archives", "",
             f"{len(pages)} veilles publiées, de la plus récente à la plus ancienne.", ""]
    month = None
    for p in pages:
        key = (p["date"].year, p["date"].month)
        if key != month:
            if month is not None:
                lines.append("")
            month = key
            lines += [f"## {MOIS[key[1] - 1].capitalize()} {key[0]}", ""]
        lines.append(f"- [{date_label(p['date'])}]({p['path']}) — "
                     f"{count_label(len(p['titres']))}")
    lines.append("")
    (DOCS / "archives.md").write_text("\n".join(lines), encoding="utf-8")


NAV = """nav:
  - Accueil: index.md
  - Archives: archives.md
  - Tags: tags.md
  - Sources: sources.md
  - Favoris: favoris.md"""


def write_nav():
    """Navigation à plat : les pages de jour n'y figurent pas (accès via accueil/archives)."""
    yml = MKDOCS_YML.read_text(encoding="utf-8")
    new = re.sub(r"# BEGIN NAV\n.*?# END NAV",
                 lambda m: "# BEGIN NAV\n" + NAV + "\n# END NAV", yml, flags=re.DOTALL)
    if new != yml:
        MKDOCS_YML.write_text(new, encoding="utf-8")


DAYNAV_RE = re.compile(r"\n*<!-- BEGIN NAV-VEILLES -->.*?<!-- END NAV-VEILLES -->\n*",
                       re.DOTALL)


def write_day_links(pages):
    """Ajoute en bas de chaque veille les liens vers la précédente et la suivante."""
    for i, p in enumerate(pages):  # pages : de la plus récente à la plus ancienne
        here = DOCS / p["path"]
        base = here.parent

        def link(q, fmt):
            rel = os.path.relpath(DOCS / q["path"], base).replace(os.sep, "/")
            return f"[{fmt.format(fr_date(q['date']))}]({rel})"

        prev = pages[i + 1] if i + 1 < len(pages) else None
        nxt = pages[i - 1] if i > 0 else None
        parts = []
        if prev:
            parts.append(link(prev, "← Veille précédente : {}") + "{ .veille-prev }")
        if nxt:
            parts.append(link(nxt, "Veille suivante : {} →") + "{ .veille-next }")
        text = here.read_text(encoding="utf-8")
        body = DAYNAV_RE.sub("\n", text).rstrip("\n") + "\n"
        if parts:
            body += ("\n<!-- BEGIN NAV-VEILLES -->\n<div class=\"veille-nav\" markdown>\n\n"
                     + "\n\n".join(parts) + "\n\n</div>\n<!-- END NAV-VEILLES -->\n")
        if body != text:
            here.write_text(body, encoding="utf-8")


def rebuild():
    pages = read_pages()
    write_index(pages)
    write_archives(pages)
    write_nav()
    write_day_links(pages)
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
                    help="régénère seulement accueil, archives, navigation et liens entre veilles")
    a = ap.parse_args()

    if a.rebuild and not a.date:
        rebuild()
        print("Accueil, archives, navigation et liens entre veilles régénérés.")
        if not a.no_git and not a.dry_run:
            commit_and_push("Régénère les index", push=not a.no_push)
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
    page, n, tags = build_page(date, text)
    if a.dry_run:
        print(page)
        print(f"[dry-run] {target.relative_to(REPO)} : {n} actus, tags {', '.join(tags)}",
              file=sys.stderr)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(page, encoding="utf-8")
    rebuild()
    print(f"{'Remplacée' if existed else 'Écrite'} : {target.relative_to(REPO)} "
          f"({n} actus ; tags : {', '.join(tags)})")
    if not a.no_git:
        commit_and_push(f"Veille du {date.isoformat()}", push=not a.no_push)


if __name__ == "__main__":
    main()
