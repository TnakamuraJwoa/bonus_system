import logging
import math

from django.contrib import messages
from django.db import connections
from django.http import HttpResponse
from django.views import generic
import openpyxl

from connect.views import KeysetPaginationMixin


logger = logging.getLogger(__name__)


class ActiveUserSearchView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "active_user_search.html"
    DEFAULT_PER_PAGE = 200
    MAX_PER_PAGE = 500

    ACTIVE_STATUS_CHOICES = (
        ("1", "アクティブ"),
        ("0", "非アクティブ"),
    )

    def _build_where(
        self,
        q_jwoa_code="",
        q_name="",
        q_year="",
        q_month="",
        q_active_status="",
    ):
        where_clauses = []
        params = []

        if q_jwoa_code:
            where_clauses.append("a.jwoa_code LIKE %s")
            params.append(f"%{q_jwoa_code}%")

        if q_name:
            where_clauses.append("u.send_bv_name LIKE %s")
            params.append(f"%{q_name}%")

        if q_year:
            where_clauses.append("a.year = %s")
            params.append(int(q_year))

        if q_month:
            where_clauses.append("a.month = %s")
            params.append(int(q_month))

        if q_active_status != "":
            where_clauses.append("a.active_status = %s")
            params.append(int(q_active_status))

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        return where_sql, params

    def _count_rows(self, q_jwoa_code="", q_name="", q_year="", q_month="", q_active_status=""):
        where_sql, params = self._build_where(
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_year=q_year,
            q_month=q_month,
            q_active_status=q_active_status,
        )

        sql = f"""
            SELECT COUNT(*)
            FROM active_users a
            LEFT JOIN nexus_production.users u
                ON a.jwoa_code = u.jmoa_code
            {where_sql}
        """

        with connections["rds"].cursor() as cursor:
            logger.info("アクティブ会員検索件数SQLを実行します。")
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _fetch_rows(
        self,
        q_jwoa_code="",
        q_name="",
        q_year="",
        q_month="",
        q_active_status="",
        limit=200,
        offset=0,
    ):
        where_sql, params = self._build_where(
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_year=q_year,
            q_month=q_month,
            q_active_status=q_active_status,
        )

        sql = f"""
            SELECT
                a.id,
                a.jwoa_code,
                u.send_bv_name,
                a.year,
                a.month,
                a.active_status,
                a.created_at
            FROM active_users a
            LEFT JOIN nexus_production.users u
                ON a.jwoa_code = u.jmoa_code
            {where_sql}
            ORDER BY a.year DESC, a.month DESC, a.jwoa_code
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        with connections["rds"].cursor() as cursor:
            logger.info("アクティブ会員検索一覧SQLを実行します。")
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_jwoa_code = self.request.GET.get("q_jwoa_code", "").strip()
        q_name = self.request.GET.get("q_name", "").strip()
        q_year = self.request.GET.get("q_year", "").strip()
        q_month = self.request.GET.get("q_month", "").strip()
        q_active_status = self.request.GET.get("q_active_status", "").strip()

        ctx["q_jwoa_code"] = q_jwoa_code
        ctx["q_name"] = q_name
        ctx["q_year"] = q_year
        ctx["q_month"] = q_month
        ctx["q_active_status"] = q_active_status
        ctx["active_status_choices"] = self.ACTIVE_STATUS_CHOICES

        try:
            total_count = self._count_rows(
                q_jwoa_code=q_jwoa_code,
                q_name=q_name,
                q_year=q_year,
                q_month=q_month,
                q_active_status=q_active_status,
            )
        except ValueError:
            messages.error(self.request, "年・月・ステータスは数値で入力してください。")
            total_count = 0

        per_page = self.get_per_page()
        total_pages = max(1, math.ceil(total_count / per_page))
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page

        rows = []
        if total_count:
            rows = self._fetch_rows(
                q_jwoa_code=q_jwoa_code,
                q_name=q_name,
                q_year=q_year,
                q_month=q_month,
                q_active_status=q_active_status,
                limit=per_page,
                offset=offset,
            )

        base_params = {
            "q_jwoa_code": q_jwoa_code,
            "q_name": q_name,
            "q_year": q_year,
            "q_month": q_month,
            "q_active_status": q_active_status,
            "per_page": per_page,
        }

        return self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params=base_params,
        )


class ActiveUserSearchExportView(ActiveUserSearchView):
    def get(self, request, *args, **kwargs):
        q_jwoa_code = request.GET.get("q_jwoa_code", "").strip()
        q_name = request.GET.get("q_name", "").strip()
        q_year = request.GET.get("q_year", "").strip()
        q_month = request.GET.get("q_month", "").strip()
        q_active_status = request.GET.get("q_active_status", "").strip()

        try:
            rows = self._fetch_rows(
                q_jwoa_code=q_jwoa_code,
                q_name=q_name,
                q_year=q_year,
                q_month=q_month,
                q_active_status=q_active_status,
                limit=1000000,
                offset=0,
            )
        except ValueError:
            rows = []

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "アクティブ会員検索"
        ws.append([
            "ID",
            "会員コード",
            "会員名",
            "年",
            "月",
            "アクティブ年月",
            "ステータス",
            "作成日時",
        ])

        for row in rows:
            active_status = row.get("active_status")
            status_label = "アクティブ" if active_status == 1 else "非アクティブ"
            year = row.get("year")
            month = row.get("month")
            ws.append([
                row.get("id"),
                row.get("jwoa_code"),
                row.get("send_bv_name"),
                year,
                month,
                f"{year}/{month}",
                status_label,
                row.get("created_at"),
            ])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            'attachment; filename="active_user_search.xlsx"'
        )
        wb.save(response)
        return response
