"""
Conversion de fichiers PDF en Markdown.

Quatre modes de traitement par page (choix automatique) :

  « texte »   — Extraction rapide via PyMuPDF.
                Pages simples : peu de blocs, pas de tableau, pas d'image.

  « tableau » — PyMuPDF find_tables() + blocs texte hors tableaux.
                Pages dont la complexité vient uniquement de tableaux détectables
                structurellement (pas de schéma). Aucun appel au modèle.

  « hybride » — Texte extrait par PyMuPDF + images décrites individuellement.
                Pages mixant du texte extractible et des images secondaires
                (captures d'écran, icônes). Élimine les hallucinations sur les
                interfaces logicielles tout en reproduisant le texte fidèlement.

  « vision »  — Rendu de la page en image → modèle de vision → Markdown.
                Pages complexes : schémas, organigrammes, mises en page
                fragmentées, images significatives. Méthode la plus fidèle.

Mode --no-images : force « texte » pour toutes les pages (pas de modèle).
"""

import re
from collections import Counter
from io import BytesIO

import fitz  # PyMuPDF
import requests
from PIL import Image

from .page_transcriber import PAGE_MAX_IMAGE_SIZE, RENDER_DPI, describe_image, transcribe_page

# Résolution de repli en cas de timeout sur une page vision (pleine page).
# 512 px réduit la surface de l'image d'environ 55 % par rapport à 768 px.
_RETRY_IMAGE_SIZE = 512

# Résolution haute définition pour les pages à forte densité visuelle.
# Déclenchée quand img_blocks >= 3 ET (paysage ≥ 1.2× OU img_blocks >= 5).
# Cible : organigrammes larges, logigrammes multi-colonnes, pages paysage.
# Ne modifie pas le seuil de retry (_RETRY_IMAGE_SIZE reste à 512 px).
_HIGH_RES_IMAGE_SIZE = 1536

# Nombre minimum de blocs texte sur une page pour activer le mode hybride.
# Si une page contient des images significatives ET >= ce seuil de blocs texte,
# on extrait le texte via PyMuPDF et on décrit les images individuellement.
# Seuil bas (2) pour activer le mode hybride dès qu'il y a du texte extractible.
# Un organigramme pleine page a généralement 0-1 blocs texte en dehors de l'image
# → reste en vision. Une page avec texte d'instructions + capture d'écran a 2+ blocs
# → passe en hybride, ce qui élimine les hallucinations sur les captures.
_HYBRID_TEXT_THRESHOLD = 2

# Nombre minimum d'images significatives pour qu'une page avec des blocs texte courts
# soit routée en mode vision (au lieu d'hybride).
# Un vrai diagramme multi-éléments (flowchart) a généralement ≥ 4 petites images
# (flèches, connecteurs, boîtes graphiques séparées).
# Une page "instructions + capture d'écran" a 1–3 images → reste en hybride.
_DIAGRAM_MIN_IMAGES = 4

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
    word_count = len(full_text.split())

    # Critères pour la détection de titre par taille de police :
    # – Le bloc doit être court (≤ 8 mots) : au-delà, c'est du corps de texte
    #   même si la police est légèrement différente de la taille de référence.
    # – Le texte ne doit pas finir par un signe de ponctuation de phrase (".", ",", ":", ";").
    # – Les symboles de puce seuls (▪, •, →, —…) ne sont jamais des titres.
    # – Les blocs multi-lignes (fragments de phrase coupée à l'affichage) ne sont pas des titres.
    ends_with_sentence_punct = bool(full_text) and full_text[-1] in ".,:;"
    is_bullet_symbol = len(full_text.strip()) <= 2 and not full_text.strip().isalnum()
    has_internal_newlines = "\n" in full_text
    # Un titre commence toujours par une majuscule : un fragment de phrase
    # débutant en minuscule (ex : "votre profil en page") n'est pas un titre.
    starts_with_lowercase = bool(full_text.strip()) and full_text.strip()[0].islower()
    if (
        sizes
        and word_count <= 8
        and not ends_with_sentence_punct
        and not is_bullet_symbol
        and not has_internal_newlines
        and not starts_with_lowercase
    ):
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


