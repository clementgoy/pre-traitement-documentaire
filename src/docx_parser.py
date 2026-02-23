"""
Conversion de fichiers Word (.docx) en Markdown.

Les styles de titres Word (Heading 1, Titre 1, etc.) sont mappés
directement vers les niveaux Markdown (#, ##, ###...).

Les tableaux sont rendus en syntaxe Markdown basique.
Les images inline sont extraites et analysées via le modèle de vision.
"""

import re
from io import BytesIO

from docx import Document
from PIL import Image

from .image_analyzer import analyze_image

# Correspondance styles Word → niveau de titre Markdown
_HEADING_STYLES: dict[str, int] = {
    # Anglais
    "heading 1": 1, "heading 2": 2, "heading 3": 3,
    "heading 4": 4, "heading 5": 5,
    # Français (Word FR)
    "titre 1": 1, "titre 2": 2, "titre 3": 3,
    "titre 4": 4, "titre 5": 5,
    # Variantes sans espace
    "heading1": 1, "heading2": 2, "heading3": 3,
    "heading4": 4, "heading5": 5,
}

# Namespaces OOXML utilisés pour chercher les images inline
_NS_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_BLIP_TAG = f"{{{_NS_DRAWING}}}blip"
_EMBED_ATTR = f"{{{_NS_REL}}}embed"


def _style_to_level(style_name: str) -> int:
    """Retourne le niveau de titre (1-5) ou 0 si ce n'est pas un titre."""
    if not style_name:
        return 0
    key = style_name.strip().lower()
    if key in _HEADING_STYLES:
        return _HEADING_STYLES[key]
    # Patterns génériques : "Heading 2", "Titre3", etc.
    m = re.match(r"heading\s*(\d)", key)
    if m:
        return int(m.group(1))
    m = re.match(r"titre\s*(\d)", key)
    if m:
        return int(m.group(1))
    return 0


def _extract_images_from_element(element, doc_part) -> list[Image.Image]:
    """
    Extrait les images embarquées dans un élément XML (paragraphe ou cellule).

    Les images inline Word sont stockées dans les relations du document.
    On cherche les éléments <a:blip r:embed="rIdX"/> pour trouver les rIds,
    puis on résout la relation pour obtenir les octets de l'image.
    """
    images: list[Image.Image] = []
    for blip in element.iter(_BLIP_TAG):
        r_id = blip.get(_EMBED_ATTR)
        if not r_id:
            continue
        rel = doc_part.rels.get(r_id)
        if rel is None or "image" not in rel.reltype.lower():
            continue
        try:
            img = Image.open(BytesIO(rel.target_part.blob))
            images.append(img)
        except Exception:
            pass
    return images


def _table_to_markdown(table) -> str:
    """Convertit un tableau Word en tableau Markdown (format GFM)."""
    if not table.rows:
        return ""

    rows_md: list[str] = []
    for i, row in enumerate(table.rows):
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        rows_md.append("| " + " | ".join(cells) + " |")
        if i == 0:
            rows_md.append("|" + "|".join(["---"] * len(cells)) + "|")

    return "\n".join(rows_md)


def _process_paragraph_element(p_elem, doc_part, parts, vision_model, analyze_images, verbose):
    """Traite un élément <w:p> du corps du document."""
    from docx.text.paragraph import Paragraph as DocxParagraph
    para = DocxParagraph(p_elem, doc_part)

    text = para.text.strip()
    level = _style_to_level(para.style.name if para.style else "")

    if text:
        if level > 0:
            prefix = "#" * level
            parts.append(f"\n{prefix} {text}\n")
        else:
            parts.append(f"\n{text}\n")

    if analyze_images:
        images = _extract_images_from_element(p_elem, doc_part)
        for img in images:
            if verbose:
                print(f"  Image ({img.width}x{img.height}) ...", end=" ", flush=True)
            result = analyze_image(img, vision_model)
            if result["relevant"]:
                parts.append(f"\n> **[Visuel]** {result['description']}\n")
                if verbose:
                    print("pertinente [OK]")
            else:
                if verbose:
                    print(f"ignorée — {result['reason']}")


def _process_table_element(tbl_elem, doc_part, parts, vision_model, analyze_images, verbose):
    """Traite un élément <w:tbl> du corps du document."""
    from docx.table import Table as DocxTable
    table = DocxTable(tbl_elem, doc_part)

    md_table = _table_to_markdown(table)
    if md_table:
        parts.append(f"\n{md_table}\n")

    if analyze_images:
        for row in table.rows:
            for cell in row.cells:
                images = _extract_images_from_element(cell._element, doc_part)
                for img in images:
                    if verbose:
                        print(
                            f"  Image tableau ({img.width}x{img.height}) ...",
                            end=" ",
                            flush=True,
                        )
                    result = analyze_image(img, vision_model)
                    if result["relevant"]:
                        parts.append(f"\n> **[Visuel]** {result['description']}\n")
                        if verbose:
                            print("pertinente [OK]")
                    else:
                        if verbose:
                            print(f"ignorée — {result['reason']}")


def parse_docx(
    file_path: str,
    vision_model: str,
    analyze_images: bool = True,
    verbose: bool = True,
) -> str:
    """
    Parse un fichier Word et retourne son contenu en Markdown.

    L'ordre de traitement respecte le flux du document :
    paragraphes et tableaux dans leur ordre d'apparition.

    Note : on crée les objets Paragraph/Table directement depuis les éléments
    XML du body, pour ne pas inclure par erreur les paragraphes imbriqués
    dans les tableaux (doc.paragraphs les inclut tous en mode récursif).
    """
    doc = Document(file_path)
    parts: list[str] = []
    body = doc.element.body

    for child in body:
        # Extraction du nom local de la balise (sans namespace)
        local_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if local_tag == "p":
            _process_paragraph_element(
                child, doc.part, parts, vision_model, analyze_images, verbose
            )
        elif local_tag == "tbl":
            _process_table_element(
                child, doc.part, parts, vision_model, analyze_images, verbose
            )
        # Les autres balises (sectPr, etc.) sont ignorées

    return "".join(parts)
