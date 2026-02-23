#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

# Force UTF-8 sur stdout/stderr pour les terminaux Windows (cp1252 par défaut)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

"""
doc2md — Convertisseur de documents vers Markdown avec analyse d'images par IA locale.

Formats supportés : PDF, Word (.docx), PowerPoint (.pptx)
Modèle de vision  : qwen2.5vl:latest (recommandé)

Utilisation — fichier unique :
    python convert.py document.pdf
    python convert.py rapport.docx -o rapport.md
    python convert.py document.pdf --no-images

Utilisation — dossier complet :
    python convert.py doc-raw/
    python convert.py doc-raw/ -o doc-md/
    python convert.py doc-raw/ --no-images

Autres :
    python convert.py --list-models
"""

import argparse
import traceback
from pathlib import Path

from src.ollama_client import check_ollama, list_available_models

SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".pptx": "PowerPoint",
}

OLD_FORMATS = {".doc", ".ppt", ".pptm", ".docm"}

DEFAULT_VISION_MODEL = "qwen2.5vl:latest"

# Modèles de vision reconnus (pour l'affichage et les fallbacks)
VISION_MODEL_KEYWORDS = ("llava", "qwen2.5vl", "qwen2-vl", "minicpm-v", "moondream", "bakllava")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="convert.py",
        description="Convertit des documents (ou un dossier entier) en Markdown via Ollama.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemples :
  # Fichier unique
  python convert.py document.pdf
  python convert.py rapport.docx -o rapport.md

  # Dossier complet (tous les PDF/DOCX/PPTX)
  python convert.py doc-raw/
  python convert.py doc-raw/ -o doc-md/
  python convert.py doc-raw/ --no-images

  # Utilitaires
  python convert.py --list-models
