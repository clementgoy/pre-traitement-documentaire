# 📚 Pré-traitement Documentaire Intelligent

Système de pré-traitement de ressources documentaires avec transcription intelligente pour améliorer l'assimilation par les modèles de langage (LLM).

## 🎯 Objectifs

Ce projet permet de convertir des documents (PDF, DOCX) en Markdown structuré avec :
- **Fidélité absolue** : Préservation intégrale du texte source, mot pour mot (mode strict)
- **Extraction intelligente** : Préservation de la hiérarchie (titres, sections, listes, tableaux)
- **Analyse d'images** : Détection automatique de la pertinence des schémas, graphiques et images
- **Transcription factuelle** : Description textuelle détaillée uniquement de ce qui est visible
- **Filtrage intelligent** : Élimination des éléments décoratifs et des templates
- **Aucune invention** : Pas de reformulation, synthèse ou interprétation du contenu
- **Optimisé pour RAG** : Markdown pur compatible avec tous les systèmes de chunking (Delibia, etc.)

## 🏗️ Architecture

### Modules principaux

```
├── main.py                   # Orchestrateur principal
├── config.py                 # Configuration centralisée
├── document_extractor.py     # Extraction de contenu (PDF/DOCX)
├── image_analyzer.py         # Analyse intelligente d'images
├── markdown_processor.py     # Génération de Markdown enrichi
└── notes_generator.py        # Conversion de notes brutes (ancien système)
```

### Pipeline de traitement

```
Document (PDF/DOCX)
    ↓
1. Extraction (document_extractor.py)
    ├── Texte structuré (titres, paragraphes, tables)
    └── Images + contexte textuel
    ↓
2. Analyse d'images (image_analyzer.py)
    ├── Classification (schéma, graphique, photo, décoratif)
    ├── Évaluation de pertinence
    └── Génération de description textuelle
    ↓
3. Génération Markdown (markdown_processor.py)
    ├── Structure hiérarchique préservée
    ├── Descriptions d'images intégrées
    └── Enrichissement via LLM
    ↓
Markdown enrichi (.md)
```

## 📋 Prérequis

### 1. Installation d'Ollama

Ollama doit être installé et en cours d'exécution :

**Windows:**
```powershell
# Télécharger depuis https://ollama.ai/download
# Ou via winget:
winget install Ollama.Ollama
```

**Linux/Mac:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### 2. Téléchargement des modèles

```bash
# Modèle de texte (obligatoire)
ollama pull ministral3:14b

# Modèle de vision pour l'analyse d'images (recommandé)
ollama pull llava:13b

# Alternatives pour le modèle de vision:
# ollama pull llava:34b      # Plus précis mais plus lent
# ollama pull bakllava       # Version optimisée
```

### 3. Dépendances Python

```bash
python -m venv .venv
.venv/Scripts/Activate

pip install -r requirements.txt
```

## 🚀 Utilisation

### Mode recommandé : STRICT (pour Delibia et RAG)

Garantie de fidélité absolue, aucune reformulation, aucune invention.

```bash(mode strict recommandé)** :
```bash
python main.py doc_to_markdown 4 --strict
```

**Paramètres** :
- `4` : Nombre de threads (traitement parallèle)
- `--strict` : Mode fidélité absolue (recommandé pour Delibia)
- ✅ Correction syntaxe Markdown seulement (# pour titres, - pour listes, | | pour tableaux)
- ❌ Aucune reformulation, aucune interprétation, aucun ajout

**Temps** : ~1-2 minutes pour 20 pages + 5 images

---

### Mode 1: Traitement de documents enrichis (NOUVEAU)

Convertit des PDF/DOCX en Markdown avec analyse d'images.

**Utilisation basique :**
```bash
python main.py doc_to_markdown 4
```

**Paramètres :**
- `4` : Nombre de threads (traitement parallèle)

**Options avancées :**
```bash
python main.py doc_to_markdown <threads> [options]

Options:
  --text-model <model>      Modèle de texte (défaut: ministral3:14b)
  --vision-model <model>    Modèle de vision (défaut: llava:13b)
  --input <folder>          Dossier d'entrée (défaut: docs-bruts)
  --output <folder>         Dossier de sortie (défaut: docs-traites)
  --no-images               Désactiver l'analyse d'images
  --strict                  Mode STRICT : fidélité absolue, aucune reformulation (RECOMMANDÉ pour Delibia)
  --no-enrich               Désactiver l'enrichissement LLM (pipeline original)
