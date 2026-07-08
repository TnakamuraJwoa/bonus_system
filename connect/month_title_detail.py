import logging
import math
from urllib.parse import urlencode

from django.db import connections
from django.views import generic

from connect.models import MonthlyPeriod
from connect.sql.month_title_detail_sql import (
    MONTH_TITLE_DETAIL_CTE_SQL,
    MONTH_TITLE_LINE_SUMMARY_SQL,
    MONTH_TITLE_PAYER_DETAIL_SQL,
)


logger = logging.getLogger(__name__)


class MonthTitleDetailView(generic.TemplateView):
    template_name = "month_title_detail.html"
    DEFAULT_PER_PAGE = 100
    MAX_PER_PAGE = 500

    def _get_per_page(self):
        try:
            per_page = int(self.request.GET.get("per_page") or self.DEFAULT_PER_PAGE)
        except ValueError:
            per_page = self.DEFAULT_PER_PAGE
        return max(1, min(per_page, self.MAX_PER_PAGE))

    def _get_page(self, total_pages):
        try:
            page = int(self.request.GET.get("page") or "1")
        except ValueError:
            page = 1
        return max(1, min(page, total_pages))

    @staticmethod
    def _build_base_qs(params):
        return urlencode({
            key: value
            for key, value in params.items()
            if value not in ("", None)
        })

    @staticmethod
    def _pagination_pages(current_page, total_pages, adjacent=3):
        if total_pages <= 1:
            return []

        pages = []
        if current_page > adjacent + 1:
            pages.append(1)
            pages.append(None)

        start = max(1, current_page - adjacent)
        end = min(total_pages, current_page + adjacent)
        pages.extend(range(start, end + 1))

        if current_page < total_pages - adjacent:
            pages.append(None)
            pages.append(total_pages)

        return pages

    def _get_registered_periods(self):
        sql = """
            SELECT DISTINCT
                mt.kibetu,
                mp.year,
                mp.month,
                mp.payment_date
            FROM bonus_db.month_title AS mt
            LEFT JOIN bonus_db.monthly_period AS mp
              ON mt.kibetu = mp.kibetu
            ORDER BY
                mp.year DESC,
                mp.month DESC,
                mt.kibetu DESC
        """
        with connections["rds"].cursor() as cursor:
            logger.info("月タイトル詳細 登録済み期別SQLを実行します。")
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _get_title_result(self, kibetu, target_jwoa_code):
        sql = """
            SELECT
                mt.kibetu,
                mt.jwoa_code,
                mt.jwoa_name,
                mt.income_line_bv,
                mt.basic_line_bv,
                mt.title_id,
                COALESCE(tm.title_name, 'タイトルなし') AS title_name,
                mt.updated_at
            FROM bonus_db.month_title AS mt
            LEFT JOIN bonus_db.title_master AS tm
              ON mt.title_id = tm.title_id
            WHERE mt.kibetu = %s
              AND mt.jwoa_code = %s
            LIMIT 1
        """
        with connections["rds"].cursor() as cursor:
            logger.info("月タイトル詳細 対象月タイトルSQLを実行します。")
            cursor.execute(sql, [kibetu, target_jwoa_code])
            row = cursor.fetchone()
            if not row:
                return None
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))

    def _fetch_month_title_rows(self, kibetu):
        sql = """
            SELECT
                mt.id,
                mt.kibetu,
                mt.jwoa_code,
                mt.jwoa_name,
                mt.income_line_bv,
                mt.basic_line_bv,
                COALESCE(tm.title_name, 'タイトルなし') AS title_name,
                mt.updated_at
            FROM bonus_db.month_title AS mt
            LEFT JOIN bonus_db.title_master AS tm
              ON mt.title_id = tm.title_id
            WHERE mt.kibetu = %s
            ORDER BY
                mt.title_id DESC,
                mt.income_line_bv DESC,
                mt.basic_line_bv DESC,
                mt.jwoa_code
        """
        with connections["rds"].cursor() as cursor:
            logger.info("月タイトル詳細 月タイトル一覧SQLを実行します。")
            cursor.execute(sql, [kibetu])
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _fetch_line_summary_rows(self, period, target_jwoa_code):
        sql = MONTH_TITLE_LINE_SUMMARY_SQL.format(cte_sql=MONTH_TITLE_DETAIL_CTE_SQL)
        params = [period.year, period.month, target_jwoa_code]
        with connections["rds"].cursor() as cursor:
            logger.info("月タイトル詳細 ライン別集計SQLを実行します。")
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _build_detail_filters(filters):
        where = []
        params = []

        if filters["line_type"] in ("1", "2"):
            where.append("itb.rn = %s")
            params.append(int(filters["line_type"]))

        if filters["q_line_code"]:
            where.append("pt.line_code LIKE %s")
            params.append(f"%{filters['q_line_code']}%")

        if filters["q_payer_code"]:
            where.append("pt.payer_code LIKE %s")
            params.append(f"%{filters['q_payer_code']}%")

        if filters["q_payer_name"]:
            where.append("pt.payer_name LIKE %s")
            params.append(f"%{filters['q_payer_name']}%")

        return where, params

    def _build_detail_sql(self, filters):
        sql = MONTH_TITLE_PAYER_DETAIL_SQL.format(cte_sql=MONTH_TITLE_DETAIL_CTE_SQL)
        where, params = self._build_detail_filters(filters)
        if where:
            sql += "\n  AND " + "\n  AND ".join(where)
        return sql, params

    def _count_detail_rows(self, period, target_jwoa_code, filters):
        where, filter_params = self._build_detail_filters(filters)
        sql = f"""
            {MONTH_TITLE_DETAIL_CTE_SQL}
            SELECT COUNT(*)
            FROM payer_order_tree AS pt
            JOIN introducer_total_bv AS itb
              ON itb.upper_code = pt.upper_code
             AND itb.line_code = pt.line_code
            WHERE pt.upper_code = %s
        """
        if where:
            sql += "\n              AND " + "\n              AND ".join(where)
        params = [period.year, period.month, target_jwoa_code, *filter_params]
        with connections["rds"].cursor() as cursor:
            logger.info("月タイトル詳細 購入者明細COUNT SQLを実行します。")
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _fetch_detail_rows(self, period, target_jwoa_code, filters, limit, offset):
        detail_sql, filter_params = self._build_detail_sql(filters)
        sql = f"""
            {detail_sql}
            ORDER BY
                itb.rn,
                pt.line_code,
                pt.lvl,
                pt.payer_code,
                pt.bonus_payment_date,
                pt.order_code
            LIMIT %s OFFSET %s
        """
        params = [
            period.year,
            period.month,
            target_jwoa_code,
            *filter_params,
            limit,
            offset,
        ]
        with connections["rds"].cursor() as cursor:
            logger.info("月タイトル詳細 購入者明細SELECT SQLを実行します。")
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = (self.request.GET.get("kibetu") or "").strip()
        target_jwoa_code = (self.request.GET.get("jwoa_code") or "").strip()
        detail_fullscreen = self.request.GET.get("detail_fullscreen") == "1"
        filters = {
            "line_type": (self.request.GET.get("line_type") or "").strip(),
            "q_line_code": (self.request.GET.get("q_line_code") or "").strip(),
            "q_payer_code": (self.request.GET.get("q_payer_code") or "").strip(),
            "q_payer_name": (self.request.GET.get("q_payer_name") or "").strip(),
        }
        per_page = self._get_per_page()

        ctx.update({
            "period_options": self._get_registered_periods(),
            "selected_kibetu": selected_kibetu,
            "target_jwoa_code": target_jwoa_code,
            "line_type": filters["line_type"],
            "q_line_code": filters["q_line_code"],
            "q_payer_code": filters["q_payer_code"],
            "q_payer_name": filters["q_payer_name"],
            "per_page": per_page,
            "selected_period": None,
            "title_result": None,
            "month_title_rows": [],
            "line_summary_rows": [],
            "detail_rows": [],
            "is_searched": bool(selected_kibetu or target_jwoa_code),
            "detail_fullscreen": detail_fullscreen,
        })

        base_params = {
            "kibetu": selected_kibetu,
            "jwoa_code": target_jwoa_code,
            "line_type": filters["line_type"],
            "q_line_code": filters["q_line_code"],
            "q_payer_code": filters["q_payer_code"],
            "q_payer_name": filters["q_payer_name"],
            "per_page": per_page,
        }
        detail_fullscreen_params = {
            **base_params,
            "detail_fullscreen": "1",
        }

        if not selected_kibetu:
            return self._set_page_context(ctx, [], per_page, 0, 1, 1, base_params)

        period = MonthlyPeriod.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return self._set_page_context(ctx, [], per_page, 0, 1, 1, base_params)

        ctx["selected_period"] = period
        if not target_jwoa_code:
            ctx["month_title_rows"] = self._fetch_month_title_rows(selected_kibetu)
            return self._set_page_context(ctx, [], per_page, 0, 1, 1, base_params)

        ctx["title_result"] = self._get_title_result(selected_kibetu, target_jwoa_code)
        if not ctx["title_result"]:
            return self._set_page_context(ctx, [], per_page, 0, 1, 1, base_params)

        ctx["line_summary_rows"] = self._fetch_line_summary_rows(period, target_jwoa_code)
        total_count = self._count_detail_rows(period, target_jwoa_code, filters)
        if detail_fullscreen:
            total_pages = 1
            page = 1
            limit = total_count
            offset = 0
        else:
            total_pages = max(1, math.ceil(total_count / per_page))
            page = self._get_page(total_pages)
            limit = per_page
            offset = (page - 1) * per_page
        detail_rows = []
        if total_count:
            detail_rows = self._fetch_detail_rows(
                period,
                target_jwoa_code,
                filters,
                limit,
                offset,
            )

        return self._set_page_context(
            ctx,
            detail_rows,
            per_page,
            total_count,
            total_pages,
            page,
            base_params,
            detail_fullscreen_params,
        )

    def _set_page_context(
        self,
        ctx,
        rows,
        per_page,
        total_count,
        total_pages,
        page,
        base_params,
        detail_fullscreen_params=None,
    ):
        ctx["detail_rows"] = rows
        ctx["total_count"] = total_count
        ctx["per_page"] = per_page
        ctx["page"] = page
        ctx["total_pages"] = total_pages
        if total_count > 0:
            ctx["display_from"] = (page - 1) * per_page + 1
            ctx["display_to"] = min(ctx["display_from"] + len(rows) - 1, total_count)
        else:
            ctx["display_from"] = 0
            ctx["display_to"] = 0
        ctx["base_qs"] = self._build_base_qs(base_params)
        ctx["detail_fullscreen_qs"] = self._build_base_qs(
            detail_fullscreen_params or {**base_params, "detail_fullscreen": "1"}
        )
        ctx["detail_normal_qs"] = self._build_base_qs(base_params)
        ctx["has_prev"] = page > 1
        ctx["has_next"] = page < total_pages
        ctx["prev_page"] = page - 1
        ctx["next_page"] = page + 1
        ctx["pagination_pages"] = self._pagination_pages(page, total_pages)
        return ctx
