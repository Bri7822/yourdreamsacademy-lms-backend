# project_config/env/local.py
#
# Local development overrides.
# Run with: DJANGO_SETTINGS_MODULE=project_config.env.local
#
from .common import *  # noqa

# ---------------------------------------------------------------------------
# Security — relaxed for local dev
# ---------------------------------------------------------------------------
SECRET_KEY = 'django-insecure-local-dev-only-do-not-use-in-production-abc123'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# ---------------------------------------------------------------------------
# Database — local PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'academy_db',
        'USER': 'bright_admin',
        'PASSWORD': 'Jef7801@',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# ---------------------------------------------------------------------------
# CORS — allow Vite dev server
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]

# ---------------------------------------------------------------------------
# Email — print to console, no SMTP needed
# ---------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'dev@dreamsacademy.local'

# ---------------------------------------------------------------------------
# Frontend URL (used in email links)
# ---------------------------------------------------------------------------
FRONTEND_URL = 'http://localhost:5173/'

SITE_ID = 1

# ---------------------------------------------------------------------------
# PayPal — sandbox
# ---------------------------------------------------------------------------
PAYPAL_BASE_URL = 'https://api-m.sandbox.paypal.com'
PAYPAL_CLIENT_ID = 'Adwdb7v2HDbG4nUfTOyRcCUm_V4p59L4_0xXBeM6GuQEeS9Uzbr9-DYGETUM3uLp88rgRV7y9kHHh0yJ'
PAYPAL_SECRET = 'EF18NODaENMQ3DzJ4xoJfCES2x_JdB1teWwGX3HQ64iudXnAM460qnIibpKtTe5ag_HO-G_6m3P_dg2MU'