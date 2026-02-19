# Documentation Technique - Pré-traitement Documentaire

## Objectif du système

Ce système automatise la conversion de documents techniques (PDF, DOCX) vers le format Markdown avec transcription intelligente des éléments visuels. L'objectif principal est d'améliorer l'assimilation des informations contenues dans ces documents par les modèles de langage (LLM) comme Delibia, en compensant leur incapacité à interpréter correctement les schémas et images.

## Fonctionnement détaillé

### Phase 1 : Extraction structurée

**Module** : document_extractor.py

**Processus** :
1. Analyse du document source (PDF ou DOCX)
2. Extraction du texte avec préservation de la hiérarchie
   - Détection des titres par analyse de taille de police (PDF) ou styles (DOCX)
   - Identification des paragraphes, listes, et tableaux
   - Maintien de l'ordre séquentiel du contenu
3. Extraction des images avec métadonnées
   - Données binaires de l'image
   - Position dans le document
   - Dimensions (largeur x hauteur)
   - Contexte textuel avant et après l'image (3 blocs chacun)
4. Filtrage automatique des petites images (< 100x100px par défaut)
   - Élimine les icônes, puces décoratives, logos de bas de page

**Bibliothèques utilisées** :
- PyMuPDF (fitz) pour les PDF
- python-docx pour les fichiers Word
- Pillow pour la manipulation d'images

**Modèle LLM** : Aucun à cette étape (traitement algorithmique)

### Phase 2 : Analyse intelligente des images

**Module** : image_analyzer.py

**Modèle utilisé** : LLaVA 13B (ou 34B) - Modèle multimodal vision + langage

**Processus pour chaque image** :
1. Encodage de l'image en base64
2. Construction d'un prompt incluant :
   - Instructions d'analyse structurée
   - Contexte textuel avant l'image (jusqu'à 3 paragraphes)
   - Contexte textuel après l'image (jusqu'à 3 paragraphes)
3. Appel au modèle LLaVA via Ollama
4. Réception d'une réponse JSON contenant :
   - Type d'image : diagram, chart, photo, screenshot, illustration, logo, decorative
   - Pertinence : booléen basé sur le contenu informatif
   - Confiance : score 0.0 à 1.0
   - Description : texte détaillé expliquant le contenu visuel
   - Présence de texte : détection de texte visible dans l'image
   - Texte extrait : OCR indirect via le modèle de vision

**Critères de pertinence** :
- Score de confiance >= 0.6 (paramétrable)
- Type non décoratif (exclut logo, decorative)
- Contenu technique ou informatif identifié

**Temps estimé** : 5-10 secondes par image selon le modèle

### Phase 3 : Génération du Markdown brut

**Module** : markdown_processor.py

**Modèle utilisé** : Aucun à cette étape (génération algorithmique)

**Processus** :
1. Construction de la structure Markdown
   - Titre principal (h1)
   - Métadonnées optionnelles
2. Parcours séquentiel des blocs de texte et images
3. Pour chaque bloc de type texte :
   - Conversion des titres en # selon leur niveau
   - Préservation des paragraphes
   - Conversion des tableaux en syntaxe Markdown
4. Pour chaque bloc de type image :
   - Si image pertinente : insertion de la description formatée
     ```markdown
     ---
     [Image N: type]
     Texte visible: ...
     Description: ...
     ---
     ```
   - Si image non pertinente : commentaire HTML invisible
     ```html
     <!-- Image N: décorative ou non pertinente -->
     ```

### Phase 4 : Enrichissement textuel (OPTIONNEL)

**Module** : markdown_processor.py

**Modèle utilisé** : Ministral 3 (14B) - Modèle de langage textuel

**Note importante** : Cette phase est OPTIONNELLE et peut être désactivée avec `--no-enrich` pour suivre strictement le pipeline original recommandé.

**Processus** :
1. Découpage du Markdown en chunks de 4096 tokens maximum
   - Découpage intelligent évitant de couper au milieu d'un paragraphe
   - Préservation de la cohérence contextuelle
2. Pour chaque chunk :
   - Construction d'un prompt avec le système prompt de structuration
   - Appel à Ministral 3 via Ollama
   - Réception du texte enrichi avec :
     - Formatage Markdown amélioré
     - Mise en évidence des éléments importants (gras)
     - Conservation de la précision technique
     - Structuration cohérente
3. Maintien du contexte conversationnel entre chunks
   - Historique des messages conservé
   - Continuité narrative assurée
