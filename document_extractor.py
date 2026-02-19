"""
Module d'extraction de contenu depuis différents formats de documents.
Extrait le texte, les images, et la structure hiérarchique.
"""

import logging
import os
import io
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from PIL import Image

# Imports conditionnels pour gérer les dépendances
try:
    import pymupdf as fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF non installé. Utiliser: pip install pymupdf")

try:
    from docx import Document as DocxDocument
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import _Cell, Table
    from docx.text.paragraph import Paragraph
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logging.warning("python-docx non installé. Utiliser: pip install python-docx")


@dataclass
class ExtractedImage:
    """Représente une image extraite d'un document."""
    image_data: bytes
    image_format: str
    page_number: int
    position_index: int  # Position relative dans le document
    width: int
    height: int
    context_before: str = ""  # Texte avant l'image
    context_after: str = ""   # Texte après l'image
    caption: str = ""         # Légende/caption de l'image si présente


@dataclass
class DocumentContent:
    """Représente le contenu structuré d'un document."""
    title: str
    text_blocks: List[Dict[str, any]]  # {type: "heading"|"paragraph"|"list", level: int, content: str}
    images: List[ExtractedImage]
    metadata: Dict[str, str]


class DocumentExtractor:
    """Extrait le contenu structuré de différents formats de documents."""
    
    def __init__(self, min_image_size: Tuple[int, int] = (100, 100)):
        self.min_image_size = min_image_size
        
    def extract(self, file_path: str) -> DocumentContent:
        """Extrait le contenu d'un document selon son extension."""
        file_path = Path(file_path)
        extension = file_path.suffix.lower().lstrip('.')
        
        logging.info(f"Extraction du document: {file_path.name}")
        
        if extension == 'pdf':
            return self._extract_from_pdf(file_path)
        elif extension in ['docx', 'doc']:
            return self._extract_from_docx(file_path)
        else:
            raise ValueError(f"Format non supporté: {extension}")
    
    def _extract_from_pdf(self, file_path: Path) -> DocumentContent:
        """Extrait le contenu d'un PDF avec PyMuPDF."""
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF requis pour traiter les PDFs")
        
        doc = fitz.open(file_path)
        text_blocks = []
        images = []
        position_index = 0
        
        # Métadonnées
        metadata = {
            "pages": doc.page_count,
            "format": "PDF",
            "title": doc.metadata.get("title", file_path.stem),
        }
        
        title = doc.metadata.get("title", file_path.stem)
        
        for page_num, page in enumerate(doc, start=1):
            logging.info(f"Traitement page {page_num}/{doc.page_count}")
            
            # Extraction du texte avec structure
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if block["type"] == 0:  # Bloc de texte
                    for line in block.get("lines", []):
                        text = ""
                        font_size = 0
                        for span in line.get("spans", []):
                            text += span["text"]
                            font_size = max(font_size, span["size"])
                        
                        text = text.strip()
                        if text:
                            # Détection des titres par taille de police
                            if font_size > 14:
                                level = 1
                            elif font_size > 12:
                                level = 2
                            elif font_size > 10:
                                level = 3
                            else:
                                level = 0
                            
                            block_type = "heading" if level > 0 else "paragraph"
                            text_blocks.append({
                                "type": block_type,
                                "level": level,
                                "content": text,
                                "page": page_num,
                                "position": position_index
                            })
                            position_index += 1
                
                elif block["type"] == 1:  # Bloc image
                    try:
                        # Extraire l'image
                        image_list = page.get_images()
                        for img_index, img in enumerate(image_list):
                            xref = img[0]
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]
                            
                            # Vérifier la taille de l'image
                            pil_image = Image.open(io.BytesIO(image_bytes))
                            width, height = pil_image.size
                            
                            if width >= self.min_image_size[0] and height >= self.min_image_size[1]:
                                # Contexte textuel
                                context_before = self._get_context_text(text_blocks, -3)
                                context_after = ""  # Sera rempli plus tard
                                
                                # Chercher une légende (texte juste après l'image, souvent en plus petit)
                                caption = self._extract_caption_pdf(page, block)
                                
                                extracted_img = ExtractedImage(
                                    image_data=image_bytes,
                                    image_format=image_ext,
                                    page_number=page_num,
                                    position_index=position_index,
                                    width=width,
                                    height=height,
                                    context_before=context_before,
                                    context_after=context_after,
                                    caption=caption
                                )
                                images.append(extracted_img)
                                
                                # Marqueur dans les blocs de texte
                                text_blocks.append({
                                    "type": "image",
                                    "level": 0,
                                    "content": f"[IMAGE_{len(images)-1}]",
                                    "page": page_num,
                                    "position": position_index
                                })
                                position_index += 1
                                
                                logging.info(f"Image extraite: {width}x{height}px (page {page_num})")
                    except Exception as e:
                        logging.error(f"Erreur extraction image page {page_num}: {e}")
        
        doc.close()
        
        # Remplir le contexte après pour chaque image
        for img in images:
            img.context_after = self._get_context_after(text_blocks, img.position_index, 3)
        
        return DocumentContent(
            title=title,
            text_blocks=text_blocks,
            images=images,
            metadata=metadata
        )
    
    def _extract_from_docx(self, file_path: Path) -> DocumentContent:
        """Extrait le contenu d'un document Word."""
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx requis pour traiter les fichiers Word")
        
        doc = DocxDocument(file_path)
        text_blocks = []
        images = []
        position_index = 0
        
        # Métadonnées
        metadata = {
            "format": "DOCX",
            "title": doc.core_properties.title or file_path.stem,
        }
        
        title = doc.core_properties.title or file_path.stem
        
        # Parcourir tous les éléments du document
        for element in doc.element.body:
            # Paragraphes
            if isinstance(element, CT_P):
                paragraph = Paragraph(element, doc)
                text = paragraph.text.strip()
                
                if text:
                    # Détection du niveau de titre
                    level = 0
                    
                    # Méthode 1 : Style Word explicite
                    if paragraph.style.name.startswith('Heading'):
                        try:
                            level = int(paragraph.style.name.split()[-1])
                        except:
                            level = 1
                    
                    # Méthode 2 : Heuristique (texte court en MAJUSCULES)
                    elif len(text) < 100 and text.isupper() and not any(char in text for char in ['|', '€', '@']):
                        # Paragraphe court tout en majuscules sans caractères spéciaux = probablement un titre
                        level = 2  # Titre de niveau 2 par défaut
                    
                    # Méthode 3 : Texte court avec mise en forme spéciale (gras + taille > normale)
                    elif len(text) < 150 and paragraph.runs:
                        # Vérifier si le premier run est en gras et a une taille notable
                        first_run = paragraph.runs[0]
                        try:
                            is_bold = first_run.bold
                            font_size = first_run.font.size
                            # Si gras ET (grande police OU ligne courte sans ponctuation finale)
                            if is_bold and (not text.endswith('.') and not text.endswith(',')):
                                level = 3  # Sous-titre de niveau 3
                        except:
                            pass
                    
                    block_type = "heading" if level > 0 else "paragraph"
                    text_blocks.append({
                        "type": block_type,
                        "level": level,
                        "content": text,
                        "page": 0,
                        "position": position_index
                    })
                    position_index += 1
                
                # Extraire les images du paragraphe
                for run in paragraph.runs:
                    if 'graphicData' in run.element.xml:
                        try:
                            # Extraction d'images via relations
                            for rel in doc.part.rels.values():
                                if "image" in rel.target_ref:
                                    image_data = rel.target_part.blob
                                    
                                    # Vérifier la taille
                                    pil_image = Image.open(io.BytesIO(image_data))
                                    width, height = pil_image.size
                                    
                                    if width >= self.min_image_size[0] and height >= self.min_image_size[1]:
                                        # Contexte textuel
                                        context_before = self._get_context_text(text_blocks, -3)
                                        
                                        # Chercher légende dans les paragraphes suivants
                                        caption = self._extract_caption_docx(paragraph)
                                        
                                        extracted_img = ExtractedImage(
                                            image_data=image_data,
                                            image_format=pil_image.format.lower(),
                                            page_number=0,
                                            position_index=position_index,
                                            width=width,
                                            height=height,
                                            context_before=context_before,
                                            context_after="",
                                            caption=caption
                                        )
                                        images.append(extracted_img)
                                        
                                        text_blocks.append({
                                            "type": "image",
                                            "level": 0,
                                            "content": f"[IMAGE_{len(images)-1}]",
                                            "page": 0,
                                            "position": position_index
                                        })
                                        position_index += 1
                                        
                                        logging.info(f"Image extraite: {width}x{height}px")
                        except Exception as e:
                            logging.error(f"Erreur extraction image: {e}")
            
            # Tables
            elif isinstance(element, CT_Tbl):
                table = Table(element, doc)
                # Conversion simple de la table en texte structuré
                table_text = self._table_to_text(table)
                text_blocks.append({
                    "type": "table",
                    "level": 0,
                    "content": table_text,
                    "page": 0,
                    "position": position_index
                })
                position_index += 1
        
        # Remplir contexte après
        for img in images:
            img.context_after = self._get_context_after(text_blocks, img.position_index, 3)
        
        return DocumentContent(
            title=title,
            text_blocks=text_blocks,
            images=images,
            metadata=metadata
        )
    
    def _get_context_text(self, text_blocks: List[Dict], num_blocks: int) -> str:
        """Récupère le texte de contexte des N derniers blocs."""
        if num_blocks < 0:
            blocks = text_blocks[num_blocks:]
        else:
            blocks = text_blocks[:num_blocks]
        
        return " ".join([
            block["content"] 
            for block in blocks 
            if block["type"] in ["heading", "paragraph"]
        ])
    
    def _get_context_after(self, text_blocks: List[Dict], position: int, num_blocks: int) -> str:
        """Récupère le texte de contexte après une position donnée."""
        future_blocks = [
            block for block in text_blocks 
            if block["position"] > position and block["type"] in ["heading", "paragraph"]
        ][:num_blocks]
        
        return " ".join([block["content"] for block in future_blocks])
    
    def _table_to_text(self, table: 'Table') -> str:
        """Convertit une table Word en texte structuré."""
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        return "\n".join(rows)
    
    def _extract_caption_pdf(self, page, image_block) -> str:
        """
        Tente d'extraire une légende pour une image PDF.
        Cherche du texte juste en dessous de l'image avec une police plus petite.
        """
        # Simplifié : retourne la première ligne de texte après l'image si petite police
        # Une implémentation complète analyserait la position et la taille de police
        return ""
    
    def _extract_caption_docx(self, paragraph) -> str:
        """
        Extrait la légende d'une image Word si présente.
        Word stocke souvent les légendes dans le style 'Caption'.
        """
        # Vérifier si le paragraphe suivant est un caption
        try:
            if paragraph.style and 'caption' in paragraph.style.name.lower():
                return paragraph.text.strip()
        except:
            pass
        return ""
    
    def save_images(self, document: DocumentContent, output_dir: Path):
        """Sauvegarde les images extraites dans un dossier."""
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, img in enumerate(document.images):
            filename = f"image_{idx:03d}.{img.image_format}"
            filepath = images_dir / filename
            
            with open(filepath, "wb") as f:
                f.write(img.image_data)
            
            logging.info(f"Image sauvegardée: {filename}")
        
        return images_dir


# Test unitaire
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    extractor = DocumentExtractor()
    
    # Test avec un fichier PDF
    # doc = extractor.extract("test.pdf")
    # print(f"Titre: {doc.title}")
    # print(f"Blocs de texte: {len(doc.text_blocks)}")
    # print(f"Images: {len(doc.images)}")
