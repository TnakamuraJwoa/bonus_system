from .settings_common import *



# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'db_connect',
        'USER': 'postgres',
        'PASSWORD': 'admin',
        'HOST': '',
        'POST': '',
        'ATOMIC_REQUESTS': True,  # 追加
    },
    "rds": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "bonus_db",
        "USER": "admin",
        "PASSWORD": "#1qaz3edc5tgb#",
        "HOST": "jwoashop-prod-mysql.cvposccznprz.ap-northeast-1.rds.amazonaws.com",
        "PORT": "3306",
        "OPTIONS": {"charset": "utf8mb4"},
    },
}

#ロギング設定
LOGGING = {
    'version': 1, # 1固定
    'disable_existing_loggers': False,

    #ロガーの設定
    'loggers': {
        # Djangoが利用するロガー
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        # diaryアプリケーションが利用するロガー
        'connect': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },

    #ハンドラの設定
    'handlers': {
        'console':{
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'dev'
        },
    },

    #フォーマッタの設定
    'formatters':{
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
