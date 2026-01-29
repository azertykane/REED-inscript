#!/bin/bash
# setup.sh - Script d'installation pour Render

echo "Mise à jour de pip..."
python -m pip install --upgrade pip

echo "Installation des dépendances..."
pip install --no-cache-dir -r requirements.txt

echo "Création des dossiers nécessaires..."
mkdir -p static/uploads instance

echo "Installation terminée!"