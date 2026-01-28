#!/usr/bin/env python3
"""
Script d'initialisation de la base de données
"""
import sys
import os

# Ajouter le répertoire courant au chemin Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, init_db

if __name__ == '__main__':
    print("Initialisation de la base de données...")
    init_db()
    print("Base de données initialisée avec succès!")