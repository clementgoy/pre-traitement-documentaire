"""
Conversion de fichiers PDF en Markdown.

Trois modes de traitement par page (choix automatique) :

  « texte »   — Extraction rapide via PyMuPDF.
                Pages simples : peu de blocs, pas de tableau, pas d'image.

  « tableau » — PyMuPDF find_tables() + blocs texte hors tableaux.
                Pages dont la complexité vient uniquement de tableaux détectables
                structurellement (pas de schéma). Aucun appel au modèle.

  « vision »  — Rendu de la page en image → modèle de vision → Markdown.
                Pages complexes : schémas, organigrammes, mises en page
                fragmentées, images significatives. Méthode la plus fidèle.

Mode --no-images : force « texte » pour toutes les pages (pas de modèle).
"""

import re
from collections import Counter
from io import BytesIO

import fitz  # PyMuPDF
from PIL import Image

from .page_transcriber import RENDER_DPI, transcribe_page

# ── Seuils du classificateur de complexité ────────────────────────────────────

# Au-delà de ce nombre de blocs texte, la page est complexe → vision obligatoire
_VISION_BLOCK_THRESHOLD = 20

# En dessous de ce nombre de blocs, une page sans image ni spread est traitée en mode texte.
# Seuil bas exprès : seules les pages véritablement triviales (page de garde, intro courte)
# passent en texte. Tout le reste va en vision pour éviter les incohérences de retranscription.
_TEXT_MODE_MAX_BLOCKS = 6

# Nombre de blocs max pour accepter la méthode « tableau » (find_tables).
# En dessous : peu de blocs hors tableaux → extraction structurelle fiable.
# Au-dessus : trop de blocs épars (schémas, formes) → préférer la vision.
_TABLE_BLOCK_THRESHOLD = 25

# Taille minimale (px) d'une image pour la considérer significative (pas une icône)
_SIGNIFICANT_IMAGE_SIZE = 100

# Seuils pour la détection de mises en page complexes par dispersion horizontale.
# Si >= _MIN_BLOCKS_FOR_SPREAD_CHECK blocs et x-spread > _X_SPREAD_THRESHOLD * page_width
# sans structure en colonnes claire → vision (hub-spoke, formes positionnées librement…)
_MIN_BLOCKS_FOR_SPREAD_CHECK = 10
_X_SPREAD_THRESHOLD = 0.35

# ── Mode texte : détection des titres par taille de police ────────────────────

HEADING_THRESHOLDS = [
    (1.8, 1),
    (1.4, 2),
    (1.15, 3),
    (1.05, 4),
]

# Longueur maximale d'un texte gras pour le considérer comme titre H4.
# Valeur conservative : les phrases longues en gras sont du corps de texte, pas des titres.
MAX_BOLD_HEADING_LEN = 60
ROW_TOLERANCE_PT = 10
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


# ── Helpers mode texte ────────────────────────────────────────────────────────

def _detect_body_size(doc: fitz.Document) -> float:
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
    ratio = font_size / body_size
    for threshold, level in HEADING_THRESHOLDS:
        if ratio >= threshold:
            return level
    return 0


def _block_to_markdown(block: dict, body_size: float) -> str:
    full_text = ""
    sizes: list[float] = []
    bold_chars = 0
    total_chars = 0
    num_lines_non_empty = 0

    for line in block["lines"]:
        line_text = ""
        for span in line["spans"]:
            line_text += span["text"]
            text_stripped = span["text"].strip()
            if text_stripped:
                sizes.append(span["size"])
                char_count = len(text_stripped)
                total_chars += char_count
                if span["flags"] & (1 << 4):
                    bold_chars += char_count
        if line_text.strip():
            num_lines_non_empty += 1
        full_text += line_text + "\n"

    full_text = full_text.strip()
    if not full_text or _PAGE_NUMBER_RE.match(full_text):
        return ""

    level = 0
    if sizes:
        avg_size = sum(sizes) / len(sizes)
        level = _heading_level(avg_size, body_size)

    # Titre H4 par gras : critères stricts pour éviter les faux positifs.
    # Requis : majorité du texte en gras, une seule ligne, court, pas de ponctuation de fin de phrase.
    if level == 0 and bold_chars > 0:
        bold_ratio = bold_chars / total_chars if total_chars > 0 else 0
        ends_with_sentence_punct = bool(full_text) and full_text[-1] in ".,:;?!"
        if (
            bold_ratio >= 0.65
            and num_lines_non_empty == 1
            and len(full_text) <= MAX_BOLD_HEADING_LEN
            and not ends_with_sentence_punct
        ):
            level = 4

    if level > 0:
        return f"\n{'#' * level} {full_text}\n"
    return f"\n{full_text}\n"


