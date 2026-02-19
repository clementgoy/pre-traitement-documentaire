"""
Configuration centralisée pour le pré-traitement documentaire
"""

# Modèle Ollama pour l'analyse de texte
TEXT_MODEL = "ministral3:14b"

# Modèle Ollama multimodal pour l'analyse d'images (LLaVA, Bakllava, etc.)
VISION_MODEL = "llava:latest"  # Modèle 13B pour meilleure compréhension des détails (RAM suffisante : 21GB)

# Paramètres de traitement
MAX_TOKENS = 4096
MAX_THREADS = 4

# Types d'images à traiter
IMAGE_TYPES = {
    "diagram": "schéma technique ou diagramme",
    "chart": "graphique ou tableau visuel",
    "screenshot": "capture d'écran",
    "photo": "photographie",
    "illustration": "illustration ou dessin",
    "logo": "logo ou élément décoratif",
}

# Seuils de pertinence
RELEVANCE_THRESHOLD = 0.3  # Score minimum pour considérer une image comme pertinente (réduit pour éviter de filtrer des organigrammes importants)
MIN_IMAGE_SIZE = (80, 80)  # Taille minimale pour traiter une image (évite les petites icônes)
MAX_IMAGE_SIZE = (1536, 1536)  # Augmenté pour préserver les détails des organigrammes complexes (RAM suffisante)

# Extensions de fichiers supportées
SUPPORTED_EXTENSIONS = {
    "pdf": "PDF",
    "docx": "Microsoft Word",
    "doc": "Microsoft Word (ancien)",
    "pptx": "Microsoft PowerPoint",
}

# Dossiers
INPUT_FOLDER = "docs-bruts"
OUTPUT_FOLDER = "docs-traites"

# Prompts système

# Prompt STRICT : Aucune reformulation, aucune interprétation, aucun ajout
SYSTEM_PROMPT_TEXT_STRICT = """Tu es un convertisseur Markdown STRICTEMENT FIDÈLE.

RÈGLES IMPÉRATIVES :
1. PRÉSERVE INTÉGRALEMENT tout le texte source, mot pour mot
2. NE JAMAIS résumer, paraphraser, reformuler ou interpréter
3. NE JAMAIS ajouter de contenu (pas de conclusion, synthèse, commentaire)
4. NE JAMAIS supprimer d'information
5. UNIQUEMENT corriger le formatage Markdown :
   - Ajouter # pour les titres selon leur niveau
   - Convertir les listes en - ou 1. 2. 3.
   - Convertir les tableaux en | col1 | col2 |
   - Utiliser ** uniquement si déjà en gras dans le source
   - Utiliser LaTeX $ $ pour équations mathématiques existantes

Tu es un TRANSCRIPTEUR FIDÈLE, pas un rédacteur.
Ton rôle est de fixer la syntaxe Markdown sans toucher au contenu."""

# Prompt standard (moins strict, peut améliorer légèrement la structure)
SYSTEM_PROMPT_TEXT = """Tu es un expert en structuration de documents techniques.
Ton rôle est de convertir du texte brut en Markdown bien structuré en :
- Préservant la hiérarchie des titres (h1, h2, h3...)
- Conservant les listes à puces et numérotées
- Formatant correctement les tableaux
- Mettant en évidence les éléments importants en **gras**
- Utilisant LaTeX pour les équations mathématiques
- Gardant le contenu technique précis et complet

RÈGLE ABSOLUE : Ne modifie jamais le sens ou le contenu technique.
Ne résume pas, ne paraphrase pas, ne réorganise pas les concepts."""

SYSTEM_PROMPT_IMAGE_ANALYSIS = """Analyse cette image de document professionnel et retourne un JSON.

MISSION : Transcrire l'image en texte pour qu'elle soit compréhensible sans la voir.

RÈGLES :
- Transcris TOUT le texte visible
- Décris la structure (organigramme, schéma, graphique, etc.)
- Explique les relations entre éléments
- Minimum 3 phrases si informative

JSON attendu :
{
  "type": "orgchart|flowchart|diagram|chart|graph|table_image|screenshot|photo|logo",
  "is_relevant": true|false,
  "confidence": 0.0-1.0,
  "description": "Description complète en 3+ phrases",
  "contains_text": true|false,
  "extracted_text": "Tout texte visible"
}

Exemple organigramme :
{
  "type": "orgchart",
  "is_relevant": true,
  "confidence": 0.9,
  "description": "Organigramme 3 niveaux. Sommet : Directeur Général. Niveau 2 : 3 directeurs (RH, Finance, Ops). Niveau 3 : 6 managers sous les directeurs. Lignes verticales montrent hiérarchie.",
  "contains_text": true,
  "extracted_text": "Directeur Général | Directeur RH | Directeur Finance | Directeur Ops | Manager Recrutement | Manager Formation | Manager Compta | Manager Tréso | Manager Prod | Manager Logistique"
}"""
