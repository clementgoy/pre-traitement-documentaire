"""
Transcription intelligente de pages et d'images en Markdown via un modèle de vision local.

Deux fonctions principales :
  transcribe_page()  — envoi d'une page entière (mode vision pleine page).
                       Utilisé quand l'image EST le contenu : organigramme, schéma de
                       processus, diagramme. La mise en page globale porte l'information.

  describe_image()   — envoi d'une image isolée extraite d'une page (mode hybride).
                       Utilisé quand la page mélange texte extractible et images embarquées.
                       Le modèle ne voit que l'image, pas son contexte textuel.
"""

import re

from PIL import Image

from .ollama_client import generate

# Résolution de rendu des pages PDF (dots per inch).
# 150 DPI : bonne lisibilité du texte dense après redimensionnement à 1024px.
RENDER_DPI = 150

# ── Prompt pleine page ─────────────────────────────────────────────────────────

TRANSCRIPTION_PROMPT = """\
Tu es un outil de transcription. Tu reçois l'image d'une page de document. \
Tu produis uniquement le Markdown correspondant. Tu ne t'adresses jamais à l'utilisateur.

FIDÉLITÉ
Transcris uniquement ce qui est visuellement présent. Ne pas inventer, ne pas enrichir. \
Éléments illisibles → [illisible]. Sortie : Markdown brut, jamais dans un bloc de code.

IGNORER
Logos, photos décoratives, fonds de page, numéros de page isolés, \
en-têtes et pieds répétitifs identiques d'une page à l'autre, \
textes visuellement inclinés à 90° ou 270°.
Exception : un encadré ou bandeau coloré avec un contenu spécifique à la page \
est du contenu — le transcrire.

ANTI-RÉPÉTITION
Chaque zone est transcrite une seule fois, dans l'ordre gauche-droite puis haut-bas. \
Ne jamais répéter une zone déjà traitée. \
Si une répétition est détectée en cours de génération, s'arrêter et passer à l'élément suivant.

TITRES
Niveau (##, ###, ####) déduit de la taille et la graisse. Jamais de #. \
Un titre sur plusieurs lignes visuelles → une seule ligne Markdown.

TABLEAUX
GFM (| col | col |). Conserver chaque valeur, en-tête et cellule vide. \
Pas de ## dans les cellules — gras (**texte**) si mise en valeur nécessaire. \
Structure ambiguë → préférer une liste structurée.

SCHÉMAS, ORGANIGRAMMES, FLOWCHARTS
Décrire tous les libellés, flèches (sens + relation), légendes. \
Étapes numérotées pour les flux, listes à puces pour les hiérarchies. \
Logigramme avec plusieurs acteurs en colonnes ou zones séparées :
**Étape N — [titre]**
- [Acteur A] : [action]
- [Acteur B] : [action]
→ [sens de l'échange]
Transcrire uniquement les étapes visuellement présentes — pas d'étapes inventées.

CAPTURES D'ÉCRAN D'INTERFACE
(Capture d'écran : [description en une phrase])
Ne pas lister le contenu visible dans l'interface.
"""

# ── Prompt image isolée (mode hybride) ────────────────────────────────────────

IMAGE_DESCRIPTION_PROMPT = """\
Tu analyses une image extraite d'un document administratif de commande publique.
Réponds en français, sans introduction ni phrase d'explication préliminaire.
Identifie ce que montre l'image, puis applique la règle correspondante.

PRIORITÉ ABSOLUE — TABLEAU AVEC COCHES OU CROIX :
Si l'image montre un tableau comportant des symboles de validation (✔, ✓, ✖, ×, Oui, Non, \
coché, décoché) comparant des fonctionnalités ou permissions par ligne et par colonne : \
transcrire impérativement ce tableau en Markdown GFM (| col1 | col2 | ...). \
Reproduire chaque ligne, chaque en-tête et chaque symbole. Ne jamais résumer en une ligne.

--- TABLEAU DE DONNÉES ---
Grille structurée en lignes et colonnes (avec ou sans bordures visibles) présentant des \
données comparatives, chiffrées ou catégorisées. Ne pas confondre avec une interface logicielle.
Règle : retranscrire sous forme de tableau Markdown GFM avec séparateurs |.
Reproduire fidèlement chaque valeur, en-tête et ligne.

--- INTERFACE INFORMATIQUE ---
Capture d'écran d'une application en cours d'utilisation : fenêtre avec barre de menus, \
onglets de navigation, boutons cliquables, explorateur de fichiers, navigateur web.
EXCLUSION : un tableau de données statique (matrice de permissions, comparaison) n'est \
PAS une interface — appliquer la règle TABLEAU DE DONNÉES.
Règle : écrire exactement une ligne :
*(Capture d'écran : [ce que montre l'interface en une phrase])*
Ne pas lister les éléments visibles. Ne pas inventer de contenu.

--- SCHÉMA, ORGANIGRAMME, DIAGRAMME DE PROCESSUS, FLOWCHART ---
Représentation graphique d'une hiérarchie, d'un flux ou d'un processus — \
à distinguer des interfaces informatiques.
Règle : décrire tous les libellés visibles, toutes les flèches (sens + relation exprimée), \
toute la hiérarchie ou séquence complète.
Étapes numérotées pour les flux de processus. Listes à puces pour les arborescences.
Pour un logigramme swimlane (colonnes par acteur) : ne pas reproduire en tableau vide — \
décrire le flux en liste numérotée « 1. [Acteur] — [Action] ».

--- GRAPHIQUE (courbe, histogramme, camembert) ---
Règle : décrire les axes, les légendes et les tendances principales.

--- PHOTO, LOGO, ICÔNE, ÉLÉMENT DÉCORATIF ---
Règle : ne rien écrire — sortie vide.
"""

