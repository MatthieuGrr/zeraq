"""Réglages propres à Zeraq, lus par scripts/publish.py."""

NOM = "Zeraq"
EMOJI = "⚓"
DESCRIPTION = "Veille quotidienne géopolitique, défense et affaires maritimes"
BASELINE = ("*Zeraq*, le quart de minuit à quatre heures, celui qui demande le plus "
            "d'attention : chaque matin, l'essentiel en géopolitique, défense et affaires "
            "maritimes, résumé en quelques lignes et toujours sourcé.")
PIED = ("Zeraq est une veille automatisée : les résumés sont rédigés par un assistant IA "
        "à partir des articles cités sous chaque actu. "
        "[Voir les sources suivies](sources.md).")

# True : la publication est refusée si une actu n'a aucun lien source.
SOURCE_OBLIGATOIRE = True

NAV = [("Accueil", "index.md"), ("Archives", "archives.md"), ("Thèmes", "tags.md"),
       ("Sources", "sources.md"), ("Favoris", "favoris.md")]

# Thèmes déduits par mots-clés (texte en minuscules). Chaque actu reçoit les
# MAX_TAGS_ACTU thèmes les plus présents, sinon TAG_DEFAUT.
MAX_TAGS_ACTU = 2
TAG_DEFAUT = "géopolitique"
TAG_RULES = {
    "marine": r"\bmarine nationale|\bla marine\b|naval|navire|fr[eé]gate|sous-marin|"
              r"porte-avions|flotte|amiral|escadre|corvette|destroyer|patrouilleur|"
              r"\bsnle\b|\bsna\b|d[eé]troit|maritime|\bzee\b|piraterie|\bnavy\b|"
              r"armateur|\bports?\b",
    "défense": r"arm[eé]es?\b|militaire|d[eé]fense|missile|munition|\bdrones?\b|chasseur|"
               r"rafale|\bf-35|blind[eé]|artillerie|\bopex\b|\botan\b|\bnato\b",
    "dissuasion": r"dissuasion|\bsnle\b|ogive|balistique|arme nucl[eé]aire|"
                  r"essai nucl[eé]aire",
    "industrie": r"industrie de d[eé]fense|\bbitd\b|naval group|thales|\bmbda\b|"
                 r"dassault|safran|\bknds\b|rheinmetall|contrat|commande|exportation",
    "Europe": r"\beurop[eé]|\bue\b|bruxelles|allemagne|royaume-uni|pologne|baltique|"
              r"balte|estonie|m[eé]diterran[eé]e",
    "Russie-Ukraine": r"russ|ukrain|kremlin|poutine|zelensky|mer noire|crim[eé]e|moscou",
    "Moyen-Orient": r"isra[eë]l|\biran|gaza|liban|syrie|y[eé]men|houthi|arabie|golfe|"
                    r"mer rouge|irak|turquie|\bturc|qatar|[eé]mirats",
    "Indo-Pacifique": r"chine|chinois|ta[iï]wan|japon|cor[eé]e|inde\b|indien|australie|"
                      r"philippines|pacifique|mer de chine|p[eé]kin|malaisie",
    "Afrique": r"afrique|africain|sahel|mali\b|niger\b|soudan|somalie|djibouti|congo|\brdc\b|"
               r"nig[eé]ria|[eé]thiopie|libye|alg[eé]rie|\balger\b|maroc|maurice",
    "Amériques": r"[eé]tats-unis|am[eé]ricain|washington|pentagone|maison blanche|trump|"
                 r"venezuela|br[eé]sil|canada|mexique|arctique|\bus navy\b",
    "cyber": r"cyber|piratage|ransomware|hacker|\banssi\b|d[eé]sinformation",
}

# Nom affiché pour les domaines connus (sinon le domaine tel quel).
SOURCES = {
    "lemonde.fr": "Le Monde",
    "rfi.fr": "RFI",
    "opex360.com": "Zone Militaire",
    "navalnews.com": "Naval News",
    "breakingdefense.com": "Breaking Defense",
    "defensenews.com": "Defense News",
    "twz.com": "The War Zone",
    "news.usni.org": "USNI News",
    "legrandcontinent.eu": "Le Grand Continent",
    "meretmarine.com": "Mer et Marine",
    "la1ere.franceinfo.fr": "La 1ère",
    "franceinfo.fr": "franceinfo",
    "france24.com": "France 24",
    "tf1info.fr": "TF1 Info",
    "lapresse.ca": "La Presse",
    "courrierinternational.com": "Courrier international",
    "warontherocks.com": "War on the Rocks",
    "defense.gouv.fr": "Ministère des Armées",
    "ifri.org": "IFRI",
    "iris-france.org": "IRIS",
    "frstrategie.org": "FRS",
    "understandingwar.org": "ISW",
    "crisisgroup.org": "Crisis Group",
    "diploweb.com": "Diploweb",
    "areion24.news": "Areion24",
    "asialyst.com": "Asialyst",
    "theconversation.com": "The Conversation",
    "lefigaro.fr": "Le Figaro",
    "reuters.com": "Reuters",
}
