import logging
import math
from urllib.parse import urlencode

import openpyxl

from django.contrib import messages
from django.db import connections, transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import generic

from connect.audit import record_change_audit
from connect.introducer_tree_builder import (
    build_introducer_tree_view,
    fetch_introducer_tree_search_path,
)
from connect.sql.introducer_tree_sql import INTRODUCER_TREE_REBUILD_CACHE_SQL
from connect.views import KeysetPaginationMixin

logger = logging.getLogger(__name__)


class IntroducerTreeView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "introducer_tree.html"

    DEFAULT_PER_PAGE = 200
    MAX_PER_PAGE = 500

    def _build_where(
        self,
        q_jwoa_code: str,
        q_name: str,
        q_introducer_code: str,
        q_introducer_rank: str,
        q_rank: str,
    ):
        where = []
        params = []

        if q_jwoa_code:
            where.append("c.jwoa_code LIKE %s")
            params.append(f"{q_jwoa_code}%")

        if q_name:
            where.append("c.jwoa_name LIKE %s")
            params.append(f"%{q_name}%")

        if q_introducer_code:
            where.append("c.introducer_code LIKE %s")
            params.append(f"{q_introducer_code}%")

        if q_introducer_rank:
            where.append("c.introducer_rank = %s")
            params.append(q_introducer_rank)

        if q_rank:
            where.append("c.`rank` = %s")
            params.append(q_rank)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        return where_sql, params

    def _fetch_total_count(
        self,
        q_jwoa_code: str,
        q_name: str,
        q_introducer_code: str,
        q_introducer_rank: str,
        q_rank: str,
    ) -> int:
        where_sql, params = self._build_where(
            q_jwoa_code,
            q_name,
            q_introducer_code,
            q_introducer_rank,
            q_rank,
        )

        sql = f"""
SELECT COUNT(*)
FROM bonus_db.C_users_introducer_tree_cache c
{where_sql}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            return int(cursor.fetchone()[0])

    def _fetch_rows(
        self,
        q_jwoa_code: str,
        q_name: str,
        q_introducer_code: str,
        q_introducer_rank: str,
        q_rank: str,
        limit: int,
        offset: int = 0,
    ):
        where_sql, params = self._build_where(
            q_jwoa_code,
            q_name,
            q_introducer_code,
            q_introducer_rank,
            q_rank,
        )

        sql = f"""
SELECT
    c.id,
    c.introducer_code,
    c.introducer_name,
    c.introducer_rank,
    c.jwoa_code,
    c.jwoa_name,
    c.`rank`,
    c.tree_level,
    c.created_at