""",
    )
    p.add_argument(
        "input",
        nargs="?",
        help="Fichier ou dossier source à convertir",
    )
    p.add_argument(
        "-o", "--output",
        metavar="CHEMIN",
        help=(
            "Fichier .md de sortie (mode fichier unique) "
            "ou dossier de sortie (mode dossier)"
        ),
    )
    p.add_argument(
        "--vision-model",
        default=DEFAULT_VISION_MODEL,
        metavar="MODELE",
        help=f"Modèle Ollama de vision (défaut : {DEFAULT_VISION_MODEL})",
    )
    p.add_argument(
        "--no-images",
        action="store_true",
        help="Désactiver l'analyse des images (texte uniquement, plus rapide)",
    )
    p.add_argument(
        "--list-models",
        action="store_true",
        help="Afficher les modèles Ollama disponibles et quitter",
    )
    p.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Mode silencieux (pas de messages de progression)",
    )
    return p


def check_vision_model(requested: str) -> str:
    """
    Vérifie que le modèle de vision est disponible.
    Propose un modèle de remplacement si nécessaire.
    Retourne le nom du modèle à utiliser, ou '' pour désactiver.
    """
    try:
        available = list_available_models()
    except Exception as e:
        print(f"Erreur lors de la récupération des modèles : {e}")
        sys.exit(1)

    if requested in available:
        return requested

    print(f"Avertissement : le modèle '{requested}' n'est pas installé.")

    vision_models = [
        m for m in available
        if any(kw in m.lower() for kw in VISION_MODEL_KEYWORDS)
    ]
    if vision_models:
        fallback = vision_models[0]
        print(f"Modèle de remplacement : '{fallback}'")
        return fallback

    print("Aucun modèle de vision disponible.")
    print("Pour installer le modèle recommandé : ollama pull qwen2.5vl")
    print("Analyse des images désactivée.")
    return ""


def convert_file(
    input_path: Path,
    output_path: Path,
    vision_model: str,
    analyze_images: bool,
    verbose: bool,
) -> bool:
    """
    Convertit un fichier unique en Markdown.
    Retourne True si succès, False si erreur.
    """
    suffix = input_path.suffix.lower()
    fmt_label = SUPPORTED_EXTENSIONS[suffix]

    if verbose:
        print(f"\n{'='*55}")
        print(f"  Source   : {input_path.name} ({fmt_label})")
        print(f"  Sortie   : {output_path}")
        print(f"  Vision   : {vision_model if analyze_images else 'désactivée'}")
        print(f"{'='*55}\n")

    try:
        if suffix == ".pdf":
            from src.pdf_parser import parse_pdf
            content = parse_pdf(
                str(input_path),
                vision_model=vision_model,
                analyze_images=analyze_images,
                verbose=verbose,
            )
        elif suffix == ".docx":
            from src.docx_parser import parse_docx
            content = parse_docx(
                str(input_path),
                vision_model=vision_model,
                analyze_images=analyze_images,
                verbose=verbose,
            )
        elif suffix == ".pptx":
            from src.pptx_parser import parse_pptx
            content = parse_pptx(
                str(input_path),
                vision_model=vision_model,
                analyze_images=analyze_images,
                verbose=verbose,
            )

    except KeyboardInterrupt:
        raise  # remonter pour arrêter le batch proprement
    except Exception as e:
        print(f"\nErreur lors de la conversion de {input_path.name} : {e}")
        if verbose:
            traceback.print_exc()
        return False

    vision_info = f"Modèle vision : `{vision_model}`" if analyze_images else "Analyse d'images désactivée"
    header = (
        f"# {input_path.stem}\n\n"
        f"*Source : {input_path.name} ({fmt_label}) — {vision_info}*\n\n"
        f"---\n\n"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + content, encoding="utf-8")

    if verbose:
        word_count = len(content.split())
        print(f"\n{'='*55}")
        print(f"  Fichier créé : {output_path}")
        print(f"  Volume       : ~{word_count} mots")
        print(f"{'='*55}\n")

    return True


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # ── Vérification d'Ollama ─────────────────────────────────────────────
    if not check_ollama():
        print("Erreur : Ollama n'est pas accessible sur http://localhost:11434")
        print("Lancez Ollama avec : ollama serve")
        sys.exit(1)

    # ── Liste des modèles ─────────────────────────────────────────────────
    if args.list_models:
        models = list_available_models()
        print("Modèles Ollama disponibles :")
        for m in models:
            tag = " [vision]" if any(kw in m.lower() for kw in VISION_MODEL_KEYWORDS) else ""
            print(f"  {m}{tag}")
        sys.exit(0)

    # ── Validation de l'entrée ────────────────────────────────────────────
    if not args.input:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Erreur : chemin introuvable : {args.input}")
        sys.exit(1)

    # ── Modèle de vision ──────────────────────────────────────────────────
    analyze_images = not args.no_images
    vision_model = args.vision_model

    if analyze_images:
        vision_model = check_vision_model(vision_model)
        if not vision_model:
            analyze_images = False

    verbose = not args.quiet

    # ══════════════════════════════════════════════════════════════════════
    # MODE DOSSIER
    # ══════════════════════════════════════════════════════════════════════
    if input_path.is_dir():
        # Collecter tous les fichiers supportés (non récursif)
        files = sorted(
            f for f in input_path.iterdir()
            if f.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        if not files:
            print(f"Aucun fichier PDF/DOCX/PPTX trouvé dans : {input_path}")
            sys.exit(0)

        # Dossier de sortie
        if args.output:
            out_dir = Path(args.output)
        else:
            out_dir = Path("doc-md")

        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{len(files)} fichier(s) à convertir -> {out_dir}\n")

        successes, failures = [], []

        for i, file_path in enumerate(files, start=1):
            output_path = out_dir / file_path.with_suffix(".md").name
            print(f"[{i}/{len(files)}] {file_path.name}")

            try:
                ok = convert_file(
                    file_path, output_path,
                    vision_model, analyze_images, verbose,
                )
                if ok:
                    successes.append(file_path.name)
                else:
                    failures.append(file_path.name)
            except KeyboardInterrupt:
                print("\n\nInterrompu. Fichiers traités jusqu'ici :")
                for name in successes:
                    print(f"  [OK] {name}")
                sys.exit(1)

        # Résumé final
        print(f"\n{'='*55}")
        print(f"  Bilan : {len(successes)}/{len(files)} fichier(s) convertis")
        if failures:
            print(f"  Echecs ({len(failures)}) :")
            for name in failures:
                print(f"    - {name}")
        print(f"  Dossier de sortie : {out_dir}")
        print(f"{'='*55}\n")

    # ══════════════════════════════════════════════════════════════════════
    # MODE FICHIER UNIQUE
    # ══════════════════════════════════════════════════════════════════════
    else:
        suffix = input_path.suffix.lower()

        if suffix in OLD_FORMATS:
            print(f"Erreur : le format '{suffix}' (ancien format binaire) n'est pas supporté.")
            print("Convertissez votre fichier en .docx ou .pptx via LibreOffice ou Microsoft Office.")
            sys.exit(1)

        if suffix not in SUPPORTED_EXTENSIONS:
            print(f"Erreur : format non supporté '{suffix}'")
            print(f"Formats acceptés : {', '.join(SUPPORTED_EXTENSIONS.keys())}")
            sys.exit(1)

        output_path = Path(args.output) if args.output else Path("doc-md") / input_path.with_suffix(".md").name

        try:
            ok = convert_file(
                input_path, output_path,
                vision_model, analyze_images, verbose,
            )
        except KeyboardInterrupt:
            print("\n\nInterrompu.")
            sys.exit(1)

        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
