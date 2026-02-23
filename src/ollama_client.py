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
) -> str:
    """
    Appelle l'API Ollama en mode génération (non-streaming).

    Si `image` est fournie, elle est encodée en base64 et envoyée
    avec le prompt (nécessite un modèle multimodal comme llava).
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Basse température pour des réponses factuelles
            "num_predict": 1024,
        },
    }

    if image is not None:
        # Normalisation du mode couleur
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        # Redimensionnement : les modèles de vision n'ont pas besoin de plus de
        # 1024px — cela réduit la taille de la requête et accélère l'inférence
        if max(image.width, image.height) > 1024:
            image = image.copy()
            image.thumbnail((1024, 1024), Image.LANCZOS)
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
