from .settings_common import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.getenv("POSTGRES_DB"),
        'USER': os.getenv("POSTGRES_DB_USER"),
        'PASSWORD': os.getenv("POSTGRES_DB_PASSWORD"),
        'HOST': os.getenv("POSTGRES_DB_HOST"),
        'PORT': os.getenv("POSTGRES_DB_PORT"),
        'ATOMIC_REQUESTS': True,
    },

    "rds": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("RDS_DB_NAME"),
        "USER": os.getenv("RDS_DB_USER"),
        "PASSWORD": os.getenv("RDS_DB_PASSWORD"),
        "HOST": os.getenv("RDS_DB_HOST"),
        "PORT": os.getenv("RDS_DB_PORT"),
        "OPTIONS": {
            "charset": "utf8mb4"
        },
    },
}

# ロギング設定
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # ロガー設定
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },

        'connect': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },

    # ハンドラ設定
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'dev'
        },
    },

    # フォーマッタ設定
    'formatters': {
        'dev': {
            'format': '\t'.join([
                '%(asctime)s',
                '[%(levelname)s]',
                '%(pathname)s(Line:%(lineno)d)',
                '%(message)s'
            ])
        },
    }
}