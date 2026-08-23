import os
from pathlib import Path
from dotenv import load_dotenv
from django.utils.translation import gettext_lazy as _
from django.templatetags.static import static

BASE_DIR = Path(__file__).resolve().parent.parent
ARGO_ROOT = os.path.join(BASE_DIR, 'argo')

load_dotenv(dotenv_path=os.path.join(ARGO_ROOT, '.env_argo'))

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "your-django-secret")
DEBUG = True
ALLOWED_HOSTS = ['*']
# Application definition
INSTALLED_APPS = [
    'unfold',
    'unfold.contrib.import_export',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'easy_thumbnails',
    'filer',
    'django_celery_beat',
    'crispy_forms',
    'argo',
]

CRISPY_TEMPLATE_PACK = "unfold_crispy"
CRISPY_ALLOWED_TEMPLATE_PACKS = ["unfold_crispy"]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'argo_project.urls'
WSGI_APPLICATION = 'argo_project.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages'
            ],
            'debug': DEBUG,
        },
    }
]

UNFOLD = {
    "SITE_TITLE": _("Argo"),
    "SITE_HEADER": _("Argo"),
    "SITE_SUBHEADER": _("Financial Manager"),
    "STYLES": [
        lambda request: static("css/unfold_filer_custom.css"),
        lambda request: static("css/custom.css"),
    ],
    "ACCOUNT": {},
}

# Database
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "postgresql")
if DATABASE_TYPE == "sqlite":
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv("POSTGRES_DB", "argo"),
            'USER': os.getenv("POSTGRES_USER", "postgres"),
            'PASSWORD': os.getenv("POSTGRES_PASSWORD", "your_new_password"),
            'HOST': os.getenv("POSTGRES_HOST", "localhost"),
            'PORT': os.getenv("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
LANGUAGES = [
    ('en', _('English')),
    ('it', _('Italian')),
    ('es', _('Spanish')),
    ('pt', _('Portuguese')),
    ('fr', _('French')),
]
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery Configuration
CELERY_BROKER_TYPE = os.getenv("CELERY_BROKER_TYPE", "sqlite")
CELERY_BROKER_URL = "sqla+sqlite:///celerydb.sqlite" if CELERY_BROKER_TYPE == "sqlite" else os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "7200"))
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "7260"))
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))

GENAI_REQUEST_TIMEOUT_MS = int(os.getenv("GENAI_REQUEST_TIMEOUT_MS", "300000"))

# Task Constants & Schemas
TASK_TYPE_GENERATE_TEXT = 'generate_text'
TASK_TYPE_CHOICES = (
    (TASK_TYPE_GENERATE_TEXT, _("Generate Text")),
)

SCHEMA_OUTPUT_WITH_MESSAGE = "outwithmsg"
SCHEMA_CREATE_INSTRUCTIONS = "create_instructions"

AGENT_SCHEMA_CHOICES = [
    (SCHEMA_OUTPUT_WITH_MESSAGE, _("Output With Message")),
    (SCHEMA_CREATE_INSTRUCTIONS, _("Create Instructions")),
]

AGENT_SCHEMAS = {
    SCHEMA_OUTPUT_WITH_MESSAGE: "agent.schemas.OutputWithMessageSchema",
    SCHEMA_CREATE_INSTRUCTIONS: "agent.schemas.CreateInstructionsSchema",
}

PRESET_INFO = "info"
PRESET_INSTRUCTION = "instruction"

COMMON_TEXT_AGENT_PRESETS = (
    (PRESET_INFO, _("Last message")),
    (PRESET_INSTRUCTION, _("Instruction")),
)

ACTION_INFO = f"generate_text-preset-{PRESET_INFO}"
ACTION_INSTRUCTION = f"generate_text-preset-{PRESET_INSTRUCTION}-schema-{SCHEMA_OUTPUT_WITH_MESSAGE}"
ACTION_INSTRUCTION_COMMIT = f"generate_text-preset-{PRESET_INSTRUCTION}-schema-{SCHEMA_CREATE_INSTRUCTIONS}"

COMMON_TEXT_ACTION_CHOICES = (
    (ACTION_INFO, _("Info")),
    (ACTION_INSTRUCTION, _("Instruction")),
    (ACTION_INSTRUCTION_COMMIT, _("Instruction Commit")),
)

SYSTEM_PRESETS = [
    PRESET_INFO,
    PRESET_INSTRUCTION,
]
