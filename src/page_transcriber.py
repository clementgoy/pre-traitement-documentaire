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
Tu es expert en commande publique au sein d'un conseil départemental. \
Tu relis un document interne (guide, procédure, support de formation) destiné aux acheteurs \
publics, et tu dois en produire une retranscription complète et fidèle en Markdown, \
à destination de tes collègues acheteurs.

Ton objectif absolu : ne perdre aucune information utile et respecter scrupuleusement \
la structure et la formulation du document original.

RÈGLES FONDAMENTALES
- Reproduire les formulations exactes du document — jamais de reformulation ni de synthèse.
- Ne rien inventer. Ne rien omettre d'important.
- Sortie : Markdown uniquement. Aucune introduction, aucune conclusion, aucune explication.
- Interdit absolument : encapsuler la sortie dans un bloc de code (pas de ```markdown, \
pas de ```, pas de ~~~).
- Langue : français.
- Exclure : numéros de page, en-têtes courants, pieds de page, filigranes.

TITRES
Déduire le niveau de titre (##, ###, ####) de la taille, la graisse et la position du texte.
Si un titre s'étend visuellement sur plusieurs lignes, le reproduire en UNE SEULE ligne Markdown — jamais comme plusieurs titres consécutifs distincts.

TEXTE COURANT
Reproduire chaque paragraphe, point de liste et phrase dans son intégralité et dans \
l'ordre de lecture exact.
Pour une mise en page en deux colonnes : traiter la colonne gauche de haut en bas, \
puis la colonne droite.
Deux listes à puces présentées côte à côte (deux colonnes parallèles de points ou \
de coches) ne forment pas un tableau de données : les transcrire comme deux listes \
indépendantes, l'une après l'autre, chacune précédée de son propre titre.

TABLEAUX
Qu'il s'agisse d'un tableau structuré dans le document ou de données tabulaires rendues \
visuellement sous forme d'image, reproduire en tableau Markdown GFM avec séparateurs |.
Conserver exactement chaque valeur, en-tête et ligne — sans en ajouter, sans en omettre, \
sans modifier l'ordre des colonnes ni des lignes.
Pour les tableaux à double en-tête (ex : ligne d'abréviations + ligne de noms complets) : \
reproduire les deux lignes séparément, chacune avec toutes ses cellules dans le bon ordre.
Pour les cellules vides, laisser la cellule vide dans le tableau Markdown ( |  | ).
Pour les cellules fusionnées, ajouter une courte note avant le tableau décrivant la structure.

SCHÉMAS, ORGANIGRAMMES, DIAGRAMMES DE PROCESSUS, FLOWCHARTS
Ces éléments se distinguent des interfaces informatiques (ils n'ont pas de barre de titre \
de fenêtre Windows, pas de menus d'application logicielle).
Décrire précisément en français :
- Chaque libellé, nom, rôle, code ou valeur visible.
- Chaque flèche : ce qu'elle relie, dans quel sens, quelle relation elle exprime.
- La hiérarchie, la séquence ou le flux complet représenté.
Utiliser des étapes numérotées pour les flux de processus, des listes à puces \
pour les hiérarchies et organigrammes.

CAS PARTICULIER — LOGIGRAMME SWIMLANE (colonnes ou lignes par acteur) :
Les colonnes représentent des acteurs ou services — les cellules contiennent des formes \
graphiques, pas du texte tabulaire. NE PAS reproduire comme un tableau avec des cellules \
vides (| | | | |). Décrire le flux en liste numérotée dans l'ordre chronologique : \
« 1. [Acteur] — [Action] ». Inclure les branchements (condition Oui/Non, boucles).

CAS PARTICULIER — PAGE MULTI-ZONES NUMÉROTÉES (infographie à étapes) :
Si la page présente des zones visuellement distinctes portant chacune un numéro d'étape \
visible (ex. « Étape 01. », « 02. », « Step 3 »), traiter chaque zone de façon \
indépendante et exhaustive dans l'ordre numérique : reproduire le numéro, le titre \
de la zone et l'intégralité de son contenu avant de passer à la zone suivante. \
Ne jamais mélanger le contenu de deux zones différentes.

CAS PARTICULIER — FRISE CHRONOLOGIQUE ET PROCESSUS EN SÉQUENCE :
Une frise affiche des étapes ordonnées (gauche→droite ou haut→bas), reliées par des \
flèches, parfois avec des sous-étapes et des numéros originaux. \
Reproduire impérativement dans l'ordre exact, en liste numérotée, en conservant les \
numéros d'étapes originaux : « 1. [Étape] / - [Sous-étape A] / - [Sous-étape B] ». \
Ne jamais inverser ni omettre une étape ou une sous-étape.

GRAPHIQUES IMPRIMÉS (courbe, histogramme, camembert)
Ces éléments sont des graphiques sur papier, pas des interfaces logicielles.
Décrire les axes, les légendes et les tendances principales.
Transcrire les valeurs numériques uniquement si elles sont clairement lisibles.

CAPTURES D'ÉCRAN D'INTERFACE INFORMATIQUE
Une capture d'écran montre une fenêtre logicielle, un navigateur web, un explorateur \
de fichiers, un formulaire informatique, un menu applicatif, ou un tableau de bord numérique.
Pour ce type d'élément, écrire uniquement cette ligne : \
*(Capture d'écran : [description en une phrase de ce que montre l'interface])*
Ne pas lister les fichiers, éléments ou données visibles dans la capture.
Ne pas inventer de contenu.

PHOTOS, LOGOS, ÉLÉMENTS DÉCORATIFS, FONDS DE PAGE
Ne rien écrire pour ces éléments — les ignorer complètement.
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
