#!/bin/bash
# build.sh pour Render

echo "=== Installation de Python dépendances ==="

# Mettre à jour pip
python -m pip install --upgrade pip

# Installer les dépendances
pip install -r requirements.txt

# Créer le dossier uploads s'il n'existe pas
mkdir -p static/uploads

echo "=== Installation terminée ==="