4. Reconstitution du document complet

**Temps estimé** : 30-60 secondes par chunk selon la longueur

**Quand l'utiliser** :
- Documents avec structure peu claire → activer (par défaut)
- Documents déjà bien structurés → désactiver avec `--no-enrich` (plus rapide)
- Usage avec Delibia → désactiver recommandé (Markdown pur, pas de réécriture)

### Phase 5 : Sauvegarde

**Processus** :
1. Écriture du fichier Markdown final
   - Nommage : `document.ministral3_14b.md`
2. Sauvegarde optionnelle des images dans un sous-dossier `images/`
   - Format : `image_001.png`, `image_002.jpg`, etc.

## Appels aux modèles LLM - Synthèse

### Modèle de vision (LLaVA 13B ou 34B)

**Quand** : Phase 2, pour chaque image extraite

**Fréquence** : N appels (N = nombre d'images dans le document)

**Prompt type** :
```
Tu es un expert en analyse d'images de documents techniques.
Ton rôle est d'analyser une image et de fournir:
1. Type: Identifie le type (schéma, graphique, photo, logo, décoratif, etc.)
2. Pertinence: Est-ce pertinent pour la compréhension du document ? (oui/non)
3. Description: Si pertinent, fournis une description textuelle détaillée et technique de l'image.

Contexte avant l'image:
[texte des 3 paragraphes précédents]

Contexte après l'image:
[texte des 3 paragraphes suivants]

Format de réponse en JSON: {...}
```

**Entrée** : Image (base64) + contexte textuel

**Sortie** : JSON structuré avec classification et description

### Modèle de texte (Ministral 3 14B)

**Quand** : Phase 4, pour enrichir le Markdown

**Fréquence** : M appels (M = nombre de chunks, environ 1 par 3000 mots)

**Prompt type** :
```
Tu es un expert en structuration de documents techniques.
Ton rôle est de convertir du texte brut en Markdown bien structuré en :
- Préservant la hiérarchie des titres (h1, h2, h3...)
- Conservant les listes à puces et numérotées
- Formatant correctement les tableaux
- Mettant en évidence les éléments importants en gras
- Utilisant LaTeX pour les équations mathématiques
- Gardant le contenu technique précis et complet

Ne modifie pas le sens ou le contenu technique.

[contenu du chunk]
```

**Entrée** : Chunk de texte Markdown

**Sortie** : Texte Markdown enrichi et formaté

## Robustesse du système

### 1. Modularité

**Avantages** :
- Chaque module peut être testé indépendamment
- Remplacement facile d'un composant sans affecter les autres
- Maintenance simplifiée

**Implémentation** :
- document_extractor : responsable uniquement de l'extraction
- image_analyzer : responsable uniquement de l'analyse d'images
- markdown_processor : orchestration et génération

### 2. Gestion d'erreurs multi-niveaux

**Au niveau du traitement parallèle** :
- ThreadPoolExecutor isole les erreurs par document
- Un document en échec n'arrête pas le traitement des autres
- Logs détaillés pour chaque erreur

**Au niveau de l'analyse d'images** :
- Try-catch autour de chaque appel au modèle de vision
- Fallback vers une analyse par défaut en cas d'échec
- Image marquée comme "non pertinente" si erreur

**Au niveau de l'extraction** :
- Vérification de disponibilité des bibliothèques (PyMuPDF, python-docx)
- Messages d'erreur explicites en cas de dépendance manquante
- Import conditionnel avec gestion de ImportError

### 3. Filtrage intelligent

**Élimination du bruit** :
- Seuil de taille minimale pour les images (évite icônes, puces)
- Score de pertinence avec seuil configurable
- Classification par type (élimine logos, éléments décoratifs)

**Utilisation du contexte** :
- Analyse basée sur le texte environnant
- Améliore la précision de la classification
- Réduit les faux positifs

### 4. Performance optimisée

**Traitement parallèle** :
- MultiThreading pour traiter plusieurs documents simultanément
- Paramétrable (1 à N threads selon ressources)

**Évitement de retraitement** :
- Vérification de l'existence du fichier de sortie
- Skip automatique des documents déjà traités

**Découpage intelligent** :
- Chunks respectant les limites de tokens
- Évite de couper au milieu d'un paragraphe
- Maintien du contexte entre chunks

### 5. Confidentialité garantie

**Traitement local** :
- Ollama exécute les modèles localement
- Aucune donnée envoyée à des services externes
- Pas de dépendance à une connexion Internet (après téléchargement des modèles)

**Avantages** :
- Documents sensibles/confidentiels protégés
- Pas de limite d'utilisation (API payante)
- Contrôle total sur les données

## Points d'amélioration potentiels

### 1. Support de formats additionnels

**Actuellement** : PDF, DOCX

**À ajouter** :
- PowerPoint (PPTX)
  - Extraction slide par slide
  - Conversion des animations en descriptions textuelles
  - Extraction de notes du présentateur
- HTML enrichi
- Fichiers OpenDocument (ODT, ODP)

**Complexité** : Moyenne
**Priorité** : Haute pour PPTX

### 2. OCR avancé pour documents scannés

**Problème actuel** : 
- Les PDF scannés (images de pages) ne sont pas traités correctement
- Le texte n'est pas extractible

**Solution proposée** :
- Intégration de Tesseract OCR
- Détection automatique de PDF image vs PDF texte
- Preprocessing d'image (deskew, denoising)

**Complexité** : Moyenne
**Priorité** : Moyenne

### 3. Détection et extraction de tableaux complexes

**Problème actuel** :
- Tableaux complexes mal convertis en Markdown
- Perte de structure pour tableaux imbriqués ou fusionnés

**Solution proposée** :
- Bibliothèque spécialisée (Camelot, Tabula)
- Détection de structure de tableau via vision LLM
- Conversion intelligente en Markdown ou HTML

**Complexité** : Haute
**Priorité** : Moyenne

### 4. Cache des analyses d'images

**Problème actuel** :
- Réanalyse des mêmes images si retraitement du document
- Temps de traitement long pour documents avec nombreuses images

**Solution proposée** :
- Hash MD5 de chaque image extraite
- Stockage des analyses dans une base de données SQLite locale
  ```
  cache.db:
    - image_hash (clé)
    - analysis_json
    - timestamp
  ```
- Lookup avant analyse, fallback si absent

**Complexité** : Faible
**Priorité** : Haute
**Gain estimé** : 50-70% de réduction du temps sur documents réanalysés

### 5. Amélioration des prompts

**Approche actuelle** : Prompts génériques

**Améliorations** :
- Prompts spécialisés par type de document
  - Documents techniques : focus sur schémas architecturaux
  - Rapports financiers : focus sur graphiques et tableaux de chiffres
  - Manuels utilisateur : focus sur captures d'écran et workflows
- Prompts adaptatifs basés sur le contexte détecté
- Fine-tuning des prompts basé sur des retours utilisateurs

**Complexité** : Faible à Moyenne
**Priorité** : Moyenne

### 6. Détection de la langue du document

**Problème actuel** :
- Prompts en français uniquement
- Descriptions peuvent être incohérentes pour documents en anglais

**Solution proposée** :
- Détection automatique de langue (langdetect)
- Prompts multilingues (français, anglais, allemand, etc.)
- Descriptions générées dans la langue du document source

**Complexité** : Faible
**Priorité** : Moyenne

### 7. Export multi-formats

**Actuellement** : Markdown uniquement

**À ajouter** :
- HTML enrichi avec CSS
- PDF enrichi (via LaTeX ou weasyprint)
- Format JSON structuré (pour intégration dans pipelines data)
- Format DOCX enrichi (avec descriptions d'images en légendes)

**Complexité** : Moyenne
**Priorité** : Faible à Moyenne

### 8. Interface utilisateur

**Actuellement** : CLI uniquement

**Options** :
- Interface web locale (Flask/FastAPI + HTML)
  - Upload de documents
  - Configuration des paramètres
  - Preview en temps réel
  - Téléchargement des résultats
- Application desktop (Electron ou Tkinter)
- Extension VS Code

**Complexité** : Moyenne à Haute
**Priorité** : Faible (CLI suffisant pour usage technique)

### 9. Métriques et monitoring

**À implémenter** :
- Temps de traitement par phase
- Taux de pertinence des images détectées
- Taux de réussite des analyses
- Statistiques agrégées (nombre de documents traités, images analysées, etc.)
- Export des métriques en JSON/CSV pour analyse

**Complexité** : Faible
**Priorité** : Moyenne

### 10. Mode batch avancé

**Améliorations** :
- Watch mode : surveillance d'un dossier et traitement automatique des nouveaux documents
- Priorités de traitement (documents importants en premier)
- Retry automatique en cas d'échec
- Notifications (email, webhook) à la fin du traitement

**Complexité** : Moyenne
**Priorité** : Faible

### 11. Support GPU plus large

**Actuellement** : Support GPU via Ollama (CUDA pour NVIDIA)

**Améliorations** :
- Support AMD ROCm
- Support Apple Silicon (Metal)
- Optimisation pour GPU multiples
- Quantization des modèles pour réduire l'empreinte mémoire

**Complexité** : Dépend de Ollama
**Priorité** : Faible (géré par Ollama)

### 12. Validation de la qualité des descriptions

**Problème potentiel** :
- Descriptions d'images parfois imprécises ou génériques
- Pas de feedback loop

**Solution proposée** :
- Score de qualité de description (cohérence avec le contexte)
- Comparaison avec un modèle de référence (GPT-4 Vision API en validation)
- Interface de feedback utilisateur
- Ré-analyse automatique si score faible

**Complexité** : Haute
**Priorité** : Faible

## Limitations actuelles

### 1. Dépendance à Ollama
- Nécessite Ollama installé et en cours d'exécution
- Limité aux modèles supportés par Ollama

### 2. Performance sur grands documents
- Documents de 100+ pages peuvent prendre 30-60 minutes
- Mémoire importante requise pour documents avec nombreuses images

### 3. Qualité variable selon le modèle de vision
- LLaVA 7B : rapide mais moins précis
- LLaVA 34B : précis mais lent et gourmand en mémoire
- Pas de support fin-tuning facile

### 4. Tableaux complexes
- Tableaux avec fusions de cellules mal gérés
- Tableaux sur plusieurs pages perdent la continuité

### 5. Équations mathématiques
- Extraction correcte depuis PDF
- Mais reconversion en LaTeX peut être imparfaite

## Configuration système recommandée

### Minimum (test)
- CPU : 4 cores
- RAM : 16 GB
- Stockage : 20 GB
- Modèles : LLaVA 7B + Ministral 3 14B

### Production (usage intensif)
- CPU : 8+ cores ou GPU NVIDIA (RTX 3060+)
- RAM : 32 GB
- Stockage : 50 GB SSD
- Modèles : LLaVA 13B ou 34B + Ministral 3 14B

### Haute performance
- CPU : 12+ cores ou GPU NVIDIA (RTX 4090, A100)
- RAM : 64 GB
- Stockage : 100 GB NVMe SSD
- Modèles : LLaVA 34B + Ministral 3 14B

## Temps de traitement estimés

### Document type : rapport de 20 pages, 5 images

**Sans analyse d'images** :
- Extraction : 10-15 secondes
- Génération Markdown : 5 secondes
- Enrichissement LLM : 2-3 minutes
- **Total : 2-4 minutes**

**Avec analyse d'images (LLaVA 13B)** :
- Extraction : 10-15 secondes
- Analyse d'images : 30-50 secondes (5 images x 6-10s)
- Génération Markdown : 5 secondes
- Enrichissement LLM : 2-3 minutes
- **Total : 3-5 minutes**

**Avec analyse d'images (LLaVA 34B)** :
- Extraction : 10-15 secondes
- Analyse d'images : 50-90 secondes (5 images x 10-18s)
- Génération Markdown : 5 secondes
- Enrichissement LLM : 2-3 minutes
- **Total : 4-6 minutes**

### Facteurs d'accélération

**GPU vs CPU** :
- GPU NVIDIA : 3-5x plus rapide
- Apple Silicon (M1/M2/M3) : 2-3x plus rapide

**Parallélisation** :
- 4 threads : 3-4x plus rapide pour batch de documents
- 8 threads : 6-7x plus rapide (avec ressources suffisantes)

## Conclusion

Ce système offre une solution robuste et locale pour pré-traiter des documents techniques en vue de leur utilisation par des LLM. La combinaison d'extraction structurée, d'analyse intelligente d'images, et d'enrichissement textuel permet de transformer des documents complexes en Markdown exploitable tout en préservant l'information visuelle essentielle.

Les principaux avantages sont la modularité, la confidentialité (traitement local), et la qualité des transcriptions d'images grâce aux modèles multimodaux. Les améliorations futures pourront se concentrer sur l'extension des formats supportés, l'optimisation des performances via un système de cache, et l'amélioration continue des prompts pour des descriptions encore plus précises.