def _tables_have_complex_headers(tables: list) -> bool:
    """
    Détecte si des tableaux ont des en-têtes complexes (double-en-tête, cellules fusionnées,
    sous-en-têtes avec noms longs).

    Signal : la deuxième ligne non vide a la plupart de ses cellules avec du texte long
    (> 25 caractères). Cela indique une ligne de sous-en-têtes (ex. abréviations + noms
    complets d'organisations), structure que find_tables() gère mal.

    Dans ce cas, préférer le mode vision pour que le modèle voie la structure visuelle.
    """
    for table in tables:
        try:
            data = table.extract()
            if not data or len(data) < 3:
                continue
            col_count = max((len(row) for row in data), default=0)
            if col_count < 2:
                continue
            data_rows = [
                row for row in data
                if any((cell or "").strip() for cell in row)
            ]
            if len(data_rows) < 3:
                continue
            # Vérifier la deuxième ligne de données (potentielle sous-en-tête)
            sub_row = data_rows[1]
            long_cells = sum(
                1 for cell in sub_row
                if len((cell or "").strip()) > 25
            )
            # Si la plupart des cellules sont longues → sous-en-têtes complexes
            if long_cells >= col_count - 1:
                return True
        except Exception:
            continue
    return False


def _has_overlapping_text_and_images(
    text_blocks: list,
    img_blocks: list,
    page_rect,
) -> bool:
    """
    Retourne True si au moins une image couvrant > 15 % de la page contient
    au moins 2 blocs texte (centre du bloc dans la bbox de l'image).

    Signale une page de type « mise en page visuelle » : grande photo de fond
    avec des encadrés de texte PDF superposés (checklists, infographies décorées).
    En mode hybride, cela génère du contenu dupliqué — la même information
    apparaît à la fois dans la description de l'image et dans l'extraction texte
    PyMuPDF. Le mode vision pleine page est préférable pour lire la structure globale
    sans duplication.
    """
    page_area = page_rect.width * page_rect.height
    for img_b in img_blocks:
        ix0, iy0, ix1, iy1 = img_b["bbox"]
        img_area = (ix1 - ix0) * (iy1 - iy0)

        # Ignorer les petites images (< 15 % de la surface de page)
        if img_area / page_area < 0.15:
            continue

        # Compter les blocs texte dont le centre se trouve dans la bbox de l'image
        n_overlap = sum(
            1
            for tb in text_blocks
            if ix0 <= (tb["bbox"][0] + tb["bbox"][2]) / 2 <= ix1
            and iy0 <= (tb["bbox"][1] + tb["bbox"][3]) / 2 <= iy1
        )

        if n_overlap >= 2:
            return True
    return False


def _images_in_same_band(img_blocks: list, page_height: float) -> bool:
    """
    Retourne True si au moins 3 images significatives sont dans la même bande
    verticale (même rangée horizontale, hauteur < 40 % de la page).

    Signal : mise en page de type « grille d'icônes » ou « vignettes » où
    plusieurs illustrations de même taille sont alignées côte à côte.
    Dans ce cas le mode hybride fragmente les textes de légende ; la vision
    pleine page permet au modèle de comprendre la mise en page de groupe.
    """
    if len(img_blocks) < 3:
        return False
    y0s = [b["bbox"][1] for b in img_blocks]
    y1s = [b["bbox"][3] for b in img_blocks]
    return (max(y1s) - min(y0s)) < page_height * 0.40


