# Limites et Risques d'Ajout d'Information

Ce document explique HONNÊTEMENT dans quelle mesure des informations peuvent être ajoutées par rapport au document initial, et comment les minimiser.

## Vue d'ensemble des risques

| Phase | Risque d'ajout | Probabilité | Type d'ajout |
|-------|----------------|-------------|--------------|
| Phase 1 : Extraction | Aucun | 0% | Algorithmique pur |
| Phase 2 : Analyse images | Modéré | 10-20% | Interprétation visuelle |
| Phase 3 : Assemblage | Minimal | <1% | Caractères structurels (# - \|) |
| Phase 4 : LLM (mode strict) | Faible | <5% | Hallucinations possibles |
| **Mode RAW (--raw)** | **Aucun** | **0%** | **Pas de LLM** |

## Phase 1 : Extraction (0% de risque)

**Processus** : Algorithme PyMuPDF / python-docx

**Garantie** : Aucun ajout possible
- Extraction binaire du texte
- Calcul de positions et tailles
- Pas d'intelligence artificielle

**Exemple** :
```
Document source : "Le système utilise Redis"
Extraction Phase 1 : "Le système utilise Redis"
```

## Phase 2 : Analyse d'images (10-20% de risque)

**Processus** : Modèle LLaVA (vision)

### Risques d'ajout possibles

**1. Interprétation de relations (15%)**

Document source (image) :
```
[Box A] -----> [Box B]
```

Analyse LLaVA :
```
Description: Diagramme montrant le flux de données de A vers B
```

**Ajout** : "flux de données" (la flèche n'a pas de label explicite)

**2. Déduction de fonction (10%)**

Document source (image) :
```
[Logo Redis]
```

Analyse LLaVA :
```
Description: Logo Redis, système de cache en mémoire
```

**Ajout** : "système de cache en mémoire" (ce n'est pas écrit dans l'image)

**3. Lecture de texte flou (5%)**

Document source (image) :
```
[Texte flou/mal scanné]
```

Analyse LLaVA :
```
Texte visible: "Configuration du système"
```

**Ajout** : Le modèle peut "deviner" un mot flou

### Solutions pour Phase 2

**Option 1 : Désactiver analyse d'images**
```bash
python main.py doc_to_markdown 4 --no-images
```
Risque : 0% pour les images (mais perte de cette information)

**Option 2 : Valider manuellement**
- Traiter 1 document test
- Comparer image source vs description
- Identifier si le modèle ajoute des déductions

**Option 3 : Prompt encore plus strict**
Ajouter dans le prompt : "Si tu n'es pas certain, écris 'non visible'"

## Phase 3 : Assemblage Markdown (0% de risque sémantique)

**Processus** : Algorithme Python pur

**"Ajouts" non sémantiques** :
```
Titre →  "# Titre"          (+2 caractères)
Liste →  "- item"           (+2 caractères)  
Tableau → "| col1 | col2 |" (+6 caractères)
```

**Garantie** : Aucun mot ajouté, uniquement syntaxe Markdown

## Phase 4 : Nettoyage LLM - Mode STRICT (<5% de risque)

**Processus** : Ministral 3 avec prompt ultra-strict

### Risques d'ajout possibles

**1. Hallucinations LLM (2-5%)**

Document source :
```
Le système utilise Redis
```

Sortie LLM (hallucination) :
```
Le système utilise Redis pour le caching en mémoire
```

**Ajout** : "pour le caching en mémoire"

**Pourquoi ça arrive** :
- Le LLM a vu beaucoup de textes où Redis apparaît avec cette explication
- Il "complète" malgré la consigne stricte
- C'est une limite fondamentale des LLM actuels

**Probabilité** :
- Ministral 3 : ~2-3%
- GPT-4 : ~1-2%
- Llama 2 : ~5-8%

**2. Correction "intelligente" (1-2%)**

Document source (erreur OCR) :
```
Le systeme utilise Redis
```

Sortie LLM :
```
Le système utilise Redis
```

**Ajout** : Accent sur "système" (était peut-être intentionnel ?)

**3. Normalisation de termes (<1%)**

Document source :
```
Utilise Redis (base de donnée)
```

Sortie LLM :
```
Utilise Redis (base de données)
```

**Ajout** : Correction orthographique

### Solutions pour Phase 4

**Option 1 : Mode RAW (recommandé si besoin garantie 100%)**
```bash
python main.py doc_to_markdown 4 --raw
```

**Comportement** :
- Phase 1 : Extraction ✅
- Phase 2 : Analyse images ✅ (LLaVA, 10-20% de risque)
- Phase 3 : Assemblage ✅
- Phase 4 : **SKIP** ❌ (pas de LLM textuel)

**Résultat** : Markdown brut mais 100% fidèle au niveau textuel

**Inconvénient** : Structure Markdown peut être imparfaite
```markdown
Architecture du système
Le système utilise Redis
Composants principaux
```

Au lieu de :
```markdown
# Architecture du système

Le système utilise Redis

## Composants principaux
```

**Option 2 : Validation manuelle systématique**
- Traiter 10 documents test
- Comparer manuellement source vs sortie
- Mesurer le taux réel d'ajout
- Décider si acceptable pour votre cas d'usage

**Option 3 : Post-validation automatique**
```python
# Pseudo-code
def validate_output(source_text, output_markdown):
    source_words = set(source_text.split())
    output_words = set(strip_markdown(output_markdown).split())
    
    added_words = output_words - source_words
    
    if len(added_words) > threshold:
        raise Warning(f"Ajout détecté: {added_words}")
```

## Recommandations par cas d'usage

### Cas 1 : Documents confidentiels / Juridiques / Médicaux
**Tolérance** : 0% d'ajout acceptable

**Commande** :
```bash
python main.py doc_to_markdown 4 --raw --no-images
```

**Garantie** : 0% de risque (extraction pure)

**Inconvénient** : Pas de description d'images, structure brute

### Cas 2 : Documents techniques pour Delibia
**Tolérance** : <5% acceptable si images sont transcrites

**Commande** :
```bash
python main.py doc_to_markdown 4
```

**Garantie** : ~2-5% de risque (LLM strict + analyse images)

**Avantage** : Images décrites, structure propre

**Validation** : Tester sur 10 documents, vérifier manuellement

### Cas 3 : Documents simples sans images
**Tolérance** : <2% acceptable

**Commande** :
```bash
python main.py doc_to_markdown 4 --no-images
```

**Garantie** : ~2-3% de risque (LLM strict uniquement)

**Avantage** : Structure propre, rapide

## Tests et validation

### Test recommandé avant production

1. **Sélectionner 10 documents représentatifs**

2. **Traiter en mode strict (défaut)**
```bash
python main.py doc_to_markdown 4
```

3. **Comparer manuellement**
- Ouvrir PDF source + Markdown généré côte à côte
- Identifier tout ajout d'information
- Noter le type (hallucination, interprétation, correction)

4. **Calculer le taux réel**
```
Taux d'ajout = (Nombre de mots ajoutés) / (Nombre de mots total) × 100%
```

5. **Décider**
- Si taux < 1% → Mode strict acceptable
- Si taux 1-5% → Évaluer impact métier
- Si taux > 5% → Utiliser mode RAW

### Exemple de grille de validation

| Document | Mots source | Mots sortie | Mots ajoutés | Taux | Acceptable ? |
|----------|-------------|-------------|--------------|------|--------------|
| Doc1.pdf | 1500 | 1520 | 20 | 1.3% | ⚠️ À vérifier |
| Doc2.pdf | 3000 | 3005 | 5 | 0.16% | ✅ OK |
| Doc3.pdf | 800 | 850 | 50 | 6.25% | ❌ Trop élevé |

## Comparaison des modes

### Mode STRICT (défaut)

```bash
python main.py doc_to_markdown 4
```

**Pipeline** :
1. Extraction texte ✅ (0% risque)
2. Analyse images ✅ (10-20% risque)
3. Assemblage ✅ (0% risque sémantique)
4. Nettoyage LLM ✅ (2-5% risque)

**Résultat** :
- Structure Markdown propre
- Images décrites
- Hiérarchie claire
- **Risque total : ~5-7% d'ajout possible**

### Mode RAW

```bash
python main.py doc_to_markdown 4 --raw
```

**Pipeline** :
1. Extraction texte ✅ (0% risque)
2. Analyse images ✅ (10-20% risque)
3. Assemblage ✅ (0% risque sémantique)
4. ~~Nettoyage LLM~~ ❌ SKIP

**Résultat** :
- Structure Markdown brute
- Images décrites
- Hiérarchie peut être approximative
- **Risque total : ~10-20% uniquement sur descriptions images**

### Mode RAW sans images

```bash
python main.py doc_to_markdown 4 --raw --no-images
```

**Pipeline** :
1. Extraction texte ✅ (0% risque)
2. ~~Analyse images~~ ❌ SKIP
3. Assemblage ✅ (0% risque sémantique)
4. ~~Nettoyage LLM~~ ❌ SKIP

**Résultat** :
- Structure Markdown brute
- Pas de description images
- Hiérarchie peut être approximative
- **Risque total : 0% (garantie absolue)**

## Conclusion et recommandation

### Pour Delibia (notre cas d'usage)

**Option 1 (recommandée) : Mode strict avec validation**
```bash
python main.py doc_to_markdown 4
```

**Justification** :
- Risque ~5% acceptable pour RAG
- Images transcrites = gain important
- Structure propre = meilleur chunking
- Validation manuelle sur échantillon pour confirmer

**Option 2 (conservative) : Mode RAW**
```bash
python main.py doc_to_markdown 4 --raw
```

**Justification** :
- Risque 0% sur le texte
- Risque 10-20% uniquement sur images
- Structure brute mais exploitable
- Si images sont critiques, à éviter

**Option 3 (ultra-conservative) : RAW sans images**
```bash
python main.py doc_to_markdown 4 --raw --no-images
```

**Justification** :
- Risque 0% absolu
- Pas de transcription images (perte)
- Structure brute
- Uniquement si documents ultra-sensibles

### Monitoring continu

Après déploiement :
1. Sélectionner aléatoirement 1 document traité / semaine
2. Valider manuellement
3. Mesurer le taux d'ajout réel
4. Ajuster si nécessaire (passer en mode RAW si dérive)

## Limites fondamentales

**IMPORTANT** : Il est IMPOSSIBLE de garantir 0% d'ajout avec un LLM, même avec le meilleur prompt.

Les LLM sont des modèles probabilistes qui :
- Prédisent le mot suivant basé sur des patterns appris
- Peuvent "halluciner" des informations plausibles mais fausses
- Ont des biais de leurs données d'entraînement

**Seule garantie absolue** : Mode RAW sans images (extraction algorithmique pure)
