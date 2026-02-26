#!/usr/bin/env python3
"""CLI de conversion Markdown → DOCX via pypandoc (ou le binaire pandoc sur PATH).

Usage :
  python convert-md-to-docx.py --file input.md [--out output.docx]
  python convert-md-to-docx.py --dir doc-md/
  python convert-md-to-docx.py --src doc-md/ --dst doc-docx/

Prérequis : pypandoc installé (pip install pypandoc).
Le binaire pandoc est détecté automatiquement ; s'il est absent,
le script propose de le télécharger via pypandoc.download_pandoc().
"""
import argparse
import subprocess
import sys
from pathlib import Path


def _check_pandoc() -> None:
    """Vérifie que le binaire pandoc est disponible ; propose le téléchargement sinon."""
    try:
        import pypandoc
        try:
            pypandoc.get_pandoc_version()  # lève OSError si pandoc absent
        except OSError:
            print("Pandoc non trouvé sur ce système.")
            print("Téléchargement automatique via pypandoc (une seule fois)...")
            try:
                pypandoc.download_pandoc(delete_installer=True)
                print(f"Pandoc installé : {pypandoc.get_pandoc_path()}")
            except Exception as e:
                print(f"Échec du téléchargement automatique : {e}")
                print("Installez pandoc manuellement depuis https://pandoc.org/installing.html")
                sys.exit(1)
    except ImportError:
        # pypandoc absent — on tente le binaire directement dans convert_file()
        pass


def convert_file(input_path: Path, output_path: Path) -> None:
    input_str = str(input_path)
    output_str = str(output_path)
    try:
        import pypandoc

        pypandoc.convert_file(input_str, 'docx', format='md', outputfile=output_str)
        print(f"Converted {input_path} -> {output_path} (via pypandoc)")
        return
    except Exception:
        # fall back to pandoc binary
        pass

    # Try calling pandoc binary
    try:
        subprocess.run(['pandoc', input_str, '-o', output_str], check=True)
        print(f"Converted {input_path} -> {output_path} (via pandoc)")
    except FileNotFoundError:
        print("Error: pandoc not found. Install pandoc or pypandoc.")
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"pandoc failed: {e}")
        sys.exit(3)


def main() -> None:
    _check_pandoc()
    parser = argparse.ArgumentParser(description='Convertit des fichiers Markdown en DOCX')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', '-f', type=Path, help='Input markdown file')
    group.add_argument('--dir', '-d', type=Path, help='Directory: convert all .md files inside (in-place)')
    group.add_argument('--src', type=Path, help='Source directory containing .md files')
    parser.add_argument('--out', '-o', type=Path, help='Output file (only with --file)')
    parser.add_argument('--dst', type=Path, help='Destination directory for converted files (use with --src)')

    args = parser.parse_args()

    if args.file:
        input_path = args.file
        if not input_path.exists():
            print(f"Input file not found: {input_path}")
            sys.exit(1)
        out = args.out or input_path.with_suffix('.docx')
        convert_file(input_path, out)

    elif args.dir:
        d = args.dir
        if not d.exists() or not d.is_dir():
            print(f"Directory not found: {d}")
            sys.exit(1)
        md_files = sorted(p for p in d.glob('**/*.md') if p.is_file())
        if not md_files:
            print(f"No markdown files found in {d}")
            return
        for p in md_files:
            out = p.with_suffix('.docx')
            convert_file(p, out)

    elif args.src:
        src = args.src
        dst = args.dst
        if dst is None:
            print("When using --src you must provide --dst")
            sys.exit(1)
        if not src.exists() or not src.is_dir():
            print(f"Source directory not found: {src}")
            sys.exit(1)
        dst.mkdir(parents=True, exist_ok=True)
        md_files = sorted(p for p in src.rglob('*.md') if p.is_file())
        if not md_files:
            print(f"No markdown files found in {src}")
            return
        for p in md_files:
            rel = p.relative_to(src)
            out_path = (dst / rel).with_suffix('.docx')
            out_path.parent.mkdir(parents=True, exist_ok=True)
            convert_file(p, out_path)


if __name__ == '__main__':
    main()