def _classify_page(page: fitz.Page) -> str:
    """
    Analyse rapide (sans LLM) pour choisir le mode de traitement d'une page.

    Retourne :
      'text'   — extraction texte PyMuPDF (page simple, pas d'image ni de tableau)
      'table'  — find_tables() + texte (tableaux structurés, layout simple)
      'hybrid' — texte extrait par PyMuPDF + images décrites individuellement par le modèle.
                 Déclenché quand la page mélange du texte substantiel et des images
                 (typiquement : instructions + captures d'écran de logiciel).
                 Avantage : le texte est reproduit mot pour mot, le modèle ne voit que
                 les images isolées → élimine les hallucinations sur les captures d'écran.
      'vision' — page entière rendue en image + modèle de vision.
                 Déclenché quand l'image occupe l'essentiel de la page (organigramme,
                 schéma de processus, diagramme complexe) ou quand le layout est
                 trop fragmenté pour une extraction texte fiable.
    """
    blocks = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b["type"] == 0]
    img_blocks = [b for b in blocks if b["type"] == 1]

    # Détecter les images significatives (pas des icônes ni décorations)
    significant_imgs = [
        b for b in img_blocks
        if (b["bbox"][2] - b["bbox"][0]) > _SIGNIFICANT_IMAGE_SIZE
        and (b["bbox"][3] - b["bbox"][1]) > _SIGNIFICANT_IMAGE_SIZE
    ]

    if significant_imgs:
        if len(text_blocks) >= _HYBRID_TEXT_THRESHOLD:
            # Cas 1 : beaucoup de blocs texte même avec des images → mise en page
            # complexe (infographie multi-zones, layout fragmenté avec photo).
            # Sans ce contrôle, le seuil _VISION_BLOCK_THRESHOLD est court-circuité
            # dès qu'une image est présente, forçant le mode hybride même sur des
            # pages à 30+ blocs texte.
            if len(text_blocks) > _VISION_BLOCK_THRESHOLD:
                return "vision"

            # Cas 2 : grande image dont la bbox contient des blocs texte PDF.
            # Typique des pages avec photo de fond + encadrés checklists superposés :
            # le mode hybride génère du contenu en double (image décrite + même
            # texte extrait). La vision pleine page évite cette duplication.
            if _has_overlapping_text_and_images(text_blocks, significant_imgs, page.rect):
                return "vision"

            # Cas 3 : plusieurs images alignées horizontalement (grille d'icônes /
            # vignettes). Le mode hybride fragmente les légendes ; la vision permet
            # au modèle de lire l'ensemble de la mise en page.
            if _images_in_same_band(significant_imgs, page.rect.height):
                return "vision"

            # Cas 4 : labels courts d'un schéma multi-éléments (flowchart).
            # Nombreuses petites images (≥ _DIAGRAM_MIN_IMAGES) avec du texte bref
            # → envoyer en vision pour que le modèle voie la mise en page globale.
            if (
                _is_diagram_layout(text_blocks, page.rect.width)
                and len(significant_imgs) >= _DIAGRAM_MIN_IMAGES
            ):
                return "vision"

            # Cas standard : texte extractible + capture(s) d'écran sans chevauchement.
            # PyMuPDF extrait le texte mot pour mot ; le modèle ne voit que les images.
            return "hybrid"
        # Peu de texte autour de l'image : c'est l'image qui porte l'information
        # (schéma, organigramme pleine page) → vision pleine page.
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
        # Tableaux avec double-en-têtes ou sous-en-têtes complexes :
        # find_tables() gère mal ces structures (cellules fusionnées, sous-titres de colonnes).
        # Laisser le modèle voir la page visuellement pour une meilleure fidélité.
        if _tables_have_complex_headers(tables):
            return "vision"
        if len(text_blocks) <= _TABLE_BLOCK_THRESHOLD:
            return "table"
        else:
            # Tableaux réels + beaucoup de blocs → schéma mêlé à des tableaux
            return "vision"

    # Aucun texte extractible : le contenu est en vectoriel ou en image tiles
    # (PDF de présentation, scan, export depuis PowerPoint…).
    # PyMuPDF ne peut rien extraire → vision obligatoire.
    if len(text_blocks) == 0:
        return "vision"

    # Mode texte uniquement pour les pages véritablement simples :
    # peu de blocs, pas de dispersion horizontale notable.
    # Au-delà du seuil, préférer vision pour éviter les incohérences de retranscription.
    if len(text_blocks) <= _TEXT_MODE_MAX_BLOCKS:
        return "text"

    return "vision"


# ── Rendu page et régions ──────────────────────────────────────────────────────