FROM bonus_db.C_users_introducer_tree_cache c
{where_sql}
ORDER BY c.id
LIMIT %s OFFSET %s
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params + [limit, offset])
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _rebuild_cache(self) -> int:
        delete_sql = "DELETE FROM bonus_db.C_users_introducer_tree_cache"

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                logger.info("紹介者Treeキャッシュ再作成前削除SQLを実行します。")
                cursor.execute(delete_sql)
                logger.info("紹介者Treeキャッシュ再作成INSERT SQLを実行します。")
                cursor.execute(INTRODUCER_TREE_REBUILD_CACHE_SQL)
                inserted_count = cursor.rowcount

        return inserted_count

    def _delete_all_cache(self) -> int:
        sql = "DELETE FROM bonus_db.C_users_introducer_tree_cache"

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                cursor.execute(sql)
                deleted_count = cursor.rowcount

        return deleted_count

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()

        try:
            if action == "copy":
                inserted_count = self._rebuild_cache()
                record_change_audit(
                    request,
                    screen_name="紹介者 Tree",
                    action_type="bulk_create",
                    target_table="C_users_introducer_tree_cache",
                    target_pk=None,
                    summary=f"紹介者 Treeテーブルを再作成: {inserted_count}件",
                    before_values=None,
                    after_values={"count": inserted_count},
                )
                messages.success(
                    request,
                    f"紹介者 Treeテーブルを {inserted_count} 件で再作成しました。"
                )
            elif action == "delete":
                deleted_count = self._delete_all_cache()
                record_change_audit(
                    request,
                    screen_name="紹介者 Tree",
                    action_type="bulk_delete",
                    target_table="C_users_introducer_tree_cache",
                    target_pk=None,
                    summary=f"紹介者 Treeテーブルを全件削除: {deleted_count}件",
                    before_values={"count": deleted_count},
                    after_values=None,
                )
                messages.success(
                    request,
                    "紹介者 Treeテーブルを全件削除しました。"
                )
            else:
                messages.warning(request, "不正な操作です。")
        except Exception as e:
            messages.error(request, f"処理中にエラーが発生しました: {e}")

        return redirect("connect:introducer_tree")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_jwoa_code = (self.request.GET.get("q_jwoa_code") or "").strip()
        q_name = (self.request.GET.get("q_name") or "").strip()
        q_introducer_code = (
            self.request.GET.get("q_introducer_code") or ""
        ).strip()
        q_introducer_rank = (
            self.request.GET.get("q_introducer_rank") or ""
        ).strip()
        q_rank = (self.request.GET.get("q_rank") or "").strip()
        tree_search = (self.request.GET.get("tree_search") or "").strip()

        try:
            per_page = int(
                self.request.GET.get("per_page") or str(self.DEFAULT_PER_PAGE)
            )
        except ValueError:
            per_page = self.DEFAULT_PER_PAGE
        per_page = max(1, min(per_page, self.MAX_PER_PAGE))

        total_count = self._fetch_total_count(
            q_jwoa_code,
            q_name,
            q_introducer_code,
            q_introducer_rank,
            q_rank,
        )
        total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 1
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page

        rows = self._fetch_rows(
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_introducer_code=q_introducer_code,
            q_introducer_rank=q_introducer_rank,
            q_rank=q_rank,
            limit=per_page,
            offset=offset,
        )

        base_params = {}
        if q_jwoa_code:
            base_params["q_jwoa_code"] = q_jwoa_code
        if q_name:
            base_params["q_name"] = q_name
        if q_introducer_code:
            base_params["q_introducer_code"] = q_introducer_code
        if q_introducer_rank:
            base_params["q_introducer_rank"] = q_introducer_rank
        if q_rank:
            base_params["q_rank"] = q_rank
        if tree_search:
            base_params["tree_search"] = tree_search
        if per_page != self.DEFAULT_PER_PAGE:
            base_params["per_page"] = per_page

        ctx["q_jwoa_code"] = q_jwoa_code
        ctx["q_name"] = q_name
        ctx["q_introducer_code"] = q_introducer_code
        ctx["q_introducer_rank"] = q_introducer_rank
        ctx["q_rank"] = q_rank
        ctx["tree_search"] = tree_search

        view_mode = (self.request.GET.get("view") or "list").strip()
        if view_mode not in ("list", "tree"):
            view_mode = "list"
        ctx["view_mode"] = view_mode

        tab_params = dict(base_params)
        ctx["list_tab_query"] = urlencode(tab_params) if tab_params else ""
        tree_tab_params = dict(tab_params)
        tree_tab_params["view"] = "tree"
        ctx["tree_tab_query"] = urlencode(tree_tab_params)

        tree_root_code = q_jwoa_code or q_introducer_code
        tree_context = build_introducer_tree_view(tree_root_code)
        ctx.update(tree_context)
        tree_search_path_rows = (
            fetch_introducer_tree_search_path(tree_root_code, tree_search)
            if view_mode == "tree" and tree_root_code and tree_search
            else []
        )
        ctx["tree_search_path_rows"] = tree_search_path_rows
        ctx["tree_search_target"] = (
            next((row for row in tree_search_path_rows if row.get("is_target")), None)
            if tree_search_path_rows
            else None
        )
        ctx["tree_search_not_found"] = bool(
            view_mode == "tree"
            and tree_root_code
            and tree_search
            and not tree_search_path_rows
        )

        return self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params=base_params,
        )


class IntroducerTreeExportView(IntroducerTreeView):
    EXPORT_FETCH_SIZE = 5000
    RANK_LABELS = {
        1: "シルバー",
        2: "ゴールド",
        3: "プラチナ",
        4: "ダイヤ",
        9: "一般会員",
    }

    def _rank_label(self, value):
        return self.RANK_LABELS.get(value, "-")

    def get(self, request, *args, **kwargs):
        q_jwoa_code = (request.GET.get("q_jwoa_code") or "").strip()
        q_name = (request.GET.get("q_name") or "").strip()
        q_introducer_code = (request.GET.get("q_introducer_code") or "").strip()
        q_introducer_rank = (request.GET.get("q_introducer_rank") or "").strip()
        q_rank = (request.GET.get("q_rank") or "").strip()

        where_sql, params = self._build_where(
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_introducer_code=q_introducer_code,
            q_introducer_rank=q_introducer_rank,
            q_rank=q_rank,
        )

        sql = f"""
SELECT
    c.id,
    c.introducer_code,
    c.introducer_name,
    c.introducer_rank,
    c.jwoa_code,
    c.jwoa_name,
    c.`rank`,
    c.tree_level,
    c.created_at
FROM bonus_db.C_users_introducer_tree_cache c
{where_sql}
ORDER BY c.id
        """

        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet("紹介者Tree")
        ws.append([
            "ID",
            "紹介者コード",
            "紹介者名",
            "紹介者ランク",
            "会員コード",
            "会員名",
            "ランク",
            "階層",
            "作成日時",
        ])

        with connections["rds"].cursor() as cursor:
            logger.info("紹介者Tree Excel出力SQLを実行します。")
            cursor.execute(sql, params)
            while True:
                rows = cursor.fetchmany(self.EXPORT_FETCH_SIZE)
                if not rows:
                    break
                for row in rows:
                    ws.append([
                        row[0],
                        row[1],
                        row[2],
                        self._rank_label(row[3]),
                        row[4],
                        row[5],
                        self._rank_label(row[6]),
                        row[7],
                        row[8],
                    ])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            'attachment; filename="introducer_tree.xlsx"'
        )
        wb.save(response)
        return response
