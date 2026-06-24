import json
import logging

from django.db import connections


logger = logging.getLogger(__name__)


def _json_value(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_change_audit(
    request,
    *,
    screen_name,
    action_type,
    target_table,
    target_pk=None,
    summary=None,
    before_values=None,
    after_values=None,
    changed_by=None,
):
    """共通変更履歴をRDSへ記録する。"""
    user = getattr(request, "user", None)
    changed_by = getattr(user, "username", "") or changed_by or "anonymous"
    request_path = request.get_full_path() if request else None
    client_ip = get_client_ip(request) if request else None

    sql = """
        INSERT INTO bonus_db.change_audit_log (
            changed_at,
            changed_by,
            screen_name,
            action_type,
            target_table,
            target_pk,
            summary,
            before_values,
            after_values,
            request_path,
            client_ip
        ) VALUES (
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo'),
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
    """

    with connections["rds"].cursor() as cursor:
        logger.info(
            "共通変更履歴INSERT SQLを実行します。screen=%s action=%s table=%s pk=%s",
            screen_name,
            action_type,
            target_table,
            target_pk,
        )
        cursor.execute(
            sql,
            [
                changed_by,
                screen_name,
                action_type,
                target_table,
                str(target_pk) if target_pk is not None else None,
                summary,
                _json_value(before_values),
                _json_value(after_values),
                request_path,
                client_ip,
            ],
        )


def fetch_one_dict(using, sql, params=None):
    with connections[using].cursor() as cursor:
        cursor.execute(sql, params or [])
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None
