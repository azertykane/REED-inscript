# gunicorn.conf.py
import multiprocessing

# Nombre de workers
workers = 2
worker_class = 'sync'

# Timeout augmenté pour les uploads
timeout = 180
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Worker temp directory
worker_tmp_dir = '/dev/shm'

# Max requests pour éviter les fuites mémoire
max_requests = 1000
max_requests_jitter = 50