# ── Détection de mise en page multi-colonnes ──────────────────────────────────

def _is_diagram_layout(text_blocks: list, page_width: float) -> bool:
    """
    Détecte si les blocs forment un schéma visuel (boîtes courtes, organigramme, hub-spoke)
    plutôt qu'un texte en colonnes classique.

    Signal : texte moyen très court dans les blocs étroits.
    Des colonnes de prose ont des paragraphes longs ; des boîtes de diagramme ont
    des étiquettes courtes (rôles, noms, actions brèves).

    Seuil : longueur moyenne < 50 caractères par bloc étroit.
    """
    narrow = [
        b for b in text_blocks
        if (b["bbox"][2] - b["bbox"][0]) < page_width * 0.6
    ]
    if len(narrow) < 4:
        return False

    total_chars = 0
    for b in narrow:
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                total_chars += len(span.get("text", "").strip())

    avg_chars = total_chars / len(narrow)
    return avg_chars < 50


def _detect_column_split(text_blocks: list, page_width: float) -> float | None:
    """
    Détecte une séparation verticale (axe x) entre deux colonnes de texte.

    Ignore les blocs « pleine largeur » (largeur > 60 % de la page) qui sont
    généralement des titres ou pieds de page.

    Retourne la coordonnée x du centre du gap si un split clair est détecté
    (gap ≥ 15 % de la largeur de page, dans la zone centrale 20 %–80 %,
    avec au moins 2 blocs de chaque côté), None sinon.
    """
    narrow = [
        b for b in text_blocks
        if (b["bbox"][2] - b["bbox"][0]) < page_width * 0.6
    ]
    if len(narrow) < 4:
        return None

    x0s = sorted(b["bbox"][0] for b in narrow)

    best_gap = 0.0
    best_split: float | None = None

    for i in range(len(x0s) - 1):
        gap = x0s[i + 1] - x0s[i]
        split = (x0s[i] + x0s[i + 1]) / 2.0
        # Le gap doit être dans la zone centrale de la page (20 %–80 %)
        if page_width * 0.2 <= split <= page_width * 0.8:
            left_count = sum(1 for b in narrow if b["bbox"][0] <= x0s[i])
            right_count = sum(1 for b in narrow if b["bbox"][0] >= x0s[i + 1])
            if gap > best_gap and left_count >= 2 and right_count >= 2:
                best_gap = gap
                best_split = split

    if best_split is not None and best_gap >= page_width * 0.15:
        return best_split
    return None


def _page_to_text_markdown(page: fitz.Page, body_size: float) -> str:
    """Extraction texte avec tri adaptatif : colonnes détectées ou ordre naturel."""
    blocks = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b["type"] == 0]
    page_width = page.rect.width

    split_x = _detect_column_split(text_blocks, page_width)

    if split_x is not None:
        # Mise en page à deux colonnes :
        # 1. Blocs plein-largeur (titres, en-têtes) triés par y
        # 2. Colonne gauche triée par y
        # 3. Colonne droite triée par y
        wide_threshold = page_width * 0.6
        wide = sorted(
            [b for b in text_blocks if (b["bbox"][2] - b["bbox"][0]) >= wide_threshold],
            key=lambda b: b["bbox"][1],
        )
        left = sorted(
            [b for b in text_blocks
             if (b["bbox"][2] - b["bbox"][0]) < wide_threshold and b["bbox"][0] < split_x],
            key=lambda b: b["bbox"][1],
        )
        right = sorted(
            [b for b in text_blocks
             if (b["bbox"][2] - b["bbox"][0]) < wide_threshold and b["bbox"][0] >= split_x],
            key=lambda b: b["bbox"][1],
        )
        sorted_blocks = wide + left + right
    else:
        sorted_blocks = sorted(
            text_blocks,
            key=lambda b: (round(b["bbox"][1] / ROW_TOLERANCE_PT), b["bbox"][0]),
        )

    parts = []
    for block in sorted_blocks:
        md = _block_to_markdown(block, body_size)
        if md:
            parts.append(md)
    return "".join(parts)


