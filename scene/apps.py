from django.apps import AppConfig

class SceneConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scene'

    def ready(self):
        # Import signals module to ensure receivers are connected
        import scene.signals