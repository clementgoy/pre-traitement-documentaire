# 🏗️ Architecture Technique du Système

## Vue d'ensemble

Le système de pré-traitement documentaire est organisé en modules indépendants et réutilisables, suivant une architecture en pipeline.

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│                  (Orchestration principale)                  │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
             v                                v
    ┌────────────────┐              ┌─────────────────┐
    │ raw_to_notes   │              │ doc_to_markdown │
    │   (ancien)     │              │    (nouveau)    │
    └────────────────┘              └────────┬────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     │                       │                       │
                     v                       v                       v
           ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
           │ markdown_        │   │ document_        │   │ image_           │
           │ processor.py     │   │ extractor.py     │   │ analyzer.py      │
           └──────────────────┘   └──────────────────┘   └──────────────────┘
                     │                       │                       │
                     v                       v                       v
           ┌──────────────────────────────────────────────────────────────┐
           │                    Ollama (LLM Backend)                      │
           │  ┌──────────────┐        ┌──────────────┐                  │
           │  │ Text Model   │        │ Vision Model │                  │
           │  │ ministral3   │        │   llava      │                  │
           │  └──────────────┘        └──────────────┘                  │
           └──────────────────────────────────────────────────────────────┘
```

## Modules détaillés

### 1. config.py
**Rôle** : Configuration centralisée

**Contenu** :
- Modèles à utiliser (texte et vision)
- Paramètres de traitement (tokens, threads, seuils)
- Prompts système pour les LLM
- Dossiers d'entrée/sortie

**Avantage** : Un seul endroit pour modifier tous les paramètres

---

### 2. document_extractor.py
**Rôle** : Extraction du contenu structuré depuis PDF/DOCX

**Classes principales** :
- `ExtractedImage` : Dataclass pour une image extraite
- `DocumentContent` : Dataclass pour le contenu complet du document
- `DocumentExtractor` : Classe d'extraction

**Fonctionnalités** :
- Extraction de texte avec détection de hiérarchie (titres niveau 1, 2, 3...)
- Extraction d'images avec contexte textuel (avant/après)
- Détection de la structure (paragraphes, listes, tableaux)
- Filtrage par taille d'image (évite les icônes)

**Bibliothèques utilisées** :
- `pymupdf` (PyMuPDF) pour PDF
- `python-docx` pour DOCX
- `Pillow` pour manipulation d'images

**Flux de traitement** :

```python
fichier.pdf
    ↓
DocumentExtractor.extract()
    ↓
    ├─ Parcourir chaque page
    ├─ Extraire blocs de texte
    │  └─ Détecter niveau de titre (via taille de police)
    ├─ Extraire images
    │  ├─ Vérifier taille minimale
    │  ├─ Capturer contexte textuel
    │  └─ Sauvegarder données binaires
    └─ Construire DocumentContent
    ↓
DocumentContent {
    title, text_blocks, images, metadata
}
```

---

### 3. image_analyzer.py
**Rôle** : Analyse intelligente des images via modèle de vision

**Classes principales** :
- `ImageAnalysis` : Dataclass pour résultat d'analyse
- `ImageAnalyzer` : Classe d'analyse

**Fonctionnalités** :
- Classification d'image (schéma, graphique, photo, décoratif...)
- Évaluation de pertinence avec score de confiance
- Génération de description textuelle détaillée
- Extraction de texte visible (OCR via LLM)
- Utilisation du contexte textuel environnant

**Flux d'analyse** :

```python
image_data (bytes)
    ↓
ImageAnalyzer.analyze_image(image_data, context_before, context_after)
    ↓
    ├─ Encoder image en base64
    ├─ Construire prompt avec contexte
    ├─ Appel Ollama (modèle vision)
    │  └─ llava:13b ou llava:34b
    ├─ Parser réponse JSON
    └─ Créer ImageAnalysis
    ↓