def _render_page(page: fitz.Page) -> Image.Image:
    """Rend une page PDF entière en image PIL à RENDER_DPI."""
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _crop_page_region(page: fitz.Page, bbox: tuple) -> Image.Image:
    """
    Rend une région rectangulaire d'une page PDF en image PIL à RENDER_DPI.
    Utilisé en mode hybride pour extraire chaque image individuellement.
    """
    rect = fitz.Rect(bbox)
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, clip=rect, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _needs_high_res(page: fitz.Page) -> bool:
    """
    Retourne True si la page mérite un rendu à _HIGH_RES_IMAGE_SIZE (1536 px).

    Critère : forte densité visuelle → organigrammes larges, pages de contacts
    multi-colonnes, logigrammes avec beaucoup d'éléments graphiques.

    Déclenchement : img_blocks >= 3 ET (largeur >= 1.2 × hauteur OU img_blocks >= 5).
    - Condition paysage (1.2×) : logigramme ou organigramme étalé horizontalement.
    - Condition img_blocks >= 5 : page dense quelle que soit son orientation.
    """
    blocks = page.get_text("dict")["blocks"]
    img_count = sum(1 for b in blocks if b["type"] == 1)
    if img_count < 3:
        return False
    w, h = page.rect.width, page.rect.height
    return (h > 0 and w >= 1.2 * h) or img_count >= 5


# ── Mode hybride ───────────────────────────────────────────────────────────────

def _join_word_fragments(
    items: list[tuple[float, str]], body_size: float
) -> list[tuple[float, str]]:
    """
    Fusionne les fragments texte très courts consécutifs en mode hybride.

    Certains PDFs (issus de PowerPoint avec positionnement absolu mot par mot)
    créent un bloc PyMuPDF distinct par mot. Chaque mot devient alors un paragraphe
    isolé dans la sortie Markdown.

    Cette fonction effectue deux passes :
    - Passe 1 : réunit les séquences de fragments ≤ 2 mots (blocs consécutifs
      séparés par un écart vertical ≤ 3,5 × taille du corps de texte).
    - Passe 2 : rattache un court fragment final (≤ 2 mots) au texte long qui
      le précède immédiatement (ex. "(double clic)." après sa phrase principale).

    Titres (lignes commençant par #), images (lignes commençant par *)
    et items vides ne sont jamais fusionnés.
    """
    if len(items) < 2:
        return items

    y_gap_limit = body_size * 3.5  # ~3 interlignages

    # ── Passe 1 : fusionner les séquences de fragments courts ─────────────────
    pass1: list[tuple[float, str]] = []
    buf_y0: float = 0.0   # y0 du premier fragment du groupe (positionnement)
    last_y0: float = 0.0  # y0 du dernier fragment ajouté (contrôle du gap)
    buf_parts: list[str] = []

    def _flush_buf() -> None:
        if buf_parts:
            pass1.append((buf_y0, f"\n{' '.join(buf_parts)}\n"))

    for y0, content in items:
        stripped = content.strip()

        # Éléments non fusionnables : titres (#), images (*), vides
        if not stripped or stripped.startswith("#") or stripped.startswith("*"):
            _flush_buf()
            buf_parts = []
            pass1.append((y0, content))
            continue

        word_count = len(stripped.split())

        if word_count <= 2:
            if buf_parts:
                if y0 - last_y0 <= y_gap_limit:
                    buf_parts.append(stripped)
                    last_y0 = y0
                else:
                    # Écart trop grand : nouveau groupe
                    _flush_buf()
                    buf_parts = [stripped]
                    buf_y0 = y0
                    last_y0 = y0
            else:
                buf_parts = [stripped]
                buf_y0 = y0
                last_y0 = y0
        else:
            # Texte substantiel : vider le tampon et ajouter directement
            _flush_buf()
            buf_parts = []
            pass1.append((y0, content))

    _flush_buf()

    # ── Passe 2 : rattacher les courts fragments finaux au texte précédent ─────
    # Ex. "(double clic)." séparé de "Puis, sélectionner l'année en cours"
    _BULLET_CHARS = {'▪', '•', '◦', '●', '–', '—'}
    pass2: list[tuple[float, str]] = []

    for y0, content in pass1:
        stripped = content.strip()

        is_short_appendable = (
            stripped
            and not stripped.startswith("#")
            and not stripped.startswith("*")
            and len(stripped.split()) <= 2
            and stripped[0] not in _BULLET_CHARS
        )

        if is_short_appendable and pass2:
            prev_y0, prev_content = pass2[-1]
            prev_stripped = prev_content.strip()
            is_prev_long_text = (
                prev_stripped
                and not prev_stripped.startswith("#")
                and not prev_stripped.startswith("*")
                and len(prev_stripped.split()) > 2
            )
            if is_prev_long_text and (y0 - prev_y0) <= y_gap_limit:
                pass2[-1] = (prev_y0, f"\n{prev_stripped} {stripped}\n")
                continue

        pass2.append((y0, content))

    return pass2


