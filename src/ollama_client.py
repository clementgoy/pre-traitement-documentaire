"""
Communication avec l'API REST d'Ollama (http://localhost:11434).
"""

import base64
import json
from io import BytesIO

import requests
from PIL import Image

OLLAMA_BASE_URL = "http://localhost:11434"

# Délai d'inactivité max entre deux chunks de streaming (secondes).
# Avec stream=True, ce timeout s'applique au silence entre deux tokens reçus,
# PAS à la durée totale de génération. Le modèle peut donc prendre plusieurs
# minutes pour une page complexe sans déclencher de timeout, tant qu'il
# continue de générer des tokens.
# On conserve une valeur élevée car l'encodage de l'image (avant le premier token)
# peut être long sur CPU : 600 s couvre l'encodage de pages très denses.
DEFAULT_TIMEOUT = 600


def check_ollama() -> bool:
    """Vérifie qu'Ollama est accessible."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return r.ok
    except Exception:
        return False


def list_available_models() -> list[str]:
    """Retourne la liste des modèles installés."""
    r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def generate(
    model: str,
    prompt: str,
    image: Image.Image | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_image_size: int = 1024,
    max_tokens: int = 1024,
) -> str:
    """
    Appelle l'API Ollama en mode streaming.

    Pourquoi streaming (stream: true) ?
    ------------------------------------
    En mode non-streaming, le timeout s'applique à la durée TOTALE de la requête
    (encodage image + génération de tous les tokens). Sur CPU lent, une page dense
    peut dépasser 300 s → ReadTimeout.

    En mode streaming, le timeout s'applique au SILENCE entre deux chunks reçus.
    Tant que le modèle génère des tokens (même lentement), des chunks arrivent
    continuellement et le timeout ne se déclenche jamais. Seul un blocage complet
    du modèle (aucun token pendant `timeout` secondes) provoque une erreur.

    Note : l'encodage de l'image se fait AVANT le premier token. Pendant cette
    phase, aucun chunk n'est envoyé. Le timeout doit donc être supérieur au temps
    d'encodage de l'image sur la machine cible (600 s par défaut).

    Args:
        model         : nom du modèle Ollama
        prompt        : texte du prompt
        image         : image PIL optionnelle (modèle multimodal requis)
        timeout       : délai max d'inactivité en secondes (entre deux chunks)
        max_image_size: côté le plus long de l'image après redimensionnement (px).
                        Réduire accélère l'encodage image ; 768 est un bon compromis
                        vitesse/qualité pour la transcription de pages complètes.
                        En cas de timeout, relancer avec 512 réduit significativement
                        le temps d'encodage.
        max_tokens    : nombre max de tokens générés en sortie (num_predict).
                        2048 évite la troncature sur les pages denses (tableaux, listes).
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.1,    # Basse température pour des réponses factuelles
            "num_predict": max_tokens,
            "repeat_penalty": 1.15,  # Pénalise les tokens répétés — coupe les boucles d'hallucination
        },
    }

    if image is not None:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if max(image.width, image.height) > max_image_size:
            image = image.copy()
            image.thumbnail((max_image_size, max_image_size), Image.LANCZOS)
        buf = BytesIO()
        image.save(buf, format="JPEG", quality=85)
        payload["images"] = [base64.b64encode(buf.getvalue()).decode()]

    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        stream=True,
        timeout=timeout,
    )
    r.raise_for_status()

    parts: list[str] = []
    for line in r.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        parts.append(chunk.get("response", ""))
        if chunk.get("done", False):
            break

    return "".join(parts).strip()