ImageAnalysis {
    type, is_relevant, confidence, description, extracted_text
}
```

**Format de réponse attendu du LLM** :

```json
{
  "type": "diagram|chart|photo|screenshot|illustration|logo|decorative",
  "is_relevant": true|false,
  "confidence": 0.85,
  "description": "Architecture microservices avec 5 composants...",
  "contains_text": true,
  "extracted_text": "API Gateway, Service A, Service B"
}
```

---

### 4. markdown_processor.py
**Rôle** : Orchestration du pipeline complet et génération Markdown

**Classe principale** :
- `MarkdownProcessor` : Processeur principal

**Fonctionnalités** :
- Orchestration de l'extraction → analyse → génération
- Génération de Markdown brut depuis DocumentContent
- Enrichissement du texte via LLM textuel
- Découpage intelligent en chunks (pour limites de tokens)
- Intégration des descriptions d'images au bon endroit

**Pipeline de traitement** :

```python
fichier.pdf
    ↓
MarkdownProcessor.process_document()
    ↓
Phase 1: Extraction
    DocumentExtractor.extract(file) → DocumentContent
    ↓
Phase 2: Analyse d'images (si activée)
    Pour chaque image:
        ImageAnalyzer.analyze_image() → ImageAnalysis
    ↓
Phase 3: Génération Markdown brut
    _generate_markdown() → string
    ├─ Titre principal
    ├─ Métadonnées
    ├─ Pour chaque bloc:
    │  ├─ Si heading → # Titre
    │  ├─ Si paragraph → texte
    │  ├─ Si table → markdown table
    │  └─ Si image → Description (si pertinente)
    ↓
Phase 4: Enrichissement LLM
    _enrich_text_with_llm() → string
    ├─ Découper en chunks
    ├─ Pour chaque chunk:
    │  └─ Ollama(TEXT_MODEL) → markdown enrichi
    └─ Reconstituer document complet
    ↓
Phase 5: Sauvegarde
    Écrire fichier.md + images/
    ↓
fichier.ministral3_14b.md
```

---

### 5. notes_generator.py
**Rôle** : Conversion de notes brutes (ancien système, conservé pour rétrocompatibilité)

**Fonctionnalités** :
- Découpage de texte brut en chunks
- Génération de notes structurées via LLM
- Utilisation de conversation contextualisée

**Utilisation** : Pipeline `raw_to_notes`

---

### 6. main.py
**Rôle** : Point d'entrée et orchestration des pipelines

**Architecture** :

```python
main.py
├─ run_raw_to_notes()           # Ancien pipeline
│  └─ NotesGenerator
│
└─ run_doc_to_markdown()        # Nouveau pipeline
   └─ MarkdownProcessor
      ├─ DocumentExtractor
      └─ ImageAnalyzer
```

**Gestion de la parallélisation** :
- `ThreadPoolExecutor` pour traiter plusieurs documents simultanément
- Filtrage des fichiers déjà traités (évite retraitement)
- Gestion d'erreurs par document (un échec n'arrête pas le batch)

---

## Flux de données complet

```
Document PDF/DOCX
    ↓
┌────────────────────────────────────────────────┐
│  DocumentExtractor                             │
│  ┌──────────────┐        ┌─────────────┐      │
│  │  Texte       │        │   Images    │      │
│  │  structuré   │        │  + contexte │      │
│  └──────────────┘        └─────────────┘      │
└────────┬───────────────────────┬───────────────┘
         │                       │
         v                       v
