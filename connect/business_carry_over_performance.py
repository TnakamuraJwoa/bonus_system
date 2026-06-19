import logging
import math

from django.db import ProgrammingError, connections
from django.views import generic

from .views import KeysetPaginationMixin


logger = logging.getLogger(__name__)

BASIC_BV_LINE_TABLE = "bonus_db.basic_bv_line"


def is_missing_table_error(exc):
    return bool(exc.args and exc.args[0] == 1146)


def fetch_carry_over_history_rows():
    sql = f"""
        SELECT
            h.kibetu,
            h.row_count,
            h.created_at,
            h.updated_at,
            pm.st_date,
            pm.end_date,
            pm.completion_date,
            NULL AS year,
            NULL AS month,
            NULL AS payment_date
        FROM (
            SELECT
                kibetu,
                COUNT(*) AS row_count,
                MIN(created_at) AS created_at,
                MAX(created_at) AS updated_at
            FROM {BASIC_BV_LINE_TABLE}
            GROUP BY kibetu
        ) AS h
        LEFT JOIN bonus_db.period_master AS pm
          ON pm.kibetu = h.kibetu
        ORDER BY h.kibetu DESC
    """
    with connections["rds"].cursor() as cursor:
        logger.info("繰り越し業績履歴取得SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
        try:
            cursor.execute(sql)
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except ProgrammingError as exc:
            if is_missing_table_error(exc):
                logger.info("繰り越し業績テーブルが未作成です。table=%s", BASIC_BV_LINE_TABLE)
                return []
            raise


class CarryOverPerformanceView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "business_carry_over_performance.html"

    def _build_where(self, q_kibetu="", q_placement_code="", q_jmoa_code=""):
        where = []
        params = []

        if q_kibetu:
            where.append("kibetu = %s")
            params.append(q_kibetu)

        if q_placement_code:
            where.append("placement_code LIKE %s")
            params.append(f"%{q_placement_code}%")

        if q_jmoa_code:
            where.append("jmoa_code LIKE %s")
            params.append(f"%{q_jmoa_code}%")

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return where_sql, params

    def _fetch_total_count(self, q_kibetu="", q_placement_code="", q_jmoa_code=""):
        where_sql, params = self._build_where(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
        )
        sql = f"""
            SELECT COUNT(*)
            FROM {BASIC_BV_LINE_TABLE}
            {where_sql}
        """
        with connections["rds"].cursor() as cursor:
            logger.info("繰り越し業績件数取得SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("繰り越し業績テーブルが未作成です。table=%s", BASIC_BV_LINE_TABLE)
                    return 0
                raise
        return int(row[0]) if row else 0

    def _fetch_rows(self, q_kibetu="", q_placement_code="", q_jmoa_code="", limit=200, offset=0):
        where_sql, params = self._build_where(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
        )
        sql = f"""
            SELECT
                id,
                kibetu,
                placement_code,
                jmoa_code,
                bv,
                carry_over_bv,
                created_at
            FROM {BASIC_BV_LINE_TABLE}
            {where_sql}
            ORDER BY kibetu DESC, placement_code, jmoa_code
            LIMIT %s OFFSET %s
        """
        with connections["rds"].cursor() as cursor:
            logger.info("繰り越し業績一覧取得SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
            try:
                cursor.execute(sql, params + [limit, offset])
                cols = [col[0] for col in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("繰り越し業績テーブルが未作成です。table=%s", BASIC_BV_LINE_TABLE)
                    return []
                raise

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q_kibetu = (self.request.GET.get("q_kibetu") or "").strip()
        q_placement_code = (self.request.GET.get("q_placement_code") or "").strip()
        q_jmoa_code = (self.request.GET.get("q_jmoa_code") or "").strip()
        kibetu_choice_mode = self.request.GET.get("kibetu_choice_mode") or "recent"

        per_page = self.get_per_page()
        total_count = self._fetch_total_count(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
        )
        total_pages = max(1, math.ceil(total_count / per_page))
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page

        rows = self._fetch_rows(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
            limit=per_page,
            offset=offset,
        )

        ctx["q_kibetu"] = q_kibetu
        ctx["q_placement_code"] = q_placement_code
        ctx["q_jmoa_code"] = q_jmoa_code
        ctx["active_menu"] = "business_carry_over_performance"
        ctx["registration_history_rows"] = fetch_carry_over_history_rows()
        ctx["registration_history_modal_id"] = "carryOverPerformanceHistoryModal"
        ctx["registration_modal_title"] = "登録履歴（繰り越し業績照会）"
        ctx["registration_target_url_name"] = "connect:business_carry_over_performance"
        return self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params={
                "q_kibetu": q_kibetu,
                "q_placement_code": q_placement_code,
                "q_jmoa_code": q_jmoa_code,
                "per_page": per_page,
                "kibetu_choice_mode": kibetu_choice_mode,
            },
        )
