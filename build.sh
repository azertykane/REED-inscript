#!/bin/bash
set -o errexit

pip install -r requirements.txt

# Créer les dossiers nécessaires
mkdir -p static/uploads
mkdir -p templates

# Initialiser la base de données
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Base de données initialisée')
"