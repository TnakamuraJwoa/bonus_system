from django.contrib.messages import constants as messages
import os
from pathlib import Path



AUTH_USER_MODEL = 'accounts.CustomUser'

# カスタムフォームの設定
ACCOUNT_FORMS = {
    'login': 'accounts.forms.CustomLoginForm',
}
ACCOUNT_ADAPTER = 'accounts.adapter.LastVisitedAccountAdapter'

NUMBER_GROUPING = 3

# django-allauthで利用するdjango.contrib.sitesを使うためにサイト識別用IDを設定
SITE_ID = 1

AUTHENTICATION_BACKENDS = (
    'allauth.account.auth_backends.AuthenticationBackend',
)

#メールアドレス認証に変更する設定
ACCOUNT_AUTHENTICATION_METHOD = 'username'
# ユーザー名を要求しない
ACCOUNT_USERNAME_REQUIRED = True
# メールアドレス入力を必須にしない
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = 'none'

# ログイン/ログアウト後の遷移先を設定
LOGIN_REDIRECT_URL = 'connect:users'
ACCOUNT_LOGOUT_REDIRECT_URL = 'account_login'

# ログアウトリンクのクリック一発でログアウトする設定
ACCOUNT_LOGOUT_ON_GET = True

# 1時間操作がなければセッションを失効させる
SESSION_IDLE_TIMEOUT = 60 * 60
SESSION_COOKIE_AGE = SESSION_IDLE_TIMEOUT
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
LOGIN_URL = '/accounts/login/'
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'


STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

MEDIA_URL = '/media/'


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-+vh0@p=u0l2)#g316f0*lag3x6#^v*b^k2elf4)taz^lpwog^x'


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'connect.apps.ConnectConfig',
    'accounts.apps.AccountsConfig',

    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'import_export',
    'django.contrib.humanize'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'connect.middleware.LoginRequiredMiddleware',
    'connect.middleware.SessionIdleTimeoutMiddleware',
    'connect.middleware.UserPermissionMiddleware',
    'connect.middleware.LastVisitedPageMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'connect_app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'connect', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.user_access',
            ],
        },
    },
]

WSGI_APPLICATION = 'connect_app.wsgi.application'



# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'ja'

TIME_ZONE = 'Asia/Tokyo'

USE_I18N = True

USE_TZ = True


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


MESSAGE_TAGS = {
    messages.ERROR:'alert alert-danger',
    messages.WARNING: 'alert alert-warning',
    messages.SUCCESS: 'alert alert-success',
    messages.INFO: 'alert alert-info',
}

RESERVATION_LIMIT_HOURS = 1