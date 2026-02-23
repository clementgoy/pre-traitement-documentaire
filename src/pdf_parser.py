"""
Conversion de fichiers PDF en Markdown.

Deux modes de fonctionnement :

- Avec vision (défaut) :
    Chaque page est rendue en image (150 DPI) et envoyée au modèle de vision
    qui produit un Markdown structuré en voyant le contexte global de la page.
    Cela permet de traiter correctement les tableaux, schémas avec flèches,
    organigrammes et mises en page multi-colonnes complexes.

- Sans vision (--no-images) :
    Extraction rapide du texte via PyMuPDF, sans appel au modèle.
    Utile pour les tests rapides ou les documents purement textuels.
    Les blocs sont triés par ordre de lecture visuel (haut→bas, gauche→droite).
"""

import re
from collections import Counter
from io import BytesIO

import fitz  # PyMuPDF
from PIL import Image

from .page_transcriber import RENDER_DPI, transcribe_page

# ── Mode texte (--no-images) : détection des titres par taille de police ──────

HEADING_THRESHOLDS = [
    (1.8, 1),
    (1.4, 2),
    (1.15, 3),
    (1.05, 4),
]

MAX_BOLD_HEADING_LEN = 120

# Tolérance verticale (pts) pour regrouper les blocs sur la même "ligne" visuelle
ROW_TOLERANCE_PT = 10

# Filtre les blocs qui ne contiennent qu'un numéro de page (1-4 chiffres)
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


def _detect_body_size(doc: fitz.Document) -> float:
    """Détecte la taille de police dominante (= corps du texte)."""
    sizes: list[int] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes.append(round(span["size"]))
    if not sizes:
        return 11.0
    return float(Counter(sizes).most_common(1)[0][0])


def _heading_level(font_size: float, body_size: float) -> int:
    """Retourne le niveau de titre (1-4) ou 0 si corps du texte."""
    ratio = font_size / body_size
    for threshold, level in HEADING_THRESHOLDS:
        if ratio >= threshold:
            return level
    return 0


def _block_to_markdown(block: dict, body_size: float) -> str:
    """Convertit un bloc de texte PyMuPDF en ligne Markdown."""
    full_text = ""
    sizes: list[float] = []
    is_bold = False

    for line in block["lines"]:
        line_text = ""
        for span in line["spans"]:
            line_text += span["text"]
            if span["text"].strip():
                sizes.append(span["size"])
                if span["flags"] & (1 << 4):  # bit 4 = gras
                    is_bold = True
        full_text += line_text + "\n"

    full_text = full_text.strip()
    if not full_text:
        return ""

    if _PAGE_NUMBER_RE.match(full_text):
        return ""

    level = 0
    if sizes:
        avg_size = sum(sizes) / len(sizes)
        level = _heading_level(avg_size, body_size)

    if level == 0 and is_bold and len(full_text) <= MAX_BOLD_HEADING_LEN:
        level = 4

    if level > 0:
        return f"\n{'#' * level} {full_text}\n"
    return f"\n{full_text}\n"


def _page_to_text_markdown(page: fitz.Page, body_size: float) -> str:
    """
    Extrait le texte d'une page en Markdown (mode --no-images, sans vision).
    Les blocs sont triés par ordre de lecture visuel.
    """
    blocks = sorted(
        page.get_text("dict")["blocks"],
        key=lambda b: (round(b["bbox"][1] / ROW_TOLERANCE_PT), b["bbox"][0]),
    )
    parts = []
    for block in blocks:
        if block["type"] == 0:
            md = _block_to_markdown(block, body_size)
            if md:
                parts.append(md)
    return "".join(parts)


def _render_page(page: fitz.Page) -> Image.Image:
    """Rend une page PDF en image PIL à RENDER_DPI."""
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def parse_pdf(
    file_path: str,
    vision_model: str,
    analyze_images: bool = True,
    verbose: bool = True,
) -> str:
    """
    Parse un PDF et retourne son contenu en Markdown.

    Avec vision : rendu visuel de chaque page → modèle de vision → Markdown structuré.
    Sans vision  : extraction rapide du texte via PyMuPDF (--no-images).

    Chaque page est séparée par une ligne `---`.
    """
    doc = fitz.open(file_path)

    body_size = None
    if not analyze_images:
        body_size = _detect_body_size(doc)

    if verbose:
        mode = f"vision ({vision_model})" if analyze_images else "texte uniquement"
        print(f"  Mode            : {mode}")
        print(f"  Nombre de pages : {len(doc)}")

    page_sections: list[str] = []

    for page_num, page in enumerate(doc):
        if verbose:
            print(f"  Page {page_num + 1}/{len(doc)} ...", end=" ", flush=True)

        try:
            if analyze_images:
                img = _render_page(page)
                md = transcribe_page(img, vision_model)
            else:
                md = _page_to_text_markdown(page, body_size)
        except Exception as e:
            if verbose:
                print(f"erreur — {e}")
            continue

        md = md.strip()
        if md:
            page_sections.append(md)

        if verbose:
            print("ok")

    doc.close()
    return "\n\n---\n\n".join(page_sections)
