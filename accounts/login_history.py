import logging

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction

from .models import LoginHistory


logger = logging.getLogger(__name__)


def _get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.META.get("REMOTE_ADDR")

    if not ip_address:
        return None

    try:
        validate_ipv46_address(ip_address)
    except ValidationError:
        logger.warning("ログイン履歴のIPアドレス形式が不正です。ip=%s", ip_address)
        return None

    return ip_address


def record_login_history(request, user, event_type):
    """ログイン/ログアウト履歴を認証DBへ記録する。"""
    if request is None or user is None:
        return

    username = getattr(user, "username", "") or "anonymous"
    user_obj = user if getattr(user, "is_authenticated", False) else None

    try:
        with transaction.atomic(using="default"):
            LoginHistory.objects.using("default").create(
                user=user_obj,
                username=username,
                event_type=event_type,
                ip_address=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                session_key=request.session.session_key or "",
                request_path=request.get_full_path()[:500],
            )
    except Exception:
        logger.exception(
            "ログイン履歴の記録に失敗しました。username=%s event_type=%s",
            username,
            event_type,
        )