def _page_to_hybrid_markdown(
    page: fitz.Page,
    body_size: float,
    vision_model: str,
) -> str:
    """
    Mode hybride : texte extrait par PyMuPDF + images décrites individuellement.

    Pourquoi ce mode ?
    ------------------
    En mode vision pleine page, le modèle voit le texte ET les images simultanément.
    Sur les pages "instructions + captures d'écran" (typiques des guides logiciel),
    il peut :
      - lister le contenu visible dans une capture d'écran (boucle d'hallucination)
      - inventer des données dans un tableau affiché à l'écran
      - reformuler le texte au lieu de le reproduire fidèlement

    En mode hybride :
      - Le texte est extrait mot pour mot par PyMuPDF (fiable, sans interprétation)
      - Chaque image est envoyée seule au modèle avec un prompt focalisé
      - Le modèle n'a pas de contexte textuel qui pourrait le "contaminer"
    """
    blocks = page.get_text("dict")["blocks"]
    items: list[tuple[float, str]] = []

    for block in blocks:
        y0 = block["bbox"][1]

        if block["type"] == 0:  # Bloc texte → extraction directe PyMuPDF
            md = _block_to_markdown(block, body_size)
            if md:
                items.append((y0, md))

        elif block["type"] == 1:  # Bloc image → description par le modèle
            w = block["bbox"][2] - block["bbox"][0]
            h = block["bbox"][3] - block["bbox"][1]
            if w <= _SIGNIFICANT_IMAGE_SIZE or h <= _SIGNIFICANT_IMAGE_SIZE:
                continue  # Icône ou décoration → ignorer
            try:
                img = _crop_page_region(page, block["bbox"])
                description = describe_image(img, vision_model)
                if description:
                    items.append((y0, f"\n{description}\n"))
            except Exception as e:
                items.append((y0, f"\n*(image — non décrite : {type(e).__name__})*\n"))

    items.sort(key=lambda x: x[0])
    items = _join_word_fragments(items, body_size)
    return "".join(content for _, content in items)


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
    counts = {"text": 0, "table": 0, "vision": 0, "hybrid": 0}

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
                image_size = (
                    _HIGH_RES_IMAGE_SIZE if _needs_high_res(page) else PAGE_MAX_IMAGE_SIZE
                )
                if verbose and image_size == _HIGH_RES_IMAGE_SIZE:
                    print(f"1536px … ", end="", flush=True)
                try:
                    md = transcribe_page(img, vision_model, max_image_size=image_size)
                except requests.exceptions.ReadTimeout:
                    # Relance avec image plus petite (encodage ~55 % plus rapide)
                    if verbose:
                        print(f"timeout → relance {_RETRY_IMAGE_SIZE}px … ", end="", flush=True)
                    md = transcribe_page(img, vision_model, max_image_size=_RETRY_IMAGE_SIZE)
                tag = "[vision] "
            elif mode == "hybrid":
                md = _page_to_hybrid_markdown(page, body_size, vision_model)
                tag = "[hybride]"
            elif mode == "table":
                md = _page_to_table_markdown(page, body_size)
                tag = "[tableau]"
            else:
                md = _page_to_text_markdown(page, body_size)
                tag = "[texte]  "

        except Exception as e:
            if verbose:
                print(f"erreur — {e}")
            page_sections.append(
                f"> *(Page {page_num + 1} — non transcrite : {type(e).__name__})*"
            )
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
            f"  Hybride : {counts['hybrid']:3d} page(s)  "
            f"  Tableau : {counts['table']:3d} page(s)  "
            f"  Texte   : {counts['text']:3d} page(s)\n"
            f"  Appels modèle évités (texte+tableau) : {counts['table'] + counts['text']}/{total}"
        )

    doc.close()
    return "\n\n---\n\n".join(page_sections)
