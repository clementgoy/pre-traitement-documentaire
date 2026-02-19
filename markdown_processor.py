"""
Module de traitement et génération de Markdown enrichi avec transcription d'images.
Orchestre l'extraction, l'analyse et la génération du document final.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional
import ollama

from config import (
    TEXT_MODEL, 
    SYSTEM_PROMPT_TEXT,
    MAX_TOKENS,
    OUTPUT_FOLDER
)
from document_extractor import DocumentExtractor, DocumentContent, ExtractedImage
from image_analyzer import ImageAnalyzer, ImageAnalysis


class MarkdownProcessor:
    """Processeur principal pour convertir des documents en Markdown enrichi."""
    
    def __init__(
        self, 
        text_model: str = TEXT_MODEL,
        vision_model: str = None,
        max_tokens: int = MAX_TOKENS,
        analyze_images: bool = True,
        enrich_text: bool = False
    ):
        self.text_model = text_model
        self.max_tokens = max_tokens
        self.analyze_images = analyze_images
        self.enrich_text = enrich_text
        # Mode par défaut : extraction algorithmique pure (100% fidèle) + analyse LLM des images
        # Mode enrich_text : ajoute un nettoyage LLM du texte pour améliorer la structure Markdown
        
        # Initialiser les composants
        self.extractor = DocumentExtractor()
        self.image_analyzer = ImageAnalyzer(model=vision_model) if analyze_images else None
    
    def process_document(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        Traite un document complet et génère un Markdown enrichi.
        
        Args:
            input_path: Chemin du document source
            output_path: Chemin de sortie (optionnel)
            
        Returns:
            Chemin du fichier Markdown généré
        """
        start_time = time.time()
        input_path = Path(input_path)
        
        logging.info(f"=== Traitement du document: {input_path.name} ===")
        
        # 1. Extraction du contenu
        logging.info("Phase 1: Extraction du contenu")
        document = self.extractor.extract(input_path)
        logging.info(
            f"Extraction terminée: {len(document.text_blocks)} blocs de texte, "
            f"{len(document.images)} images"
        )
        
        # 2. Analyse des images (si activée)
        image_analyses = []
        if self.analyze_images and document.images:
            logging.info("Phase 2: Analyse des images")
            image_analyses = self._analyze_all_images(document.images)
        else:
            logging.info("Phase 2: Analyse d'images désactivée")
        
        # 3. Génération du Markdown
        logging.info("Phase 3: Génération du Markdown")
        markdown_content = self._generate_markdown(document, image_analyses)
        
        # 4. Enrichissement optionnel du texte avec LLM
        if self.enrich_text:
            logging.info("Phase 4: Enrichissement Markdown avec LLM (amélioration structure)")
            logging.warning("ATTENTION : Le LLM peut ajouter <5% d'information malgré le prompt strict")
            enriched_markdown = self._enrich_text_with_llm(markdown_content)
        else:
            logging.info("Phase 4: SKIP LLM textuel - Extraction algorithmique pure (100% fidèle sur texte)")
            enriched_markdown = markdown_content
        
        # 5. Sauvegarde
        if output_path is None:
            output_path = self._get_default_output_path(input_path)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(enriched_markdown)
        
        # Sauvegarder les images si nécessaire
        if document.images:
            self.extractor.save_images(document, output_path.parent)
        
        elapsed = time.time() - start_time
        logging.info(
            f"=== Traitement terminé en {elapsed:.2f}s ===\n"
            f"Document généré: {output_path}"
        )
        
        return str(output_path)
    
    def _analyze_all_images(self, images: List[ExtractedImage]) -> List[ImageAnalysis]:
        """Analyse toutes les images extraites."""
        analyses = []
        
        for idx, image in enumerate(images, start=1):
            logging.info(f"Analyse de l'image {idx}/{len(images)}")
            analysis = self.image_analyzer.analyze_image(
                image_data=image.image_data,
                context_before=image.context_before,
                context_after=image.context_after,
                caption=image.caption
            )
            analyses.append(analysis)
        
        return analyses
    
    def _generate_markdown(
        self, 
        document: DocumentContent, 
        image_analyses: List[ImageAnalysis]
    ) -> str:
        """Génère le contenu Markdown brut depuis le document extrait."""
        markdown_lines = []
        
        # Titre principal
        markdown_lines.append(f"# {document.title}\n")
        
        # Métadonnées optionnelles
        if document.metadata:
            markdown_lines.append("---")
            for key, value in document.metadata.items():
                markdown_lines.append(f"{key}: {value}")
            markdown_lines.append("---\n")
        
        # Parcourir les blocs de texte
        image_counter = 0
        
        for block in document.text_blocks:
            block_type = block['type']
            content = block['content']
            
            if block_type == 'heading':
                level = block['level']
                markdown_lines.append(f"\n{'#' * level} {content}\n")
            
            elif block_type == 'paragraph':
                markdown_lines.append(f"{content}\n")
            
            elif block_type == 'table':
                markdown_lines.append(f"\n{content}\n")
            
            elif block_type == 'image':
                # Insérer la description de l'image analysée
                if image_counter < len(image_analyses):
                    analysis = image_analyses[image_counter]
                    image = document.images[image_counter]
                    
                    if self.image_analyzer and not self.image_analyzer.is_decorative(analysis):
                        description = self.image_analyzer.get_markdown_description(
                            analysis, 
                            image_counter + 1,
                            image.caption
                        )
                        markdown_lines.append(description)
                    else:
                        # Image décorative ou non analysée
                        markdown_lines.append(
                            f"\n<!-- Image {image_counter + 1}: décorative ou non pertinente -->\n"
                        )
                    
                    image_counter += 1
        
        return "\n".join(markdown_lines)
    
    def _enrich_text_with_llm(self, markdown_text: str) -> str:
        """
        Nettoie le texte Markdown avec le modèle de langage en mode STRICT.
        Retranscription fidèle uniquement, correction syntaxe Markdown.
        
        AVERTISSEMENT : Même en mode strict, le LLM peut ajouter <5% d'information
        (hallucinations, déductions). Pour garantie 100%, utiliser --raw.
        """
        from config import SYSTEM_PROMPT_TEXT_STRICT
        
        chunks = self._split_markdown(markdown_text)
        enriched_chunks = []
        
        messages = []
        
        for idx, chunk in enumerate(chunks, start=1):
            logging.info(f"Nettoyage STRICT chunk {idx}/{len(chunks)} (retranscription fidèle)")
            
            messages.append({
                'role': 'user',
                'content': f"{SYSTEM_PROMPT_TEXT_STRICT}\n\n{chunk}"
            })
            
            try:
                response = ollama.chat(model=self.text_model, messages=messages)
                enriched_text = response['message']['content']
                enriched_chunks.append(enriched_text)
                
                # Ajouter la réponse à l'historique pour contexte
                messages.append(response['message'])
                
            except Exception as e:
                logging.error(f"Erreur enrichissement chunk {idx}: {e}")
                # En cas d'erreur, garder le texte original
                enriched_chunks.append(chunk)
        
        return "\n\n".join(enriched_chunks)
    
    def _split_markdown(self, text: str) -> List[str]:
        """
        Découpe le texte Markdown en chunks intelligents.
        Respecte les sections et évite de couper au milieu d'un paragraphe.
        """
        lines = text.split('\n')
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = len(line.split())
            
            # Si on atteint la limite, créer un nouveau chunk
            if current_tokens + line_tokens > self.max_tokens and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_tokens = 0
            
            current_chunk.append(line)
            current_tokens += line_tokens
        
        # Ajouter le dernier chunk
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        logging.info(f"Texte divisé en {len(chunks)} chunks")
        return chunks
    
    def _get_default_output_path(self, input_path: Path) -> Path:
        """Génère le chemin de sortie par défaut."""
        output_dir = Path(OUTPUT_FOLDER)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        model_name = self.text_model.replace(":", "_")
        output_filename = f"{input_path.stem}.{model_name}.md"
        
        return output_dir / output_filename
    
    def process_batch(self, input_folder: str, output_folder: Optional[str] = None):
        """
        Traite tous les documents d'un dossier.
        
        Args:
            input_folder: Dossier contenant les documents sources
            output_folder: Dossier de sortie (optionnel)
        """
        input_path = Path(input_folder)
        
        # Trouver tous les fichiers supportés
        supported_files = []
        for ext in ['pdf', 'docx', 'doc']:
            supported_files.extend(input_path.glob(f"**/*.{ext}"))
        
        logging.info(f"Traitement de {len(supported_files)} documents")
        
        for idx, file_path in enumerate(supported_files, start=1):
            logging.info(f"\n{'='*60}")
            logging.info(f"Document {idx}/{len(supported_files)}: {file_path.name}")
            logging.info(f"{'='*60}")
            
            try:
                output_path = None
                if output_folder:
                    output_path = Path(output_folder) / f"{file_path.stem}.md"
                
                self.process_document(str(file_path), output_path)
                
            except Exception as e:
                logging.error(f"Erreur lors du traitement de {file_path.name}: {e}")
                continue


# Test unitaire
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    processor = MarkdownProcessor()
    
    # Test sur un document
    # processor.process_document("docs-bruts/test.pdf")
    
    # Ou traiter un dossier complet
    # processor.process_batch("docs-bruts", "docs-traites")