# ── Helpers mode tableau ───────────────────────────────────────────────────────

def _table_to_gfm(table) -> str:
    """
    Convertit une table PyMuPDF (find_tables) en tableau GFM Markdown.
    Retourne une chaîne vide si la table est vide ou invalide.
    """
    try:
        data = table.extract()  # list[list[str | None]]
    except Exception:
        return ""

    if not data:
        return ""

    col_count = max((len(row) for row in data), default=0)
    if col_count == 0:
        return ""

    # Normalise les cellules : None → "", sauts de ligne → espace
    rows = [
        [(cell or "").replace("\n", " ").strip() for cell in row]
        + [""] * (col_count - len(row))
        for row in data
    ]

    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join(["---"] * col_count) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows[1:])

    return f"\n{header}\n{separator}\n{body}\n"


def _page_to_table_markdown(page: fitz.Page, body_size: float) -> str:
    """
    Extraction par tables (find_tables) + blocs texte hors zones de tableau.

    Combine :
    - Les tableaux détectés par PyMuPDF → formatés en GFM
    - Les blocs texte dont le centre vertical est hors de toute zone de tableau
    Le tout est trié par position verticale pour respecter l'ordre de lecture.
    """
    table_finder = page.find_tables()
    tables = table_finder.tables

    # Bandes verticales occupées par les tableaux (y0, y1)
    table_y_bands = [(t.bbox[1], t.bbox[3]) for t in tables]

    # Tableaux → Markdown avec leur position y0
    items: list[tuple[float, str]] = []
    for table in tables:
        gfm = _table_to_gfm(table)
        if gfm:
            items.append((table.bbox[1], gfm))

    # Blocs texte hors tableaux → Markdown avec leur position y0
    blocks = page.get_text("dict")["blocks"]
    for block in blocks:
        if block["type"] != 0:
            continue
        y_center = (block["bbox"][1] + block["bbox"][3]) / 2
        # Exclure si le centre du bloc est dans une zone de tableau
        in_table = any(y0 - 5 <= y_center <= y1 + 5 for y0, y1 in table_y_bands)
        if in_table:
            continue
        md = _block_to_markdown(block, body_size)
        if md:
            items.append((block["bbox"][1], md))

    items.sort(key=lambda x: x[0])
    return "".join(content for _, content in items)


# ── Classificateur de complexité ──────────────────────────────────────────────

def _has_meaningful_tables(tables: list) -> bool:
    """
    Vérifie qu'au moins une table détectée contient de vraies données
    (pas un simple bandeau header/footer ou un artefact de navigation).

    Critère : au moins 2 lignes non vides ET au moins 2 colonnes.
    """
    for table in tables:
        try:
            data = table.extract()
            if not data:
                continue
            col_count = max((len(row) for row in data), default=0)
            data_rows = [
                row for row in data
                if any((cell or "").strip() for cell in row)
            ]
            if len(data_rows) >= 2 and col_count >= 2:
                return True
        except Exception:
            continue
    return False


