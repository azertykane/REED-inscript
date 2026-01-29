#!/bin/bash
# start.sh

echo "Starting the application..."

# Initialize database
python -c "
from app import app, init_database
with app.app_context():
    init_database()
    print('Database initialized')
"

# Start Gunicorn
exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app