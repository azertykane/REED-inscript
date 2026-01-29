# gunicorn.conf.py
import multiprocessing

# Nombre de workers
workers = 2
worker_class = 'sync'

# Timeout augmenté
timeout = 120  # 2 minutes au lieu de 30 secondes par défaut
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Worker temp directory (pour éviter les problèmes de droits)
worker_tmp_dir = '/dev/shm'