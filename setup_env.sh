#!/usr/bin/env bash
# Crée l'environnement virtuel et installe les dépendances.
# A exécuter une seule fois depuis le répertoire du projet.

set -e

echo "=== Création de l'environnement virtuel ==="
python -m venv venv

echo "=== Installation des dépendances ==="
# Sur Windows (Git Bash), le pip du venv s'appelle via python.exe directement
venv/Scripts/python.exe -m pip install --upgrade pip --quiet
venv/Scripts/python.exe -m pip install -r requirements.txt

echo ""
echo "=== Installation terminée ==="
echo "Pour convertir un document :"
echo "  venv/Scripts/python.exe convert.py <fichier.pdf|.docx|.pptx>"
echo ""
echo "Exemples :"
echo "  venv/Scripts/python.exe convert.py rapport.pdf"
echo "  venv/Scripts/python.exe convert.py rapport.pdf --vision-model llava:13b"
echo "  venv/Scripts/python.exe convert.py rapport.pdf --no-images"
echo "  venv/Scripts/python.exe convert.py --list-models"
