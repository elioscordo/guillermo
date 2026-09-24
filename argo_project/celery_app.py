import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'argo_project.settings')

app = Celery('argo')
app.config_from_object('argo_project.settings', namespace='CELERY')
app.autodiscover_tasks()