# ── Paramètres pleine page ─────────────────────────────────────────────────────

# Taille max de l'image envoyée au modèle en mode vision pleine page (px, côté le plus long).
# 1024 px améliore la lisibilité des tableaux complexes (grilles fines, cellules avec texte dense).
PAGE_MAX_IMAGE_SIZE = 1024

# Tokens max en mode vision pleine page.
# 3000 couvre les pages denses et les schémas complexes sans troncature silencieuse.
# Valeur augmentée depuis 2048 pour éviter les cases manquantes en fin de schéma.
PAGE_MAX_TOKENS = 3000

# ── Paramètres image isolée ────────────────────────────────────────────────────

# Taille max de l'image en mode hybride (image individuelle extraite d'une page).
# 512 px est suffisant pour identifier le type d'image et décrire un schéma.
# L'encodage est ~2x plus rapide qu'à 768 px.
IMAGE_MAX_SIZE = 512

# Tokens max pour la description d'une image isolée.
# 800 couvre une description détaillée d'organigramme sans excès.
IMAGE_MAX_TOKENS = 800


_EMPTY_TABLE_ROW_RE = re.compile(r"^\s*\|(\s*\|)+\s*$")

# Cellule de tableau contenant uniquement des tirets répétés (≥ 5) : artefact de génération.
# Ex. : "| Clause contractuelle | ------------------------------ |"
# Remplacer le contenu de la cellule par vide.
_DASH_ONLY_CELL_RE = re.compile(r"(?<=\|)\s*-{5,}\s*(?=\|)")


def _remove_repeated_empty_rows(text: str) -> str:
    """
    Supprime les séquences de lignes de tableau vides répétées.

    Symptôme caractéristique d'un logigramme swimlane mal transcrit :
    le modèle génère l'en-tête de tableau (colonnes = acteurs/services) puis
    des dizaines de lignes « | | | | | » correspondant aux formes graphiques
    qu'il ne peut pas lire.

    Règle : si ≥ 3 lignes consécutives sont vides (uniquement | et espaces),
    on conserve les 2 premières (en-tête + séparateur légitimes) et on remplace
    la suite par une note indiquant que le contenu est un schéma non transcriptible.
    """
    lines = text.split("\n")
    result: list[str] = []
    empty_run: list[str] = []

    def flush_run() -> None:
        if not empty_run:
            return
        if len(empty_run) <= 2:
            result.extend(empty_run)
        else:
            result.extend(empty_run[:2])
            result.append(
                "\n> *(Logigramme ou diagramme complexe — "
                "contenu graphique non transcriptible en tableau)*\n"
            )
        empty_run.clear()

    for line in lines:
        if _EMPTY_TABLE_ROW_RE.match(line):
            empty_run.append(line)
        else:
            flush_run()
            result.append(line)

    flush_run()
    return "\n".join(result)


def _clean_dash_cells(text: str) -> str:
    """
    Nettoie les cellules de tableau contenant uniquement des tirets répétés (artefact).

    Symptôme : le modèle remplit une cellule avec une longue chaîne de tirets
    (ex. « ------------------------------ ») lorsqu'il ne peut pas lire le contenu
    d'une cellule fusionnée ou d'une structure trop complexe.

    Règle : si une cellule contient ≥ 5 tirets consécutifs et rien d'autre,
    son contenu est remplacé par une cellule vide.
    """
    return _DASH_ONLY_CELL_RE.sub("  ", text)


