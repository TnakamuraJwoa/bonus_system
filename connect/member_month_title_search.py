import logging
import math

from django.contrib import messages
from django.db import connections
from django.views import generic

from connect.models import TitleMaster
from connect.views import KeysetPaginationMixin


logger = logging.getLogger(__name__)


class MemberMonthTitleSearchView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "member_month_title_search.html"
    DEFAULT_PER_PAGE = 200
    MAX_PER_PAGE = 500

    def get_title_options(self):
        title_options = [{"title_id": "0", "title_name": "タイトルなし"}]
        title_options.extend(
            {
                "title_id": str(title.title_id),
                "title_name": title.title_name,
            }
            for title in TitleMaster.objects.using("rds").order_by("title_id")
        )
        return title_options

    def get_registered_kibetu_options(self):
        sql = """
            SELECT DISTINCT
                mt.kibetu,
                mp.year,
                mp.month
            FROM bonus_db.month_title AS mt
            LEFT JOIN bonus_db.monthly_period AS mp
              ON mt.kibetu = mp.kibetu
            ORDER BY
                mp.year DESC,
                mp.month DESC,
                mt.kibetu DESC
        """
        with connections["rds"].cursor() as cursor:
            logger.info("会員 月タイトル検索 登録済み期別SQLを実行します。")
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _build_where(
        self,
        selected_kibetu="",
        q_jwoa_code="",
        q_name="",
        q_title_id="",
    ):
        where_clauses = ["mt.kibetu = %s"]
        params = [selected_kibetu]

        if q_jwoa_code:
            where_clauses.append("mt.jwoa_code LIKE %s")
            params.append(f"%{q_jwoa_code}%")

        if q_name:
            where_clauses.append("mt.jwoa_name LIKE %s")
            params.append(f"%{q_name}%")

        if q_title_id:
            where_clauses.append("mt.title_id = %s")
            params.append(int(q_title_id))

        return "WHERE " + " AND ".join(where_clauses), params

    def _count_rows(
        self,
        selected_kibetu="",
        q_jwoa_code="",
        q_name="",
        q_title_id="",
    ):
        where_sql, params = self._build_where(
            selected_kibetu=selected_kibetu,
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_title_id=q_title_id,
        )
        sql = f"""
            SELECT COUNT(*)
            FROM bonus_db.month_title AS mt
            {where_sql}
        """
        with connections["rds"].cursor() as cursor:
            logger.info("会員 月タイトル検索 件数SQLを実行します。")
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _fetch_rows(
        self,
        selected_kibetu="",
        q_jwoa_code="",
        q_name="",
        q_title_id="",
        limit=200,
        offset=0,
    ):
        where_sql, params = self._build_where(
            selected_kibetu=selected_kibetu,
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_title_id=q_title_id,
        )
        sql = f"""
            SELECT
                mt.id,
                mt.kibetu,
                mt.jwoa_code,
                mt.jwoa_name,
                mt.income_line_bv,
                mt.basic_line_bv,
                mt.title_id,
                COALESCE(tm.title_name, 'タイトルなし') AS title_name,
                mt.created_at,
                mt.updated_at
            FROM bonus_db.month_title AS mt
            LEFT JOIN bonus_db.title_master AS tm
              ON mt.title_id = tm.title_id
            {where_sql}
            ORDER BY mt.jwoa_code
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        with connections["rds"].cursor() as cursor:
            logger.info("会員 月タイトル検索 一覧SQLを実行します。")
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_kibetu = self.request.GET.get("q_kibetu", "").strip()
        q_jwoa_code = self.request.GET.get("q_jwoa_code", "").strip()
        q_name = self.request.GET.get("q_name", "").strip()
        q_title_id = self.request.GET.get("q_title_id", "").strip()

        ctx.update(
            {
                "q_kibetu": q_kibetu,
                "q_jwoa_code": q_jwoa_code,
                "q_name": q_name,
                "q_title_id": q_title_id,
                "registered_kibetu_options": self.get_registered_kibetu_options(),
                "title_options": self.get_title_options(),
                "selected_kibetu": q_kibetu,
                "is_searched": bool(q_kibetu or q_jwoa_code or q_name or q_title_id),
            }
        )

        if not q_kibetu:
            return self.set_page_context(
                ctx=ctx,
                rows=[],
                per_page=self.get_per_page(),
                total_count=0,
                total_pages=1,
                page=1,
                base_params=self._build_base_params(q_kibetu, q_jwoa_code, q_name, q_title_id),
            )

        try:
            total_count = self._count_rows(
                selected_kibetu=q_kibetu,
                q_jwoa_code=q_jwoa_code,
                q_name=q_name,
                q_title_id=q_title_id,
            )
        except ValueError:
            messages.error(self.request, "タイトルは数値で入力してください。")
            total_count = 0

        per_page = self.get_per_page()
        total_pages = max(1, math.ceil(total_count / per_page))
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page

        rows = []
        if total_count:
            rows = self._fetch_rows(
                selected_kibetu=q_kibetu,
                q_jwoa_code=q_jwoa_code,
                q_name=q_name,
                q_title_id=q_title_id,
                limit=per_page,
                offset=offset,
            )

        return self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params=self._build_base_params(q_kibetu, q_jwoa_code, q_name, q_title_id),
        )

    def _build_base_params(self, q_kibetu, q_jwoa_code, q_name, q_title_id):
        return {
            "q_kibetu": q_kibetu,
            "q_jwoa_code": q_jwoa_code,
            "q_name": q_name,
            "q_title_id": q_title_id,
            "per_page": self.get_per_page(),
        }
