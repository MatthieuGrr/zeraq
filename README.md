# Zeraq ⚓

*Zeraq*, le quart de minuit à quatre heures, celui qui demande le plus d'attention :
veille quotidienne géopolitique, défense et affaires maritimes, une page par jour avec
des résumés courts et les liens vers les sources (au moins une par actu).

**Site :** https://zeraq.georger.ovh/

## Organisation

- `docs/AAAA/MM/AAAA-MM-JJ.md` : une page par veille. Chaque actu est un bloc
  `<section class="actu">` : titre `##`, résumé, puis une ligne de liens (sources et thèmes).
- **Générés** par le script à chaque publication (ne pas éditer à la main) : la mise en forme
  des pages de jour (méta, thèmes, liens précédente/suivante), `docs/index.md` (dernière
  veille + 6 précédentes), `docs/archives.md`, `docs/tags.md` et `docs/themes/*.md` (actus
  rangées par thème), `docs/feed.xml` (flux Atom des 20 dernières veilles) et la `nav` de
  `mkdocs.yml` (Accueil, Archives, Thèmes, Sources, Favoris). Les pages de jour et de thème ne sont pas dans le menu
  (`not_in_nav`).
- `scripts/site_config.py` : tout ce qui est propre à ce site (nom, textes d'accueil, règles
  de thèmes par mots-clés, noms affichés des sources). `scripts/publish.py`,
  `docs/assets/veille.css`, `docs/assets/favoris.js` et `overrides/main.html` sont identiques
  sur Télémétrie et Zeraq ; les couleurs et polices du site sont dans `docs/assets/theme.css`.
- `docs/sources.md` : liste des sources suivies, éditée à la main.
- `docs/favoris.md` : favoris locaux (☆ sur chaque actu, y compris sur l'accueil, stockés
  dans le navigateur) et section « Favoris épinglés » éditée à la main.
- `overrides/main.html` : lien vers le flux et balises de partage (image `assets/social.png`).

## Publier une veille

```bash
python3 scripts/publish.py 2026-11-07 < veille.txt            # écrit, commit, push
python3 scripts/publish.py 2026-11-07 --dry-run < veille.txt  # aperçu, rien n'est écrit
python3 scripts/publish.py 2026-11-07 --delete                # retire une page
python3 scripts/publish.py --rebuild                          # régénère tout le site à partir des pages de jour
```

Le texte peut être au format WhatsApp (`*gras*`, `_italique_`, URL nues) ou Markdown.
Le script refuse toute actu sans lien source, retire les commentaires personnels, range chaque actu dans un ou deux thèmes par mots-clés et
remplace la page si elle existe déjà (idempotent). Bibliothèque standard uniquement.

## Développement local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/mkdocs serve
```

Après un changement de règles de thèmes ou de gabarit, `--rebuild` remet toutes les pages à jour.

Chaque push sur `main` déclenche le déploiement GitHub Pages (`.github/workflows/deploy.yml`).