```

**Exemples :**

``Recommandé pour Delibia : mode strict, fidélité absolue
python main.py doc_to_markdown 4 --strict

# Mode strict avec modèle vision plus puissant
python main.py doc_to_markdown 2 --strict --vision-model llava:34b

# Sans analyse d'images (plus rapide, documents textuels)
python main.py doc_to_markdown 4 --strict --no-images

# Mode standard (peut améliorer légèrement la structure)
python main.py doc_to_markdown 4
python main.py doc_to_markdown 2 --text-model ministral3:14b --vision-model llava:34b

# Dossiers personnalisés
python main.py doc_to_markdown 2 --input mes-docs --output exports-md

# Sans analyse d'images (plus rapide)
python main.py doc_to_markdown 4 --no-images

# Pipeline original strict (sans enrichissement LLM)
python main.py doc_to_markdown 4 --no-enrich

# Markdown pur pour Delibia (extraction + analyse images uniquement)
python main.py doc_to_markdown 4 --no-enrich
```

### Mode 2: Conversion de notes brutes (ANCIEN)

Convertit des fichiers `.raw.txt` en notes structurées.

```bash
python main.py raw_to_notes <threads> <model> <folder>
```

**Exemple :**
```bash
python main.py raw_to_notes 4 ministral3:14b docs-bruts
```

## ⚙️ Configuration

Modifiez [config.py](config.py) pour personnaliser :

```python
# Modèles
TEXT_MODEL = "ministral3:14b"
VISION_MODEL = "llava:13b"

# Seuil de pertinence des images (0.0 à 1.0)
RELEVANCE_THRESHOLD = 0.6

# Taille minimale des images à traiter (évite les icônes)
MIN_IMAGE_SIZE = (100, 100)

# Dossiers
INPUT_FOLDER = "docs-bruts"
OUTPUT_FOLDER = "docs-traites"
```

## 📊 Formats supportés

| Format | Extension | Extraction texte | Extraction images | Statut |
|--------|-----------|------------------|-------------------|--------|
| PDF | `.pdf` | ✅ Complet | ✅ Complet | ✅ Stable |
| Word | `.docx` | ✅ Complet | ✅ Complet | ✅ Stable |
| Word ancien | `.doc` | ⚠️ Partiel | ⚠️ Partiel | ⚠️ Expérimental |
| PowerPoint | `.pptx` | 🔄 À venir | 🔄 À venir | 🔄 En développement |

## 🔍 Analyse d'images

Le système analyse automatiquement chaque image pour :

### 1. Classification
- **Schéma technique** : Diagrammes, architectures, flowcharts
- **Graphique** : Charts, histogrammes, courbes
- **Capture d'écran** : Screenshots d'interface
- **Photo** : Photographies
- **Logo/Décoratif** : Éléments non pertinents

### 2. Évaluation de pertinence
Score de confiance (0.0 à 1.0) basé sur :
- Complexité visuelle
- Présence de texte technique
- Contexte textuel environnant
- Taille et qualité

### 3. Transcription
Pour les images pertinentes :
- Description textuelle détaillée
- Extraction du texte visible (OCR)
- Explication du schéma/graphique

**Exemple de sortie :**
```markdown
---

**[Image 1: schéma technique]**

*Texte visible:*
> Service A → API Gateway → Service B

*Description:*
Architecture microservices montrant la communication entre deux services via une
API Gateway. Le Service A envoie des requêtes HTTP au Gateway qui les route vers
le Service B. Présence d'un load balancer et d'une base de données PostgreSQL.

---
``` Enrichissement LLM |
|-----------|-----------------|---------|----------------|---------------------|
| **Rapide (pipeline original)** | Delibia, chunking externe | 4-8 | ✅ llava:13b | ❌ --no-enrich |
| **Équilibré** | Usage général | 2-4 | ✅ llava:13b | ✅ Par défaut |
| **Qualité max** | Documents techniques complexes | 1-2 | ✅ llava:34b | ✅ Par défaut |
| **Ultra-rapide** | Documents textuels simples | 4-8 | ❌ --no-images | ❌ --no-enrich