def _strip_code_block(text: str) -> str:
    """
    Supprime les délimiteurs ```markdown...``` ou ```...``` si le modèle
    a encapsulé sa sortie dans un bloc de code malgré l'instruction.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.split("\n")
    # Supprimer la première ligne (``` ou ```markdown ou ```md...)
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    # Supprimer la dernière ligne si c'est ```
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


_PROMPT_ECHO_FRAGMENTS = (
    "PHOTO, LOGO",
    "ÉLÉMENT DÉCORATIF",
    "INTERFACE INFORMATIQUE",
    "TABLEAU DE DONNÉES",
    "SCHÉMA, ORGANIGRAMME",
    "GRAPHIQUE (courbe",
    "PRIORITÉ ABSOLUE",
    "TABLEAU AVEC COCHES",
)


def _is_prompt_echo(text: str) -> bool:
    """
    Détecte si le modèle a retourné un label de section du prompt
    au lieu du contenu attendu (ex. '* PHOTO, LOGO, ICÔNE, ÉLÉMENT DÉCORATIF :').
    Dans ce cas, la description doit être ignorée (retourner chaîne vide).
    """
    upper = text.strip().upper()
    return any(fragment in upper for fragment in _PROMPT_ECHO_FRAGMENTS)


def _normalize_screenshot_format(text: str) -> str:
    """
    Normalise le format *(Capture d'écran : ...)* si le modèle l'a mal formaté.

    Le modèle produit parfois :
      *Capture d'écran : text*          (sans parenthèses)
      Capture d'écran : text.           (sans mise en forme du tout)
    au lieu de :
      *(Capture d'écran : text)*        (forme correcte attendue)
    """
    stripped = text.strip()
    # Format déjà correct
    if stripped.startswith("*(Capture d'écran"):
        return text
    # Étoiles mais sans parenthèses : *Capture d'écran : text*
    if stripped.startswith("*Capture d'écran"):
        inner = stripped.strip("*").strip()
        inner = re.sub(r"\.$", "", inner)
        return f"*({inner})*"
    # Aucune mise en forme : Capture d'écran : text.
    if stripped.lower().startswith("capture d'écran"):
        inner = re.sub(r"\.$", "", stripped)
        return f"*({inner})*"
    return text


def transcribe_page(
    page_image: Image.Image,
    model: str,
    max_image_size: int = PAGE_MAX_IMAGE_SIZE,
) -> str:
    """
    Transcrit l'image d'une page entière en Markdown via le modèle de vision.

    Utilisé pour les pages dont la mise en page visuelle porte l'information :
    organigrammes, schémas de processus, flowcharts, pages denses fragmentées.

    Args:
        page_image     : image PIL de la page
        model          : nom du modèle Ollama (ex. 'qwen2.5vl:latest')
        max_image_size : taille max (px) avant redimensionnement.
                         Passer IMAGE_MAX_SIZE (512) en retry pour réduire le temps d'encodage.
    """
    if page_image.mode not in ("RGB", "L"):
        page_image = page_image.convert("RGB")
    result = generate(
        model,
        TRANSCRIPTION_PROMPT,
        image=page_image,
        max_image_size=max_image_size,
        max_tokens=PAGE_MAX_TOKENS,
    )
    result = _strip_code_block(result)
    result = _clean_dash_cells(result)
    return _remove_repeated_empty_rows(result)


def describe_image(image: Image.Image, model: str) -> str:
    """
    Décrit une image individuelle extraite d'une page (mode hybride).

    Prompt plus court et plus strict que TRANSCRIPTION_PROMPT :
    - Interface informatique → une ligne
    - Tableau de données → tableau Markdown GFM
    - Schéma/organigramme → description complète
    Le modèle ne voit que l'image isolée, sans son contexte textuel.

    Args:
        image : image PIL de l'image extraite (sera convertie en RGB si nécessaire)
        model : nom du modèle Ollama
    """
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    result = generate(
        model,
        IMAGE_DESCRIPTION_PROMPT,
        image=image,
        max_image_size=IMAGE_MAX_SIZE,
        max_tokens=IMAGE_MAX_TOKENS,
    )
    result = _strip_code_block(result)
    if _is_prompt_echo(result):
        return ""
    return _normalize_screenshot_format(result)
