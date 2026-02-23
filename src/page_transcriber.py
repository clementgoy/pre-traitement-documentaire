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
You are transcribing a page from a professional French public administration document \
into well-structured Markdown. The document relates to public procurement (commande publique).

Produce a FAITHFUL and COMPLETE transcription that preserves ALL information on the page. \
Follow these rules:

HEADINGS
Use ## for main section headings, ### for sub-headings, #### for minor headings.
Infer heading levels from visual prominence (font size, bold weight, position on page).

TABLES
Reproduce every table as a GFM Markdown table using | separators.
Preserve every cell value, column header, and row exactly as written.
For tables with merged cells, add a brief note before the table describing the structure.

DIAGRAMS, FLOWCHARTS, PROCESS SCHEMAS, ORG CHARTS
Write a detailed French description capturing every visible element:
- All labels, names, roles, codes, and values
- Every arrow: what it connects, in which direction, and what relationship it expresses
- The full hierarchy, sequence, or workflow they represent
Use numbered steps for process flows, bullet lists for org charts or hierarchies.

IMAGES AND ILLUSTRATIONS
- Decorative photos, logos, background imagery, page borders → skip entirely, write nothing
- Document examples or screenshots used as illustrations → write one brief line per item:
  "*(Exemple illustratif : [type de document montré])*"
  If TWO OR MORE such examples are visible, add one line per example — do not skip any
- Data charts or graphs → describe the data, axes, labels, and key values shown

LAYOUT
For multi-column layouts: read left column fully (top to bottom), then right column.
Otherwise follow the natural reading order (top to bottom, left to right).

OUTPUT RULES
- Output ONLY the Markdown — no preamble, no "Here is the transcription:", no commentary
- Language: French throughout (the source document is in French)
- Do NOT include page numbers, running headers, footers, watermarks, or navigation elements
- Do NOT invent or add information not visible on the page
"""


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
    return generate(model, TRANSCRIPTION_PROMPT, image=page_image)
