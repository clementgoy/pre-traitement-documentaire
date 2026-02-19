# 🚀 Guide de Démarrage Rapide

Ce guide vous permettra de mettre en place et tester le système en 10 minutes.

## Étape 1 : Vérifier Ollama (2 min)

### Vérifier l'installation
```powershell
ollama --version
```

Si Ollama n'est pas installé :
```powershell
# Télécharger depuis https://ollama.ai/download
# Ou installer via winget:
winget install Ollama.Ollama
```

### Vérifier que le service est actif
```powershell
ollama list
```

## Étape 2 : Télécharger les modèles (5-10 min)

### Modèle obligatoire (texte)
```powershell
ollama pull ministral3:14b
```
*Taille : ~8GB - Durée : 3-5 minutes selon connexion*

### Modèle recommandé (vision)
```powershell
ollama pull llava:13b
```
*Taille : ~7GB - Durée : 3-5 minutes selon connexion*

**Alternative plus légère :**
```powershell
ollama pull llava:7b
```
*Taille : ~4GB - Plus rapide mais moins précis*

### Vérifier les modèles installés
```powershell
ollama list
```

Vous devriez voir :
```
NAME                ID              SIZE
ministral3:14b     ...             8.2 GB
llava:13b          ...             7.4 GB
```

## Étape 3 : Installer les dépendances Python (1 min)

```powershell
pip install -r requirements.txt
```

## Étape 4 : Préparer vos documents

1. Placez vos documents PDF ou DOCX dans le dossier `docs-bruts/`
   ```powershell
   # Créer le dossier s'il n'existe pas
   New-Item -ItemType Directory -Force -Path docs-bruts
   ```

2. Copiez vos documents :
   ```powershell
   Copy-Item "C:\chemin\vers\votre\document.pdf" docs-bruts\
   ```

## Étape 5 : Premier test en MODE STRICT (RECOMMANDÉ)

Pour un traitement fidèle sans reformulation (recommandé pour Delibia) :

```powershell
python main.py doc_to_markdown 4 --strict
```

**Avantages** :
- ✅ Fidélité absolue (mot pour mot)
- ✅ Descriptions d'images factuelles
- ✅ Aucune reformulation ni invention
- ✅ Rapide (~1-2 min pour 20 pages)

**Résultat** : Fichiers Markdown dans `docs-traites/`

## Étape 6 : Autres modes (optionnels)

### Mode standard (amélioration de structure)
```powershell
python main.py doc_to_markdown 2
```

### Sans analyse d'images (ultra-rapide)
```powershell
python main.py doc_to_markdown 4 --strict --no-images
```

**Recommandation** : Toujours utiliser `--strict` pour Delibia et systèmes RAG.

## 📊 Que se passe-t-il ?

### Pendant le traitement, vous verrez :

```
2026-02-18 10:30:15 - INFO - === Traitement du document: rapport.pdf ===
2026-02-18 10:30:15 - INFO - Phase 1: Extraction du contenu
2026-02-18 10:30:16 - INFO - Extraction terminée: 45 blocs de texte, 3 images
2026-02-18 10:30:16 - INFO - Phase 2: Analyse des images
2026-02-18 10:30:17 - INFO - Analyse image 1/3
2026-02-18 10:30:25 - INFO - Image analysée: diagram (pertinent: True, confiance: 0.92)
...
2026-02-18 10:32:15 - INFO - === Traitement terminé en 120s ===
2026-02-18 10:32:15 - INFO - Document généré: docs-traites/rapport.md
```

## 🎉 Vérifier le résultat

```powershell
# Ouvrir le fichier généré
code docs-traites\rapport.ministral3_14b.md
```

Vous devriez voir :
- ✅ Titres hiérarchiques préservés
- ✅ Texte structuré en paragraphes
- ✅ Descriptions détaillées des images/schémas (si analyse activée)
- ✅ Tableaux convertis
- ✅ Mise en forme Markdown

## ⚙️ Ajuster la configuration

Si nécessaire, modifiez [config.py](config.py) :

```python
# Augmenter le seuil de pertinence (seulement images très pertinentes)
RELEVANCE_THRESHOLD = 0.8  # Au lieu de 0.6

# Augmenter la taille minimale (ignorer petites images)
MIN_IMAGE_SIZE = (200, 200)  # Au lieu de (100, 100)

# Changer les dossiers
INPUT_FOLDER = "mes-docs"
OUTPUT_FOLDER = "exports-md"
```

## 🐛 Problèmes courants

### "Error: model not found"
```powershell
# Télécharger le modèle manquant
ollama pull <nom-du-modele>
```

### "Connection refused" ou "Cannot connect to Ollama"
```powershell
# Démarrer Ollama
ollama serve
```

### Mémoire insuffisante
```powershell
# Réduire à 1 thread
python main.py doc_to_markdown 1

# Ou utiliser un modèle plus léger
python main.py doc_to_markdown 2 --vision-model llava:7b
```

### Images non analysées correctement
```powershell
# Essayer avec un modèle plus puissant
ollama pull llava:34b
python main.py doc_to_markdown 2 --vision-model llava:34b
```

## 📈 Prochaines étapes

1. **Testez avec différents types de documents** :
   - Documents techniques avec schémas
   - Rapports avec graphiques
   - Présentations converties en PDF

2. **Optimisez les paramètres** :
   - Ajustez `RELEVANCE_THRESHOLD` dans config.py
   - Testez différents modèles de vision

3. **Automatisez** :
   - Créez un script batch pour traiter plusieurs dossiers
   - Intégrez dans votre pipeline CI/CD

## 💡 Commandes utiles

```powershell
# Lister tous les modèles disponibles sur Ollama
ollama list

# Supprimer un modèle pour libérer de l'espace
ollama rm <nom-du-modele>

# Tester un modèle directement
ollama run ministral3:14b

# Voir les logs détaillés
python main.py doc_to_markdown 4 2>&1 | Tee-Object -FilePath traitement.log
```pour Delibia (RECOMMANDÉ)
```powershell
# Placer tous les PDFs dans docs-bruts/
python main.py doc_to_markdown 4 --strict
```

### Cas 2 : Document unique avec analyse super précise
```powershell
# Copier un seul document
Copy-Item "rapport-important.pdf" docs-bruts\
python main.py doc_to_markdown 1 --strict --vision-model llava:34b
```

### Cas 3 : Conversion ultra-rapide sans images
```powershell
python main.py doc_to_markdown 8 --strict

### Cas 3 : Conversion rapide sans images
```powershell
python main.py doc_to_markdown 8 --no-images
```

---

**Temps total de setup** : ~10-15 minutes
**Temps de traitement** : ~3-5 min/document (selon taille et options)

Bon traitement ! 🚀
