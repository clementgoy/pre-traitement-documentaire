"""
Communication avec l'API REST d'Ollama (http://localhost:11434).
"""

import base64
from io import BytesIO

import requests
from PIL import Image

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 300  # secondes — les modèles de vision peuvent être lents


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
    Appelle l'API Ollama en mode génération (non-streaming).

    Args:
        model         : nom du modèle Ollama
        prompt        : texte du prompt
        image         : image PIL optionnelle (modèle multimodal requis)
        timeout       : délai max en secondes
        max_image_size: côté le plus long de l'image après redimensionnement (px).
                        Réduire accélère l'inférence ; 768 est un bon compromis
                        vitesse/qualité pour la transcription de pages complètes.
        max_tokens    : nombre max de tokens générés en sortie (num_predict).
                        Augmenter évite la troncature sur les pages denses.
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Basse température pour des réponses factuelles
            "num_predict": max_tokens,
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
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["response"].strip()