┌────────────────┐      ┌─────────────────────┐
│ text_blocks[]  │      │ images[]            │
│ - heading      │      │ - image_data        │
│ - paragraph    │      │ - context_before    │
│ - table        │      │ - context_after     │
└────────┬───────┘      └──────────┬──────────┘
         │                         │
         │                         v
         │              ┌──────────────────────┐
         │              │  ImageAnalyzer       │
         │              │  (Ollama Vision)     │
         │              └──────────┬───────────┘
         │                         │
         │                         v
         │              ┌──────────────────────┐
         │              │ analyses[]           │
         │              │ - type               │
         │              │ - is_relevant        │
         │              │ - description        │
         │              └──────────┬───────────┘
         │                         │
         └─────────────┬───────────┘
                       │
                       v
            ┌───────────────────────┐
            │ MarkdownProcessor     │
            │ _generate_markdown()  │
            └──────────┬────────────┘
                       │
                       v
            ┌───────────────────────┐
            │ Markdown brut         │
            │ (structure préservée) │
            └──────────┬────────────┘
                       │
                       v
            ┌───────────────────────┐
            │ _enrich_text_with_llm()│
            │ (Ollama Text Model)   │
            └──────────┬────────────┘
                       │
                       v
            ┌───────────────────────┐
            │ Markdown enrichi      │
            │ fichier.md            │
            └───────────────────────┘
```

## Principes de conception

### 1. Modularité
Chaque module a une responsabilité unique et peut être testé indépendamment.

### 2. Séparation des préoccupations
- **Extraction** : document_extractor.py
- **Analyse** : image_analyzer.py
- **Génération** : markdown_processor.py
- **Configuration** : config.py
- **Orchestration** : main.py

### 3. Extensibilité
Facile d'ajouter :
- Nouveau format de document (PDF → implémenter dans DocumentExtractor)
- Nouveau modèle (→ modifier config.py)
- Nouvelle fonctionnalité d'analyse (→ étendre ImageAnalyzer)

### 4. Résilience
- Gestion d'erreurs à chaque niveau
- Traitement parallèle avec isolation des erreurs
- Fallbacks en cas d'échec (ex: image non analysée → marqueur placeholder)

### 5. Performance
- Traitement parallèle de plusieurs documents
- Découpage intelligent en chunks (pour limites de tokens)
- Filtrage des fichiers déjà traités
- Caching potentiel (à implémenter si besoin)

## Points d'extension possibles

### 1. Ajout de formats
```python
# Dans document_extractor.py
def _extract_from_pptx(self, file_path: Path) -> DocumentContent:
    # Implémenter extraction PowerPoint
    pass
```

### 2. Modèles personnalisés
```python
# Dans config.py
TEXT_MODEL = "votre-modele-custom"
VISION_MODEL = "votre-vision-custom"
```

### 3. Post-traitement
```python
# Dans markdown_processor.py
def _post_process(self, markdown: str) -> str:
    # Ajouter validation, liens, TOC, etc.
    pass
```

### 4. Métriques et analyse
```python
# Nouveau module: metrics.py
class MetricsCollector:
    def track_processing_time(self, doc_name, duration):
        pass
    
    def track_image_relevance_rate(self, rate):
        pass
```

## Dépendances techniques

### Obligatoires
- **Python 3.8+**
- **Ollama** : Backend LLM local
- **pymupdf** : Extraction PDF
- **python-docx** : Extraction DOCX
- **Pillow** : Manipulation images
- **ollama-python** : Client Python pour Ollama

### Optionnelles
- **python-pptx** : Support PowerPoint (futur)
- **pytesseract** : OCR avancé (futur)

## Configuration système recommandée

### Minimum
- CPU : 4 cores
- RAM : 16 GB
- Stockage : 20 GB (modèles)

### Recommandé
- CPU : 8+ cores
- RAM : 32 GB
- GPU : NVIDIA (CUDA) pour accélération
- Stockage : SSD, 50+ GB

## Sécurité et confidentialité

### Points importants
- **Traitement local** : Tout s'exécute localement via Ollama
- **Pas d'envoi externe** : Aucune donnée envoyée à des API tierces
- **Confidentialité garantie** : Documents sensibles restent sur la machine

### Bonnes pratiques
- Ne pas versionner les documents sources (`.gitignore`)
- Nettoyer régulièrement le dossier de sortie
- Sauvegarder les configurations personnalisées

---

**Dernière mise à jour** : Février 2026
