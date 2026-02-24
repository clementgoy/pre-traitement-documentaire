"""
Transcription intelligente d'une page complète en Markdown via un modèle de vision local.

Principe : la page entière est rendue sous forme d'image et envoyée au modèle
de vision. Celui-ci voit le contexte global de la page (mise en page, colonnes,
flèches, tableaux, hiérarchie visuelle) et produit un Markdown structuré fidèle.

C'est le seul moyen de traiter correctement :
- Les tableaux encodés comme blocs de texte positionnés (pas d'image)
- Les schémas de processus avec flèches (non capturables par extraction textuelle)
- Les organigrammes avec hiérarchie visuelle
- Les mises en page multi-colonnes complexes
"""

from PIL import Image

from .ollama_client import generate

# Résolution de rendu des pages PDF (dots per inch).
# 150 DPI : bonne lisibilité du texte dense après redimensionnement à 1024px.
RENDER_DPI = 150

TRANSCRIPTION_PROMPT = """\
Tu es expert en commande publique au sein d'un conseil départemental. \
Tu relis un document interne (guide, procédure, support de formation) destiné aux acheteurs \
publics, et tu dois en produire une retranscription complète et fidèle en Markdown, \
à destination de tes collègues acheteurs.

Ton objectif absolu : ne perdre aucune information utile. Tout ce qui est visible sur la \
page doit être restitué avec précision — textes, tableaux, schémas, données chiffrées. \
Ne rien inventer. Ne rien omettre d'important.

TITRES
Utilise ## pour les titres de section principaux, ### pour les sous-titres, #### pour les \
titres mineurs. Déduis le niveau de titre de la taille, la graisse et la position du texte.

TABLEAUX
Reproduis chaque tableau en tableau Markdown GFM (séparateurs |). \
Conserve exactement chaque valeur, en-tête de colonne et ligne. \
Pour les cellules fusionnées, ajoute une courte note avant le tableau décrivant la structure.

SCHÉMAS, ORGANIGRAMMES, PROCESSUS, DIAGRAMMES
Décris en français chaque élément visible avec précision :
- Tous les libellés, noms, rôles, codes et valeurs
- Chaque flèche : ce qu'elle relie, dans quel sens, quelle relation elle exprime
- La hiérarchie, la séquence ou le flux complet représenté
Utilise des étapes numérotées pour les flux de processus, des listes à puces pour les \
organigrammes ou hiérarchies.

IMAGES ET ILLUSTRATIONS
- Photos décoratives, logos, fonds de page, bordures → ignorer complètement, n'écrire rien
- Captures d'écran de logiciels, plateformes, sites web, interfaces, tableaux de bord → \
  une ligne courte :
  « *(Capture d'écran : [description de l'interface ou de la plateforme montrée])* »
  Ne jamais tenter de lire ou reproduire des chiffres, données ou textes depuis une capture \
  d'écran — ils peuvent être illisibles à cette résolution. Ne jamais inventer de valeurs.
- Exemples de documents montrés en illustration → une ligne courte par exemple :
  « *(Exemple illustratif : [type de document montré])* »
  Si DEUX exemples ou plus sont visibles, une ligne par exemple — ne pas en omettre.
- Graphiques imprimés (pas des captures d'écran) → décris axes, légendes et tendances \
  principales ; ne transcrire les valeurs que si elles sont clairement lisibles.

MISE EN PAGE
Pour les mises en page multi-colonnes : lire la colonne de gauche en entier (haut → bas), \
puis la colonne de droite.
Sinon : suivre l'ordre de lecture naturel (haut → bas, gauche → droite).

RÈGLES DE SORTIE
- Produire UNIQUEMENT le Markdown — pas d'introduction, pas de « Voici la retranscription : »
- Langue : français dans l'intégralité de la sortie
- Ne pas inclure les numéros de page, en-têtes courants, pieds de page, filigranes ou \
  éléments de navigation
- Ne jamais inventer ni ajouter d'information absente de la page
"""


# Taille max de l'image de page envoyée au modèle de vision (px, côté le plus long).
# 768px : bon compromis vitesse/qualité pour lire texte, tableaux et schémas.
# Réduire davantage (512) accélère encore mais peut perdre du texte fin.
PAGE_MAX_IMAGE_SIZE = 768

# Nombre max de tokens générés pour la transcription d'une page.
# 2048 évite la troncature silencieuse sur les pages denses (tableaux, listes longues).
PAGE_MAX_TOKENS = 2048


def transcribe_page(page_image: Image.Image, model: str) -> str:
    """
    Transcrit l'image d'une page en Markdown via le modèle de vision Ollama.

    Args:
        page_image : image PIL de la page (sera convertie en RGB si nécessaire)
        model      : nom du modèle Ollama (ex. 'qwen2.5vl:latest')

    Returns:
        Contenu Markdown transcrit par le modèle.
    """
    if page_image.mode not in ("RGB", "L"):
        page_image = page_image.convert("RGB")
    return generate(
        model,
        TRANSCRIPTION_PROMPT,
        image=page_image,
        max_image_size=PAGE_MAX_IMAGE_SIZE,
        max_tokens=PAGE_MAX_TOKENS,
    )