| Stratégie | Recommandé pour | Threads | Analyse images |
|-----------|-----------------|---------|----------------|
| **Pipeline original strict (--no-enrich)** : ~1-2 minutes
- **Rapide** | Documents textuels simples | 4-8 | ❌ --no-images |
| **Équilibré** | Usage général | 2-4 | ✅ llava:13b |
| **Qualité max** | Documents techniques complexes | 1-2 | ✅ llava:34b |

### Temps de traitement estimé

Pour un document de 20 pages avec 5 images :
- **Sans analyse d'images** : ~2-3 minutes
- **Avec analyse (llava:13b)** : ~8-12 minutes
- **Avec analyse (llava:34b)** : ~15-20 minutes

### Amélioration des performances

1. **GPU recommandé** pour Ollama (3x plus rapide)
2. **Limiter le nombre de threads** si mémoire limitée
3. **Pré-filtrer les images** en ajustant `MIN_IMAGE_SIZE`
4. **Désactiver l'analyse d'images** pour documents textuels simples

## 🛠️ Dépannage

### Problème : Modèle Ollama non trouvé
```
Solution : ollama pull <nom-du-modele>
```

### Problème : Mémoire insuffisante
```bash
# Réduire le nombre de threads
python main.py doc_to_markdown 1

# Ou utiliser un modèle plus léger
python main.py doc_to_markdown 2 --vision-model llava:7b
```

### Problème : Images mal analysées
```python
# Dans config.py, ajuster le seuil
RELEVANCE_THRESHOLD = 0.7  # Plus strict (défaut: 0.6)
MIN_IMAGE_SIZE = (150, 150)  # Filtrer les petites images
```

### Problème : Erreur PyMuPDF
```bash
pip install --upgrade pymupdf
```

## 📝 Exemples de résultats

### Avant (PDF source)
```
[Image de schéma technique non décrite]
Le système utilise une architecture microservices.
[Graphique de performance]
```

### Après (Markdown enrichi)
```markdown
---

**[Image 1: schéma technique]**

*Description:*
Architecture microservices avec 5 composants principaux: Frontend (React),
API Gateway (Kong), Services métier (Node.js), Base de données (PostgreSQL),
et Cache (Redis). Communication via REST et événements asynchrones.

---

Le système utilise une architecture microservices permettant une scalabilité
horizontale et un déploiement indépendant de chaque service.

---

**[Image 2: graphique]**

*Description:*
Graphique en courbes montrant l'évolution des performances sur 6 mois.
Temps de réponse moyen passé de 250ms à 80ms après optimisation.
Amélioration notable à partir du mois 3 suite à l'ajout du cache Redis.

---
```

## 🔄 Évolutions futures

- [ ] Support PowerPoint (PPTX)
- [ ] Export multi-formats (HTML, PDF enrichi)
- [ ] Interface web
- [ ] Détection automatique de la langue
- [ ] Support tableaux complexes
- [ ] OCR avancé pour images scannées

## 🤝 Contribution

Pour améliorer le système :
1. Testez avec vos documents
2. Ajustez les paramètres dans `config.py`
3. Signalez les bugs ou limitations
4. Proposez des améliorations

## 📄 Licence

Ce projet est destiné à un usage interne pour le pré-traitement de ressources documentaires.

## 📧 Support

Pour toute question ou problème, consultez la documentation d'Ollama :
- https://ollama.ai/
- https://github.com/ollama/ollama

---

**Note importante** : L'analyse d'images nécessite un modèle multimodal (LLaVA, BakLLaVA) et peut être gourmande en ressources. Pour des tests rapides, utilisez l'option `--no-images`.
traitement de documenttion sous plusieurs formats afin d'en améliorer la lisibilité par des modèles de langages.

## Pre-recquis :

Python 3.12.10 (ou supérieur)



## Process lancement projet :

1. Cloner le projet depuis le dépôt GitHub : `git clone https://github.com/clementgoy/pre-traitement-documentaire`
2. Créer un environnement virtuel : `python -m venv env`
3. Activer l environnement virtuel :
   - Sur Windows : `.\env\Scripts\activate`
   - Sur macOS/Linux : `source env/bin/activate`
4. Installer les dépendances : `pip install -r requirements.txt`
5. Lancer le script de pré-traitement : 