def _classify_page(page: fitz.Page) -> str:
    """
    Analyse rapide (sans LLM) pour choisir le mode de traitement d'une page.

    Retourne :
      'text'   — extraction texte PyMuPDF (page simple ou sans vrai tableau)
      'table'  — find_tables() + texte (tableaux de données réels, layout simple)
      'vision' — rendu image + modèle de vision (page complexe)
    """
    blocks = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b["type"] == 0]
    img_blocks = [b for b in blocks if b["type"] == 1]

    # Image significative → vision obligatoire (schéma, photo, graphique)
    for b in img_blocks:
        w = b["bbox"][2] - b["bbox"][0]
        h = b["bbox"][3] - b["bbox"][1]
        if w > _SIGNIFICANT_IMAGE_SIZE and h > _SIGNIFICANT_IMAGE_SIZE:
            return "vision"

    # Trop de blocs = mise en page fragmentée (schéma, formulaire multi-zones)
    if len(text_blocks) > _VISION_BLOCK_THRESHOLD:
        return "vision"

    # Dispersion horizontale sans structure en colonnes claire → mise en page complexe
    # (hub-spoke, blocs positionnés librement, multi-zones non rectilignes)
    if len(text_blocks) >= _MIN_BLOCKS_FOR_SPREAD_CHECK:
        page_width = page.rect.width
        x0_values = [b["bbox"][0] for b in text_blocks]
        x_spread = max(x0_values) - min(x0_values) if x0_values else 0
        if x_spread > page_width * _X_SPREAD_THRESHOLD:
            split_x = _detect_column_split(text_blocks, page_width)
            if split_x is None:
                # Pas de structure en colonnes claire → layout complexe
                return "vision"
            elif _is_diagram_layout(text_blocks, page_width):
                # Colonnes apparentes mais texte trop court → boîtes de schéma, pas de prose
                return "vision"

    # Détection des tableaux
    try:
        tables = page.find_tables().tables
    except Exception:
        tables = []

    if tables and _has_meaningful_tables(tables):
        if len(text_blocks) <= _TABLE_BLOCK_THRESHOLD:
            return "table"
        else:
            # Tableaux réels + beaucoup de blocs → schéma mêlé à des tableaux
            return "vision"

    # Mode texte uniquement pour les pages véritablement simples :
    # peu de blocs, pas de dispersion horizontale notable.
    # Au-delà du seuil, préférer vision pour éviter les incohérences de retranscription.
    if len(text_blocks) <= _TEXT_MODE_MAX_BLOCKS:
        return "text"

    return "vision"


# ── Rendu page ────────────────────────────────────────────────────────────────

def _render_page(page: fitz.Page) -> Image.Image:
    """Rend une page PDF en image PIL à RENDER_DPI."""
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


# ── Point d'entrée principal ──────────────────────────────────────────────────

def parse_pdf(
    file_path: str,
    vision_model: str,
    analyze_images: bool = True,
    verbose: bool = True,
) -> str:
    """
    Parse un PDF et retourne son contenu en Markdown.

    Avec vision : classificateur automatique par page (texte / tableau / vision).
    Sans vision  : extraction texte PyMuPDF pour toutes les pages (--no-images).

    Chaque page est séparée par une ligne `---`.
    """
    doc = fitz.open(file_path)
    body_size = _detect_body_size(doc)

    if verbose:
        mode_label = f"vision ({vision_model})" if analyze_images else "texte uniquement"
        print(f"  Mode            : {mode_label}")
        print(f"  Nombre de pages : {len(doc)}")

    page_sections: list[str] = []

    # Compteurs pour le résumé final
    counts = {"text": 0, "table": 0, "vision": 0}

    for page_num, page in enumerate(doc):
        if verbose:
            print(f"  Page {page_num + 1:3d}/{len(doc)} ...", end=" ", flush=True)

        try:
            if not analyze_images:
                mode = "text"
            else:
                mode = _classify_page(page)

            counts[mode] += 1

            if mode == "vision":
                img = _render_page(page)
                md = transcribe_page(img, vision_model)
                tag = "[vision]"
            elif mode == "table":
                md = _page_to_table_markdown(page, body_size)
                tag = "[tableau]"
            else:
                md = _page_to_text_markdown(page, body_size)
                tag = "[texte] "

        except Exception as e:
            if verbose:
                print(f"erreur — {e}")
            continue

        md = md.strip()
        if md:
            page_sections.append(md)

        if verbose:
            print(tag)

    if verbose and analyze_images:
        total = sum(counts.values())
        print(
            f"\n  ── Bilan traitement ──────────────────────────────\n"
            f"  Vision  : {counts['vision']:3d} page(s)  "
            f"  Tableau : {counts['table']:3d} page(s)  "
            f"  Texte   : {counts['text']:3d} page(s)\n"
            f"  Appels modèle évités : {counts['table'] + counts['text']}/{total}"
        )

    doc.close()
    return "\n\n---\n\n".join(page_sections)
