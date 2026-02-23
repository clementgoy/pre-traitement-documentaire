"""
Analyse des images extraites des documents.

Principe : un seul appel au modèle de vision par image.
Le modèle évalue simultanément la pertinence et produit une description
si l'image est jugée utile. Cela évite d'envoyer deux fois la même image.
"""

from PIL import Image

from .ollama_client import generate

# Taille minimale (en pixels) pour qu'une image soit analysée.
# Les images plus petites sont presque toujours des icônes ou artefacts.
MIN_DIMENSION = 80

# Prompt unique qui combine évaluation et description.
# Rédigé en anglais pour de meilleures performances du modèle,
# mais la description de sortie est demandée en français.
#
# Principe directeur : une image est RELEVANT uniquement si elle contient
# de l'information STRUCTURÉE qui ne peut pas être déduite du texte seul.
# En cas de doute, le modèle doit choisir IRRELEVANT.
ANALYSIS_PROMPT = """You are a strict content filter analyzing an image extracted from a professional document.

Your only job: decide if this image contains STRUCTURED INFORMATION that would be LOST if the image were removed.

Mark as RELEVANT only if the image is one of these types:
- Flowchart or process diagram (boxes, arrows, decision nodes showing a workflow)
- Organizational chart (hierarchy of people, roles, or departments with connecting lines)
- Data chart or graph (bar chart, line graph, pie chart, scatter plot with actual data)
- Technical schema or architecture diagram (system components and their relationships)
- Annotated technical drawing or map (with labels, measurements, or legends)
- Data table rendered as an image (rows and columns of structured data not captured in text)
- Software screenshot with meaningful UI content (menus, forms, dashboards with labels)

Mark as IRRELEVANT in ALL other cases, including:
- Any photograph (of people, landscapes, buildings, objects) — always IRRELEVANT, no exceptions
- Any logo, coat of arms, or branding element — always IRRELEVANT, no exceptions
- Cover page or header/footer imagery — always IRRELEVANT
- Clipart or illustration of people, even in a professional context — always IRRELEVANT
- Decorative icons, bullets, borders, dividers, or background patterns — always IRRELEVANT
- Stock photography used for visual appeal — always IRRELEVANT
- Simple icons (checkmarks, arrows, warning symbols used as visual cues) — always IRRELEVANT

Rule: when in doubt, choose IRRELEVANT. Only choose RELEVANT when you are certain the image shows structured information (diagram, chart, org chart, schema) that carries facts not expressible in plain text.

If RELEVANT, write a detailed description in French that captures every label, value, relationship, and structural element visible in the image.

Respond in EXACTLY this format — no extra text:
ASSESSMENT: [RELEVANT or IRRELEVANT]
REASON: [one sentence in English explaining your decision]
DESCRIPTION: [detailed French description if RELEVANT; leave empty if IRRELEVANT]
"""


def analyze_image(image: Image.Image, vision_model: str) -> dict:
    """
    Analyse une image et retourne un dictionnaire :
    {
        'relevant': bool,
        'reason': str,
        'description': str  # vide si non pertinente
    }
    """
    # Ignorer les images trop petites sans appel réseau
    if image.width < MIN_DIMENSION or image.height < MIN_DIMENSION:
        return {
            "relevant": False,
            "reason": f"Image trop petite ({image.width}x{image.height}px)",
            "description": "",
        }

    try:
        response = generate(vision_model, ANALYSIS_PROMPT, image=image)
        return _parse_response(response)
    except Exception as e:
        return {
            "relevant": False,
            "reason": f"Erreur d'analyse : {e}",
            "description": "",
        }


def _parse_response(response: str) -> dict:
    """
    Parse la réponse structurée du modèle.

    Format attendu :
        ASSESSMENT: RELEVANT
        REASON: This is a flowchart showing ...
        DESCRIPTION: Ce diagramme représente ...
    """
    result = {"relevant": False, "reason": "", "description": ""}
    desc_lines: list[str] = []
    current_section: str | None = None

    for line in response.splitlines():
        stripped = line.strip()

        if stripped.upper().startswith("ASSESSMENT:"):
            value = stripped[len("ASSESSMENT:"):].strip().upper()
            # "IRRELEVANT" contient "RELEVANT", donc on teste d'abord IRRELEVANT
            result["relevant"] = "IRRELEVANT" not in value and "RELEVANT" in value
            current_section = "assessment"

        elif stripped.upper().startswith("REASON:"):
            result["reason"] = stripped[len("REASON:"):].strip()
            current_section = "reason"

        elif stripped.upper().startswith("DESCRIPTION:"):
            content = stripped[len("DESCRIPTION:"):].strip()
            if content:
                desc_lines.append(content)
            current_section = "description"

        elif current_section == "description" and stripped:
            # Continuation de la description sur plusieurs lignes
            desc_lines.append(stripped)

    result["description"] = " ".join(desc_lines).strip()
    return result
