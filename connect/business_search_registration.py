import logging

from django.db import ProgrammingError, connections


logger = logging.getLogger(__name__)

WEEK_PERSONAL_RESULT_TABLE = "bonus_db.B_week_bonus_result"
MONTH_PERSONAL_RESULT_TABLE = "bonus_db.B_month_bonus_result"
TEAM_BUSINESS_SEARCH_RESULT_TABLE = "bonus_db.B_team_business_search_result"


def is_missing_table_error(exc):
    return bool(exc.args and exc.args[0] == 1146)


def fetch_registration_history_rows(
    result_table,
    kibetu_like=None,
    kibetu_not_like=None,
    period_type=None,
):
    where = []
    params = []

    if kibetu_like:
        where.append("kibetu LIKE %s")
        params.append(kibetu_like)

    if kibetu_not_like:
        where.append("kibetu NOT LIKE %s")
        params.append(kibetu_not_like)

    if period_type:
        where.append("period_type = %s")
        params.append(period_type)

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT
            h.kibetu,
            h.row_count,
            h.created_at,
            h.updated_at,
            pm.st_date,
            pm.end_date,
            pm.completion_date,
            mp.year,
            mp.month,
            mp.payment_date
        FROM (
            SELECT
            kibetu,
            COUNT(*) AS row_count,
            MIN(created_at) AS created_at,
            MAX(updated_at) AS updated_at
            FROM {result_table}
            {where_sql}
            GROUP BY kibetu
        ) AS h
        LEFT JOIN bonus_db.period_master AS pm
          ON pm.kibetu = h.kibetu
        LEFT JOIN bonus_db.monthly_period AS mp
          ON mp.kibetu = h.kibetu
        ORDER BY h.kibetu DESC
    """
    with connections["rds"].cursor() as cursor:
        logger.info("業務検索登録履歴取得SQLを実行します。table=%s", result_table)
        try:
            cursor.execute(sql, params)
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except ProgrammingError as exc:
            if is_missing_table_error(exc):
                logger.info("業務検索登録履歴テーブルが未作成です。table=%s", result_table)
                return []
            raise
