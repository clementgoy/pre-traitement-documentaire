"""
Module d'analyse intelligente d'images via modèles de vision.
Détermine la pertinence, le type et génère une description textuelle.
"""

import logging
import json
import time
import base64
from typing import Dict, Optional
from dataclasses import dataclass
import ollama
from pathlib import Path

from config import (
    VISION_MODEL, 
    SYSTEM_PROMPT_IMAGE_ANALYSIS, 
    RELEVANCE_THRESHOLD,
    MAX_IMAGE_SIZE,
    IMAGE_TYPES
)


@dataclass
class ImageAnalysis:
    """Résultat d'analyse d'une image."""
    image_type: str
    is_relevant: bool
    confidence: float
    description: str
    contains_text: bool
    extracted_text: str = ""
    processing_time: float = 0.0


class ImageAnalyzer:
    """Analyse les images avec un modèle de vision pour déterminer leur pertinence."""
    
    def __init__(self, model: str = VISION_MODEL, relevance_threshold: float = RELEVANCE_THRESHOLD):
        self.model = model
        self.relevance_threshold = relevance_threshold
        self._check_model_availability()
    
    def _check_model_availability(self):
        """Vérifie si le modèle de vision est disponible."""
        try:
            models = ollama.list()
            # Correction : accéder correctement à la liste des modèles
            models_list = models.get('models', [])
            if models_list:
                available_models = [m.get('model', m.get('name', '')) for m in models_list]
            else:
                available_models = []
            
            if self.model not in available_models:
                logging.warning(
                    f"Modèle {self.model} non trouvé. Modèles disponibles: {available_models}"
                )
                logging.warning(
                    f"Téléchargez le modèle avec: ollama pull {self.model}"
                )
        except Exception as e:
            logging.error(f"Erreur lors de la vérification du modèle: {e}")
    
    def analyze_image(
        self, 
        image_data: bytes, 
        context_before: str = "", 
        context_after: str = "",
        caption: str = ""
    ) -> ImageAnalysis:
        """
        Analyse une image et retourne son analyse complète.
        
        Args:
            image_data: Données binaires de l'image
            context_before: Texte avant l'image dans le document
            context_after: Texte après l'image dans le document
            
        Returns:
            ImageAnalysis avec les informations d'analyse
        """
        start_time = time.time()
        
        # TOUJOURS optimiser l'image pour Ollama (redimensionnement + conversion JPEG)
        try:
            from PIL import Image as PILImage
            import io
            
            pil_image = PILImage.open(io.BytesIO(image_data))
            original_size = pil_image.size
            original_format = pil_image.format
            
            # Convertir en RGB si nécessaire (pour JPEG)
            if pil_image.mode in ('RGBA', 'LA', 'P'):
                # Créer fond blanc pour images transparentes
                background = PILImage.new('RGB', pil_image.size, (255, 255, 255))
                if pil_image.mode == 'P':
                    pil_image = pil_image.convert('RGBA')
                background.paste(pil_image, mask=pil_image.split()[-1] if pil_image.mode in ('RGBA', 'LA') else None)
                pil_image = background
            elif pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # Toujours redimensionner pour optimiser (max 1024x1024)
            needs_resize = pil_image.width > 1024 or pil_image.height > 1024
            if needs_resize:
                logging.info(
                    f"🔄 Optimisation image : {original_size} ({original_format}) → JPEG 1024px max"
                )
                pil_image.thumbnail((1024, 1024), PILImage.Resampling.LANCZOS)
            else:
                logging.info(f"🔄 Conversion image : {original_size} ({original_format}) → JPEG optimisé")
            
            # Ré-encoder en JPEG (plus léger que PNG pour Ollama)
            buffer = io.BytesIO()
            pil_image.save(buffer, format='JPEG', quality=90, optimize=True)
            image_data = buffer.getvalue()
            
            logging.info(f"✅ Image optimisée : {original_size} → {pil_image.size}, {len(image_data)//1024}KB")
        except Exception as e:
            logging.error(f"❌ Erreur optimisation image : {e}")
            logging.warning("⚠️ Utilisation de l'image originale (peut causer crash Ollama)")
        
        # Encoder l'image en base64 pour Ollama
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # Construire le prompt avec contexte
        prompt = self._build_analysis_prompt(context_before, context_after, caption)
        
        try:
            # Appel au modèle de vision
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                        'images': [image_base64]
                    }
                ]
            )
            
            # Parser la réponse JSON
            response_text = response['message']['content']
            
            # Débogage : logger la réponse brute
            if not response_text or len(response_text.strip()) < 10:
                logging.error(f"❌ Réponse LLaVA VIDE ou trop courte : '{response_text}'")
            else:
                logging.debug(f"📝 Réponse LLaVA (premiers 200 car) : {response_text[:200]}")
            
            analysis_data = self._parse_response(response_text)
            
            # Créer l'objet ImageAnalysis
            # On fait confiance au LLM pour is_relevant, on vérifie juste un seuil minimal de confiance
            analysis = ImageAnalysis(
                image_type=analysis_data.get('type', 'unknown'),
                is_relevant=analysis_data.get('is_relevant', False) and 
                           analysis_data.get('confidence', 0.0) >= self.relevance_threshold,
                confidence=analysis_data.get('confidence', 0.0),
                description=analysis_data.get('description', ''),
                contains_text=analysis_data.get('contains_text', False),
                extracted_text=analysis_data.get('extracted_text', ''),
                processing_time=time.time() - start_time
            )
            
            # Vérifier si la description est vide ou contient des caractères invalides
            has_invalid_chars = '<unk>' in analysis.description or analysis.description.strip() in ['', '#', '<unk>', 'None']
            
            if analysis.is_relevant and (not analysis.description or len(analysis.description.strip()) < 20 or has_invalid_chars):
                logging.error(
                    f"❌ ERREUR : Description d'image invalide/vide pour image pertinente ! "
                    f"Type: {analysis.image_type}, Confiance: {analysis.confidence}, "
                    f"Texte extrait: '{analysis.extracted_text[:100] if analysis.extracted_text else 'aucun'}', "
                    f"Description reçue: '{analysis.description[:100]}'"
                )
                
                # Fallback robuste : description minimale mais utile
                desc_parts = []
                desc_parts.append(f"[AVERTISSEMENT: Analyse automatique échouée]")
                desc_parts.append(f"Type d'image détecté : {analysis.image_type}")
                
                if analysis.extracted_text and len(analysis.extracted_text.strip()) > 3:
                    desc_parts.append(f"Texte visible dans l'image : {analysis.extracted_text}")
                else:
                    desc_parts.append("Image contenant probablement un schéma, diagramme ou organigramme.")
                    desc_parts.append("Vérifiez le fichier image original dans le dossier 'images/'.")
                
                if context_before:
                    desc_parts.append(f"Contexte du document : {context_before[:150]}")
                
                analysis.description = " ".join(desc_parts)
                analysis.is_relevant = True  # Forçer pertinent même si analyse échouée
            
            logging.info(
                f"Image analysée: {analysis.image_type} "
                f"(pertinent: {analysis.is_relevant}, confiance: {analysis.confidence:.2f}, desc: {len(analysis.description)} car) "
                f"en {analysis.processing_time:.2f}s"
            )
            
            return analysis
            
        except Exception as e:
            logging.error(f"Erreur lors de l'analyse d'image: {e}")
            # Retourner une analyse par défaut en cas d'erreur
            return ImageAnalysis(
                image_type="unknown",
                is_relevant=False,
                confidence=0.0,
                description="Erreur lors de l'analyse",
                contains_text=False,
                processing_time=time.time() - start_time
            )
    
    def _build_analysis_prompt(self, context_before: str, context_after: str, caption: str) -> str:
        """Construit le prompt d'analyse avec contexte et légende."""
        prompt = SYSTEM_PROMPT_IMAGE_ANALYSIS + "\n\n"
        
        if context_before:
            prompt += f"**Contexte avant l'image:**\n{context_before}\n\n"
        
        if caption:
            prompt += f"**Légende de l'image:**\n{caption}\n\n"
        
        if context_after:
            prompt += f"**Contexte après l'image:**\n{context_after}\n\n"
        
        prompt += "**Analyse l'image et fournis ta réponse au format JSON spécifié.**"
        
        return prompt
    
    def _parse_response(self, response_text: str) -> Dict:
        """Parse la réponse JSON du modèle."""
        try:
            # Essayer de parser directement
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Si le JSON est entouré de texte, essayer de l'extraire
            try:
                # Chercher le JSON entre accolades
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                
                if start != -1 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
                else:
                    raise ValueError("Pas de JSON trouvé dans la réponse")
            except Exception as e:
                logging.error(f"Impossible de parser la réponse: {response_text}")
                # Retourner une structure par défaut
                return {
                    'type': 'unknown',
                    'is_relevant': False,
                    'confidence': 0.0,
                    'description': response_text[:500],  # Prendre les premiers 500 caractères
                    'contains_text': False,
                    'extracted_text': ''
                }
    
    def batch_analyze(
        self, 
        images_data: list,
        contexts_before: list,
        contexts_after: list
    ) -> list[ImageAnalysis]:
        """
        Analyse un lot d'images de manière séquentielle.
        
        Args:
            images_data: Liste de données binaires d'images
            contexts_before: Liste des contextes avant
            contexts_after: Liste des contextes après
            
        Returns:
            Liste des analyses
        """
        results = []
        total = len(images_data)
        
        for idx, (img_data, ctx_before, ctx_after) in enumerate(
            zip(images_data, contexts_before, contexts_after), start=1
        ):
            logging.info(f"Analyse image {idx}/{total}")
            analysis = self.analyze_image(img_data, ctx_before, ctx_after)
            results.append(analysis)
        
        # Statistiques
        relevant_count = sum(1 for a in results if a.is_relevant)
        logging.info(
            f"Analyse terminée: {relevant_count}/{total} images pertinentes "
            f"({relevant_count/total*100:.1f}%)"
        )
        
        return results
    
    def is_decorative(self, analysis: ImageAnalysis) -> bool:
        """Détermine si une image est purement décorative (logo, icône uniquement)."""
        # Filtrage strict : seulement les vrais éléments décoratifs
        decorative_types = ['logo', 'icon']
        # On ne filtre que si c'est explicitement décoratif ET sans texte important
        return (
            analysis.image_type in decorative_types and 
            not analysis.contains_text
        )
    
    def get_markdown_description(self, analysis: ImageAnalysis, image_index: int, caption: str = "") -> str:
        """
        Génère une description Markdown de l'image à insérer dans le document.
        
        Args:
            analysis: Résultat de l'analyse
            image_index: Index de l'image
            caption: Légende originale si présente
            
        Returns:
            Description Markdown formatée
        """
        # Filtrer uniquement les vraies images décoratives (logos/icônes sans texte)
        if self.is_decorative(analysis):
            return f"<!-- Image décorative {image_index} ignorée (logo/icône) -->"
        
        # Même si is_relevant=False, on transcrit quand même avec un avertissement
        # (mieux vaut trop transcrire que manquer une info importante)
        
        # Construction de la description Markdown
        markdown = f"\n\n---\n\n"
        markdown += f"**[Image {image_index}: {IMAGE_TYPES.get(analysis.image_type, 'Image')}]**\n\n"
        
        if caption:
            markdown += f"*Légende:* {caption}\n\n"
        
        if analysis.contains_text and analysis.extracted_text:
            markdown += f"*Texte visible:*\n> {analysis.extracted_text}\n\n"
        
        markdown += f"*Description:*\n{analysis.description}\n"
        markdown += f"\n---\n\n"
        
        return markdown


# Test unitaire
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    analyzer = ImageAnalyzer()
    
    # Test avec une image exemple
    # with open("test_image.png", "rb") as f:
    #     image_data = f.read()
    # 
    # analysis = analyzer.analyze_image(
    #     image_data,
    #     context_before="Ce document présente l'architecture du système",
    #     context_after="Le schéma montre les différents composants"
    # )
    # 
    # print(f"Type: {analysis.image_type}")
    # print(f"Pertinent: {analysis.is_relevant}")
    # print(f"Description: {analysis.description}")
