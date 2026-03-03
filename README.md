# doc2md — Convertisseur de documents vers Markdown

Outil de conversion **PDF / DOCX / PPTX → Markdown** via un modèle de vision local (Ollama).

Pour les PDF et PPTX, un classificateur automatique analyse chaque page et choisit le
mode de traitement optimal : extraction texte pure, détection de tableaux, ou analyse
visuelle complète. Tableaux, schémas, organigrammes et mises en page complexes sont
retranscrits fidèlement en Markdown structuré. Les éléments décoratifs (logos, photos)
sont ignorés. Pour les DOCX, la structure native (styles Word, tableaux) est utilisée.

---

## Prérequis

| Outil | Version minimale | Vérification |
|---|---|---|
| Python | 3.10+ | `python --version` |
| [Ollama](https://ollama.com) | 0.16+ | `ollama --version` |
| Modèle de vision | `qwen2.5vl:latest` | `ollama list` |
| [LibreOffice](https://www.libreoffice.org/download/) *(optionnel)* | 7.0+ | `soffice --version` |
| [Pandoc](https://pandoc.org/installing.html) | 3.0+ | `pandoc --version` |

> **Pandoc** est nécessaire pour la conversion Markdown → DOCX (`convert-md-to-docx.py`).
> Si Pandoc n'est pas installé sur le système, il est **téléchargé automatiquement**
> lors du premier lancement du script (via `pypandoc.download_pandoc()`).
> Vous pouvez aussi l'installer manuellement depuis [pandoc.org](https://pandoc.org/installing.html).

> **Note Windows** : les commandes ci-dessous utilisent Git Bash (syntaxe Unix).
> Dans un terminal CMD ou PowerShell, `venv/Scripts/python.exe` reste identique.

> **LibreOffice** est nécessaire pour la conversion de qualité des fichiers PPTX
> (rendu visuel complet des diapositives). Sans lui, les slides sont traités shape
> par shape — les éléments vectoriels (flèches, connecteurs de schémas) ne sont pas capturés.

---

## Installation

### 1. Installer Ollama et le modèle de vision

Téléchargez Ollama sur [ollama.com](https://ollama.com), installez-le, puis
téléchargez le modèle recommandé :

```bash
ollama pull qwen2.5vl
```

> Le téléchargement pèse environ 6 Go. N'utilisez **pas** les modèles `llava`
> ni `minicpm-v` : ils sont incompatibles avec Ollama 0.16+ (sorties corrompues).

### 2. (Recommandé) Installer LibreOffice

Pour une conversion PPTX de qualité, installez LibreOffice :
[libreoffice.org/download](https://www.libreoffice.org/download/)

L'outil le détecte automatiquement — aucune configuration supplémentaire.

### 3. Créer l'environnement virtuel Python

Depuis le répertoire du projet :

```bash
# Linux / macOS / Git Bash (Windows)
bash setup_env.sh

# Ou manuellement :
python -m venv venv
venv/Scripts/python.exe -m pip install --upgrade pip
venv/Scripts/python.exe -m pip install -r requirements.txt
```

### 4. Vérifier l'installation

```bash
venv/Scripts/python.exe convert.py --list-models
```

Vous devriez voir `qwen2.5vl:latest [vision]` dans la liste.

---

## Utilisation

### Démarrer Ollama (si ce n'est pas déjà fait)

```bash
ollama serve
```

Laissez ce terminal ouvert pendant toute la durée des conversions.

---

### Convertir un fichier unique

```bash
# PDF → Markdown (avec analyse visuelle, par défaut)
venv/Scripts/python.exe convert.py doc-raw/monDocument.pdf

# DOCX → Markdown avec sortie explicite
venv/Scripts/python.exe convert.py doc-raw/rapport.docx -o doc-md/rapport.md

# PPTX → Markdown sans modèle de vision (extraction texte rapide)
venv/Scripts/python.exe convert.py doc-raw/presentation.pptx --no-images
```

Le fichier Markdown est créé dans **`doc-md/`** par défaut
(même nom que la source, extension `.md`).

---

### Convertir un dossier entier

```bash
# Convertit tous les PDF/DOCX/PPTX du dossier doc-raw/
venv/Scripts/python.exe convert.py doc-raw/

# Avec dossier de sortie explicite
venv/Scripts/python.exe convert.py doc-raw/ -o doc-md/

# Sans modèle de vision (test rapide, texte uniquement)
venv/Scripts/python.exe convert.py doc-raw/ --no-images
```

---

### Toutes les options

```
python convert.py <fichier_ou_dossier> [options]

Arguments :
  fichier_ou_dossier    Chemin vers un fichier PDF/DOCX/PPTX, ou un dossier

Options :
  -o, --output CHEMIN   Fichier .md de sortie (mode fichier) ou dossier (mode dossier)
  --vision-model NOM    Modèle Ollama de vision (défaut : qwen2.5vl:latest)
  --no-images           Désactiver le modèle de vision (extraction texte rapide)
  --list-models         Afficher les modèles Ollama disponibles et quitter
  -q, --quiet           Mode silencieux (pas de messages de progression)
  -h, --help            Afficher l'aide
```

---

## Comment ça fonctionne

### PDF (mode vision)

Chaque page est analysée par un classificateur rapide (PyMuPDF, sans LLM) qui choisit
le mode de traitement optimal :

| Mode | Déclenchement | Traitement |
|---|---|---|
| **vision** | Schémas, infographies, mise en page complexe (>20 blocs), images avec texte superposé | Rendu page 150 DPI → `qwen2.5vl` (1024 px, 3000 tokens) |
| **hybride** | Page mixant texte extractible et images secondaires (captures d'écran, icônes) | Texte extrait par PyMuPDF + images décrites individuellement (512 px) |
| **tableau** | Tableaux structurés détectés (≥2 lignes×colonnes), page simple | `find_tables()` PyMuPDF → GFM |
| **texte** | Pages simples sans tableau ni image significative | Extraction blocs PyMuPDF |

Le mode **hybride** combine le meilleur des deux approches : le texte est reproduit mot
pour mot (sans hallucination), et les images embarquées sont décrites individuellement.
Il est préféré au mode vision quand du texte extractible coexiste avec des captures d'écran.

Le mode **vision** (le plus fidèle visuellement) couvre :
- Schémas de processus, flowcharts, organigrammes
- Infographies à étapes numérotées, mises en page multi-zones
- Pages denses ou à fort nombre de blocs texte

Sur un document typique, le classificateur évite en moyenne **25-30% des appels au modèle**
sans perte de qualité. En cas de timeout, relance automatique à 512 px.

### PPTX (mode vision)

1. Conversion de la présentation en PDF via **LibreOffice** (si installé)
2. Traitement page par page identique au pipeline PDF ci-dessus

Sans LibreOffice : extraction shape par shape dans l'ordre visuel.
Les éléments vectoriels (flèches, formes, connecteurs) ne sont pas capturés dans ce mode.

### DOCX

Structure native utilisée directement (styles Word, paragraphes, tableaux GFM).
Pas de rendu visuel nécessaire — qualité optimale sans modèle de vision.

### Mode `--no-images`

Extraction rapide du texte via PyMuPDF (PDF) ou python-pptx (PPTX), sans aucun appel
au modèle. Utile pour vérifier la mise en forme ou traiter des documents purement textuels.

---

## Format de sortie

Chaque fichier Markdown généré commence par un en-tête automatique :

```markdown
# nom-du-fichier

*Source : nom-du-fichier.pdf (PDF) — Modèle vision : `qwen2.5vl:latest`*

---
```

Puis le contenu page par page (PDF/PPTX) ou section par section (DOCX),
avec les séparateurs `---` entre pages/diapositives.

---

## Test rapide

```bash
# Test sans modèle de vision (rapide, ~5 secondes)
venv/Scripts/python.exe convert.py doc-raw/guideAchatSimplifie.pdf --no-images -o doc-md/test-rapide.md

# Test complet avec analyse visuelle page par page
venv/Scripts/python.exe convert.py doc-raw/guideAchatSimplifie.pdf -o doc-md/guideAchatSimplifie.md
```

Consultez ensuite `doc-md/guideAchatSimplifie.md` pour vérifier le résultat.

---

## Structure du projet

```
pre-traitement-documentaire/
├── convert.py              # CLI principal : PDF/DOCX/PPTX → Markdown
├── convert-md-to-docx.py  # CLI secondaire : Markdown → DOCX (pour Delibia)
├── requirements.txt        # Dépendances Python
├── setup_env.sh            # Script d'installation (Git Bash Windows / Linux / macOS)
├── src/
│   ├── page_transcriber.py # Prompt + fonction de transcription page → Markdown
│   ├── pdf_parser.py       # Parser PDF : rendu page → vision (ou texte en --no-images)
│   ├── docx_parser.py      # Parser Word : styles natifs + tableaux GFM
│   ├── pptx_parser.py      # Parser PPTX : LibreOffice → PDF → vision (ou shapes)
│   ├── image_analyzer.py   # Analyse d'images individuelles (fallback PPTX sans LibreOffice)
│   └── ollama_client.py    # Client HTTP Ollama — resize auto 1024px
├── doc-raw/                # Dossier source (documents originaux)
├── doc-md/                 # Dossier intermédiaire (Markdown générés)
└── doc-docx/               # Dossier de sortie final (DOCX pour Delibia)
```

---

## Dépendances Python

| Paquet | Rôle |
|---|---|
| `PyMuPDF` | Rendu des pages PDF en images + extraction texte (mode --no-images) |
| `python-docx` | Lecture des fichiers Word (.docx) |
| `python-pptx` | Lecture des fichiers PowerPoint (.pptx) |
| `Pillow` | Traitement des images (conversion, redimensionnement) |
| `requests` | Communication HTTP avec l'API Ollama |
| `pypandoc` | Conversion Markdown → DOCX (wrappeur Python autour de pandoc) |

---

## Conversion Markdown → DOCX (pour Delibia)

La plateforme **Delibia** ne supporte pas les fichiers `.md`. Le script `convert-md-to-docx.py`
convertit les fichiers Markdown produits par `convert.py` en `.docx` via Pandoc.

### Utilisation

```bash
# Convertir un dossier entier doc-md/ → doc-docx/
venv/Scripts/python.exe convert-md-to-docx.py --src doc-md/ --dst doc-docx/

# Convertir un fichier unique
venv/Scripts/python.exe convert-md-to-docx.py --file doc-md/monDocument.md

# Convertir un fichier unique avec sortie explicite
venv/Scripts/python.exe convert-md-to-docx.py --file doc-md/monDocument.md --out doc-docx/monDocument.docx

# Convertir tous les .md d'un dossier en place (même dossier)
venv/Scripts/python.exe convert-md-to-docx.py --dir doc-md/
```

### Workflow complet

```
doc-raw/  →[convert.py]→  doc-md/  →[convert-md-to-docx.py]→  doc-docx/
(PDF/DOCX/PPTX)           (Markdown)                            (DOCX → Delibia)
```

> Si Pandoc n'est pas installé, le script le télécharge automatiquement au premier lancement.

---

## Problèmes fréquents

**Ollama inaccessible**
```
Erreur : Ollama n'est pas accessible sur http://localhost:11434
```
→ Lancez `ollama serve` dans un terminal séparé.

---

**Timeout sur une page**
```
erreur — HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=600)
```
→ Le modèle n'a pas répondu dans les 600 s allouées à l'encodage de l'image.
Le pipeline relance automatiquement la page en résolution réduite (512 px au lieu de 1024 px),
ce qui accélère l'encodage d'environ 75 %.

Si le retry échoue aussi, la page est marquée dans le Markdown :
`> *(Page X — non transcrite : ReadTimeout)*`

**Note technique** : le client utilise le mode streaming d'Ollama. Le timeout de 600 s
s'applique au silence entre deux tokens générés, pas à la durée totale de génération.
Un organigramme dense peut donc être transcrit même s'il prend 15+ minutes, tant que
le modèle continue de produire des tokens.

---

**Modèle de vision absent**
```
Avertissement : le modèle 'qwen2.5vl:latest' n'est pas installé.
```
→ Exécutez `ollama pull qwen2.5vl` puis relancez.

---

**PPTX : schémas non capturés**
```
LibreOffice non trouvé — extraction par shapes (les schémas vectoriels ne seront pas capturés).
```
→ Installez LibreOffice depuis [libreoffice.org/download](https://www.libreoffice.org/download/)

---

**Format de fichier non supporté**
```
Erreur : le format '.doc' (ancien format binaire) n'est pas supporté.
```
→ Ouvrez le fichier dans Microsoft Office ou LibreOffice et enregistrez-le en `.docx` ou `.pptx`.

---

## Performances indicatives

Le modèle de vision traite **une page à la fois**. Repères sur une machine
avec 21 Go de RAM et sans GPU dédié (CPU uniquement) :

| Document | Pages/Slides | Avec vision | Sans vision (`--no-images`) |
|---|---|---|---|
| PDF simple (texte, titres) | 10 | ~3-5 min | ~5 sec |
| PDF dense (tableaux, schémas) | 75 | ~25-35 min | ~30 sec |
| PPTX 20 slides (avec LibreOffice) | 20 | ~10-20 min | ~10 sec |

> **Repères machine** : 21 Go RAM, sans GPU dédié (CPU uniquement). Les temps varient
> selon la densité des pages — le classificateur automatique évite ~25% des appels modèle.

Utilisez `--no-images` pour des tests de mise en forme rapides.
La conversion avec vision est longue mais produit un Markdown fidèle et exploitable par un LLM.
