#!/usr/bin/env bash
# Crée l'environnement virtuel et installe les dépendances.
# A exécuter une seule fois depuis le répertoire du projet.

set -e

echo "=== Création de l'environnement virtuel ==="
python -m venv venv

echo "=== Installation des dépendances Python ==="
# Sur Windows (Git Bash), le pip du venv s'appelle via python.exe directement
venv/Scripts/python.exe -m pip install --upgrade pip --quiet
venv/Scripts/python.exe -m pip install -r requirements.txt

echo ""
echo "=== Vérification / téléchargement de pandoc ==="
venv/Scripts/python.exe -c "
import pypandoc, sys
try:
    v = pypandoc.get_pandoc_version()
    print(f'  pandoc déjà disponible : v{v}')
except OSError:
    print('  pandoc absent — téléchargement automatique...')
    try:
        pypandoc.download_pandoc(delete_installer=True)
        print(f'  pandoc installé : {pypandoc.get_pandoc_path()}')
    except Exception as e:
        print(f'  Échec : {e}')
        print('  Installez pandoc manuellement : https://pandoc.org/installing.html')
        sys.exit(1)
"

echo ""
echo "=== Installation terminée ==="
echo ""
echo "Conversion document → Markdown :"
echo "  venv/Scripts/python.exe convert.py <fichier.pdf|.docx|.pptx>"
echo "  venv/Scripts/python.exe convert.py doc-raw/          # dossier entier"
echo "  venv/Scripts/python.exe convert.py --list-models"
echo ""
echo "Conversion Markdown → DOCX (pour Delibia) :"
echo "  venv/Scripts/python.exe convert-md-to-docx.py --src doc-md/ --dst doc-docx/"
