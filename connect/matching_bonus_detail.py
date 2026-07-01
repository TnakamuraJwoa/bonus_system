import logging
import math
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.db import connections
from django.utils.timezone import make_aware
from django.views import generic

from connect.models import PeriodMaster
from connect.introducer_tree_builder import (
    build_introducer_tree_view,
    fetch_introducer_tree_search_path,
)
from connect.placement_tree_builder import build_member_tree_view, fetch_tree_search_path
from connect.sql.matching_bonus_detail_sql import MATCHING_BONUS_DETAIL_SQL


logger = logging.getLogger(__name__)


class MatchingBonusDetailView(generic.TemplateView):
    template_name = "matching_bonus_detail.html"
    DEFAULT_PER_PAGE = 100
    MAX_PER_PAGE = 500

    def _get_period_choices(self):
        return PeriodMaster.objects.using("rds").all().order_by("-kibetu")

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

    @staticmethod
    def _build_base_qs(params):
        return urlencode({
            key: value
            for key, value in params.items()
            if value not in ("", None)
        })

    def _build_period_params(self, selected_kibetu, period):
        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])
        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)

        prev_month_start_dt = make_aware(datetime(prev_month_last.year, prev_month_last.month, 1, 0, 0, 0))
        prev_month_end_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))

        # st_date/end_date は期別の存在確認として保持。SQL条件は既存マッチングSQLと同じ前月判定を使う。
        _ = make_aware(datetime.combine(period.st_date, time.min))
        _ = make_aware(datetime.combine(period.end_date + timedelta(days=1), time.min))

        return [
            prev_month_start_dt,
            prev_month_end_dt,
            selected_kibetu,
            selected_kibetu,
        ]

    @staticmethod
    def _build_where(filters):
        where = ["1 = 1"]
        params = []

        if filters["q_member_code"]:
            where.append("member_code LIKE %s")
            params.append(f"%{filters['q_member_code']}%")
        if filters["q_member_name"]:
            where.append("member_name LIKE %s")
            params.append(f"%{filters['q_member_name']}%")
        if filters["q_introducer_code"]:
            where.append("introducer_code LIKE %s")
            params.append(f"%{filters['q_introducer_code']}%")
        if filters["q_introducer_name"]:
            where.append("introducer_name LIKE %s")
            params.append(f"%{filters['q_introducer_name']}%")

        if filters["payable_result"] == "payable":
            where.append("payable_flg = 1")
        elif filters["payable_result"] == "unpayable":
            where.append("payable_flg = 0")

        if filters["status_reason"]:
            where.append("status_reason = %s")
            params.append(filters["status_reason"])

        return "WHERE " + " AND ".join(where), params

    def _count_rows(self, base_params, filters):
        where_sql, filter_params = self._build_where(filters)
        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM (
                {MATCHING_BONUS_DETAIL_SQL}
            ) AS matching_detail
            {where_sql}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, base_params + filter_params)
            logger.info("マッチング詳細 COUNT SQLを実行します。")
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def _fetch_rows(self, base_params, filters, limit, offset):
        where_sql, filter_params = self._build_where(filters)
        sql = f"""
            SELECT *
            FROM (
                {MATCHING_BONUS_DETAIL_SQL}
            ) AS matching_detail
            {where_sql}
            ORDER BY
                introducer_code,
                payable_flg DESC,
                matching_level IS NULL,
                matching_level,
                member_code
            LIMIT %s OFFSET %s
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, base_params + filter_params + [limit, offset])
            logger.info("マッチング詳細 SELECT SQLを実行します。")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetch_introducer_summary_rows(self, base_params, introducer_codes):
        introducer_codes = sorted({code for code in introducer_codes if code})
        if not introducer_codes:
            return []

        placeholders = ", ".join(["%s"] * len(introducer_codes))
        sql = f"""
            WITH
            prev_purchase AS (
                SELECT
                    p.jwoa_code,
                    SUM(IFNULL(p.bv, 0)) AS prev_month_bv
                FROM bonus_db.purchase_info_list p
                WHERE p.bonus_payment_date >= %s
                  AND p.bonus_payment_date <  %s
                GROUP BY p.jwoa_code
            ),
            active_members AS (
                SELECT jwoa_code
                FROM bonus_db.active_users
                WHERE active_status = 1
                UNION
                SELECT jwoa_code
                FROM prev_purchase
                WHERE prev_month_bv >= 50
            ),
            basic_bonus_member AS (
                SELECT
                    placement_code AS member_code,
                    SUM(CASE WHEN bonus_amount > 0 THEN bonus_amount ELSE 0 END) AS basic_bonus_amount
                FROM bonus_db.B_basic_bonus_result
                WHERE kibetu = %s
                GROUP BY placement_code
            )
            SELECT
                intro.jmoa_code AS introducer_code,
                intro.send_bv_name AS introducer_name,
                IFNULL(intro_basic.basic_bonus_amount, 0) AS introducer_basic_bonus_amount,
                CASE WHEN IFNULL(intro_basic.basic_bonus_amount, 0) > 0 THEN 1 ELSE 0 END AS introducer_basic_acquired_flg,
                CASE WHEN intro_active.jwoa_code IS NOT NULL THEN 1 ELSE 0 END AS introducer_active_flg,
                IFNULL(intro_prev.prev_month_bv, 0) AS introducer_prev_month_bv,
                COUNT(child.jmoa_code) AS direct_member_count,
                SUM(CASE WHEN child_active.jwoa_code IS NOT NULL THEN 1 ELSE 0 END) AS direct_active_count,
                SUM(CASE WHEN IFNULL(child_basic.basic_bonus_amount, 0) > 0 THEN 1 ELSE 0 END) AS direct_basic_acquired_count
            FROM bonus_db.users AS intro
            LEFT JOIN basic_bonus_member AS intro_basic
                ON intro.jmoa_code = intro_basic.member_code
            LEFT JOIN prev_purchase AS intro_prev
                ON intro.jmoa_code = intro_prev.jwoa_code
            LEFT JOIN active_members AS intro_active
                ON intro.jmoa_code = intro_active.jwoa_code
            LEFT JOIN bonus_db.users AS child
                ON child.introducer_code = intro.jmoa_code
            LEFT JOIN basic_bonus_member AS child_basic
                ON child.jmoa_code = child_basic.member_code
            LEFT JOIN active_members AS child_active
                ON child.jmoa_code = child_active.jwoa_code
            WHERE intro.jmoa_code IN ({placeholders})
            GROUP BY
                intro.jmoa_code,
                intro.send_bv_name,
                intro_basic.basic_bonus_amount,
                intro_active.jwoa_code,
                intro_prev.prev_month_bv
            ORDER BY intro.jmoa_code
        """

        params = [
            base_params[0],
            base_params[1],
            base_params[2],
            *introducer_codes,
        ]
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            logger.info("マッチング詳細 直紹介者サマリー SELECT SQLを実行します。")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetch_direct_referral_rows(self, base_params, introducer_codes, focus_member_codes):
        introducer_codes = sorted({code for code in introducer_codes if code})
        focus_member_codes = sorted({code for code in focus_member_codes if code})
        if not introducer_codes:
            return []

        introducer_placeholders = ", ".join(["%s"] * len(introducer_codes))
        focus_case_sql = "0"
        focus_params = []
        if focus_member_codes:
            focus_placeholders = ", ".join(["%s"] * len(focus_member_codes))
            focus_case_sql = f"CASE WHEN child.jmoa_code IN ({focus_placeholders}) THEN 1 ELSE 0 END"
            focus_params = focus_member_codes

        sql = f"""
            WITH
            prev_purchase AS (
                SELECT
                    p.jwoa_code,
                    SUM(IFNULL(p.bv, 0)) AS prev_month_bv
                FROM bonus_db.purchase_info_list p
                WHERE p.bonus_payment_date >= %s
                  AND p.bonus_payment_date <  %s
                GROUP BY p.jwoa_code
            ),
            active_members AS (
                SELECT jwoa_code
                FROM bonus_db.active_users
                WHERE active_status = 1
                UNION
                SELECT jwoa_code
                FROM prev_purchase
                WHERE prev_month_bv >= 50
            ),
            basic_bonus_member AS (
                SELECT
                    placement_code AS member_code,
                    SUM(CASE WHEN bonus_amount > 0 THEN bonus_amount ELSE 0 END) AS basic_bonus_amount
                FROM bonus_db.B_basic_bonus_result
                WHERE kibetu = %s
                GROUP BY placement_code
            )
            SELECT
                child.introducer_code,
                intro.send_bv_name AS introducer_name,
                child.jmoa_code AS member_code,
                child.send_bv_name AS member_name,
                IFNULL(basic.basic_bonus_amount, 0) AS basic_bonus_amount,
                CASE WHEN IFNULL(basic.basic_bonus_amount, 0) > 0 THEN 1 ELSE 0 END AS basic_acquired_flg,
                CASE WHEN active_members.jwoa_code IS NOT NULL THEN 1 ELSE 0 END AS active_flg,
                IFNULL(prev_purchase.prev_month_bv, 0) AS prev_month_bv,
                {focus_case_sql} AS is_focus_member
            FROM bonus_db.users AS child
            LEFT JOIN bonus_db.users AS intro
                ON child.introducer_code = intro.jmoa_code
            LEFT JOIN basic_bonus_member AS basic
                ON child.jmoa_code = basic.member_code
            LEFT JOIN prev_purchase
                ON child.jmoa_code = prev_purchase.jwoa_code
            LEFT JOIN active_members
                ON child.jmoa_code = active_members.jwoa_code
            WHERE child.introducer_code IN ({introducer_placeholders})
            ORDER BY
                child.introducer_code,
                is_focus_member DESC,
                basic_acquired_flg DESC,
                active_flg DESC,
                child.jmoa_code
            LIMIT 2000
        """

        params = [
            base_params[0],
            base_params[1],
            base_params[2],
            *focus_params,
            *introducer_codes,
        ]
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            logger.info("マッチング詳細 直下会員一覧 SELECT SQLを実行します。")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        selected_kibetu = (self.request.GET.get("kibetu") or "").strip()
        per_page = self._get_per_page()

        filters = {
            "q_member_code": (self.request.GET.get("q_member_code") or "").strip(),
            "q_member_name": (self.request.GET.get("q_member_name") or "").strip(),
            "q_introducer_code": (self.request.GET.get("q_introducer_code") or "").strip(),
            "q_introducer_name": (self.request.GET.get("q_introducer_name") or "").strip(),
            "payable_result": (self.request.GET.get("payable_result") or "").strip(),
            "status_reason": (self.request.GET.get("status_reason") or "").strip(),
        }
        ctx.update(filters)
        ctx.update({
            "object_list": self._get_period_choices(),
            "selected_kibetu": selected_kibetu,
            "selected_period": None,
            "rows": [],
            "introducer_summary_rows": [],
            "direct_referral_rows": [],
            "direct_referral_count": 0,
            "total_count": 0,
            "per_page": per_page,
            "current_page": 1,
            "total_pages": 1,
            "pagination_pages": [],
            "display_from": 0,
            "display_to": 0,
            "period_error": "",
            "status_reason_choices": [
                "支払対象",
                "ベーシック未取得",
                "直紹介者なし",
                "直紹介者ベーシック未取得",
                "配置ツリー上の対象外",
                "段数上限超過",
            ],
        })

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            ctx["period_error"] = "選択された期別が存在しません。"
            return ctx

        ctx["selected_period"] = period
        base_params = self._build_period_params(selected_kibetu, period)
        total_count = self._count_rows(base_params, filters)
        total_pages = max(1, math.ceil(total_count / per_page))
        current_page = self._get_page(total_pages)
        offset = (current_page - 1) * per_page
        rows = self._fetch_rows(base_params, filters, per_page, offset) if total_count else []
        introducer_codes = [row.get("introducer_code") for row in rows]
        introducer_summary_rows = self._fetch_introducer_summary_rows(
            base_params,
            introducer_codes,
        ) if rows else []
        direct_referral_rows = self._fetch_direct_referral_rows(
            base_params,
            introducer_codes,
            [row.get("member_code") for row in rows],
        ) if rows else []

        query_params = {
            "kibetu": selected_kibetu,
            **filters,
            "per_page": per_page,
        }

        ctx.update({
            "rows": rows,
            "introducer_summary_rows": introducer_summary_rows,
            "direct_referral_rows": direct_referral_rows,
            "direct_referral_count": len(direct_referral_rows),
            "total_count": total_count,
            "page": current_page,
            "current_page": current_page,
            "total_pages": total_pages,
            "pagination_pages": self._pagination_pages(current_page, total_pages),
            "base_qs": self._build_base_qs(query_params),
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": max(1, current_page - 1),
            "next_page": min(total_pages, current_page + 1),
            "display_from": offset + 1 if rows else 0,
            "display_to": offset + len(rows) if rows else 0,
        })
        return ctx


class MatchingBonusTreeView(generic.TemplateView):
    template_name = "matching_bonus_tree.html"

    def _get_period_choices(self):
        return PeriodMaster.objects.using("rds").all().order_by("-kibetu")

    @staticmethod
    def _build_base_qs(params):
        return urlencode({
            key: value
            for key, value in params.items()
            if value not in ("", None)
        })

    @staticmethod
    def _collect_tree_codes(tree_context):
        codes = []

        def add_code(code):
            code = (code or "").strip()
            if code and code not in codes:
                codes.append(code)

        def walk(nodes):
            for node in nodes or []:
                add_code(node.get("jwoa_code"))
                walk(node.get("children") or [])

        for node in tree_context.get("tree_ancestors") or []:
            add_code(node.get("jwoa_code"))
        focus = tree_context.get("tree_focus")
        if focus:
            add_code(focus.get("jwoa_code"))
        walk(tree_context.get("tree_children") or [])
        return codes

    @staticmethod
    def _collect_path_codes(rows):
        codes = []
        for row in rows or []:
            code = (row.get("jwoa_code") or "").strip()
            if code and code not in codes:
                codes.append(code)
        return codes

    def _build_prev_month_range(self, selected_kibetu):
        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])
        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)
        return (
            make_aware(datetime(prev_month_last.year, prev_month_last.month, 1, 0, 0, 0)),
            make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0)),
        )

    def _fetch_tree_badge_map(self, selected_kibetu, member_codes):
        member_codes = [code for code in member_codes if code]
        if not selected_kibetu or not member_codes:
            return {}

        placeholders = ", ".join(["%s"] * len(member_codes))
        prev_month_start_dt, prev_month_end_dt = self._build_prev_month_range(selected_kibetu)
        prev_active_label = f"{prev_month_start_dt.year}/{prev_month_start_dt.month}"

        badge_map = {
            code: {
                "basic_bonus_amount": 0,
                "basic_acquired_flg": False,
                "prev_month_bv": 0,
                "prev_active_flg": False,
                "prev_active_label": prev_active_label,
                "show_tree_bonus_badges": True,
            }
            for code in member_codes
        }

        basic_sql = f"""
            SELECT
                placement_code,
                SUM(CASE WHEN bonus_amount > 0 THEN bonus_amount ELSE 0 END) AS basic_bonus_amount
            FROM bonus_db.B_basic_bonus_result
            WHERE kibetu = %s
              AND placement_code IN ({placeholders})
            GROUP BY placement_code
        """
        prev_purchase_sql = f"""
            SELECT
                jwoa_code,
                SUM(IFNULL(bv, 0)) AS prev_month_bv
            FROM bonus_db.purchase_info_list
            WHERE bonus_payment_date >= %s
              AND bonus_payment_date <  %s
              AND jwoa_code IN ({placeholders})
            GROUP BY jwoa_code
        """
        active_sql = f"""
            SELECT jwoa_code
            FROM bonus_db.active_users
            WHERE active_status = 1
              AND jwoa_code IN ({placeholders})
        """

        with connections["rds"].cursor() as cursor:
            logger.info("マッチングTree ベーシック取得バッジSQLを実行します。")
            cursor.execute(basic_sql, [selected_kibetu, *member_codes])
            for code, amount in cursor.fetchall():
                if code in badge_map:
                    amount = amount or 0
                    badge_map[code]["basic_bonus_amount"] = amount
                    badge_map[code]["basic_acquired_flg"] = amount > 0

            logger.info("マッチングTree 前月購入BVバッジSQLを実行します。")
            cursor.execute(prev_purchase_sql, [prev_month_start_dt, prev_month_end_dt, *member_codes])
            for code, prev_month_bv in cursor.fetchall():
                if code in badge_map:
                    prev_month_bv = prev_month_bv or 0
                    badge_map[code]["prev_month_bv"] = prev_month_bv
                    if prev_month_bv >= 50:
                        badge_map[code]["prev_active_flg"] = True

            logger.info("マッチングTree active_usersバッジSQLを実行します。")
            cursor.execute(active_sql, member_codes)
            for row in cursor.fetchall():
                code = row[0]
                if code in badge_map:
                    badge_map[code]["prev_active_flg"] = True

        return badge_map

    @staticmethod
    def _apply_tree_badges(tree_context, badge_map):
        def apply(node):
            if not node:
                return
            code = node.get("jwoa_code")
            if code in badge_map:
                node.update(badge_map[code])
            for child in node.get("children") or []:
                apply(child)

        for node in tree_context.get("tree_ancestors") or []:
            apply(node)
        apply(tree_context.get("tree_focus"))
        for node in tree_context.get("tree_children") or []:
            apply(node)

    @staticmethod
    def _apply_path_badges(rows, badge_map):
        for row in rows or []:
            code = row.get("jwoa_code")
            if code in badge_map:
                row.update(badge_map[code])

    def _fetch_direct_referral_codes(self, member_code):
        member_code = (member_code or "").strip()
        if not member_code:
            return set()

        sql = """
            SELECT jmoa_code
            FROM bonus_db.users
            WHERE introducer_code = %s
        """
        with connections["rds"].cursor() as cursor:
            logger.info("マッチングTree 直紹介会員コード取得SQLを実行します。")
            cursor.execute(sql, [member_code])
            return {
                (row[0] or "").strip()
                for row in cursor.fetchall()
                if (row[0] or "").strip()
            }

    @staticmethod
    def _apply_direct_introducer_badge(tree_context, direct_referral_codes):
        if not direct_referral_codes:
            return

        def apply(node):
            if not node:
                return
            node["is_direct_introducer"] = node.get("jwoa_code") in direct_referral_codes
            for child in node.get("children") or []:
                apply(child)

        for node in tree_context.get("tree_ancestors") or []:
            apply(node)
        apply(tree_context.get("tree_focus"))
        for node in tree_context.get("tree_children") or []:
            apply(node)

    @staticmethod
    def _apply_direct_introducer_path_badge(rows, direct_referral_codes):
        if not direct_referral_codes:
            return
        for row in rows or []:
            row["is_direct_introducer"] = row.get("jwoa_code") in direct_referral_codes

    @staticmethod
    def _empty_tree_context(unavailable_reason):
        return {
            "tree_ancestors": [],
            "tree_focus": None,
            "tree_children": [],
            "tree_truncated": False,
            "tree_unavailable_reason": unavailable_reason,
            "tree_node_count": 0,
            "tree_search_path_rows": [],
            "tree_search_target": None,
            "tree_search_not_found": False,
        }

    def _build_matching_tree_context(
        self,
        q_member_code,
        tree_search,
        active_tree_type,
        direct_referral_codes,
    ):
        placement_tree = build_member_tree_view(q_member_code)
        introducer_tree = build_introducer_tree_view(q_member_code)

        for tree_context in (placement_tree, introducer_tree):
            tree_context.setdefault("tree_search_path_rows", [])
            tree_context.setdefault("tree_search_target", None)
            tree_context.setdefault("tree_search_not_found", False)
            self._apply_direct_introducer_badge(tree_context, direct_referral_codes)

        active_tree_context = (
            introducer_tree
            if active_tree_type == "introducer"
            else placement_tree
        )
        if tree_search:
            if active_tree_type == "introducer":
                tree_search_path_rows = fetch_introducer_tree_search_path(q_member_code, tree_search)
            else:
                tree_search_path_rows = fetch_tree_search_path(q_member_code, tree_search)

            active_tree_context["tree_search_path_rows"] = tree_search_path_rows
            active_tree_context["tree_search_target"] = (
                next((row for row in tree_search_path_rows if row.get("is_target")), None)
                if tree_search_path_rows
                else None
            )
            active_tree_context["tree_search_not_found"] = not tree_search_path_rows
            self._apply_direct_introducer_path_badge(
                active_tree_context.get("tree_search_path_rows") or [],
                direct_referral_codes,
            )

        return placement_tree, introducer_tree

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        selected_kibetu = (self.request.GET.get("kibetu") or "").strip()
        q_member_code = (self.request.GET.get("q_member_code") or "").strip()
        tree_search = (self.request.GET.get("tree_search") or "").strip()
        active_tree_type = (self.request.GET.get("tree_type") or "placement").strip()
        if active_tree_type not in ("placement", "introducer"):
            active_tree_type = "placement"

        ctx.update({
            "object_list": self._get_period_choices(),
            "selected_kibetu": selected_kibetu,
            "selected_period": None,
            "q_member_code": q_member_code,
            "tree_search": tree_search,
            "placement_tree_search": tree_search if active_tree_type == "placement" else "",
            "introducer_tree_search": tree_search if active_tree_type == "introducer" else "",
            "active_tree_type": active_tree_type,
            "period_error": "",
            "placement_tree": self._empty_tree_context("会員コードを入力して「表示」を押してください。"),
            "introducer_tree": self._empty_tree_context("会員コードを入力して「表示」を押してください。"),
            "show_tree_bonus_badges": False,
            "direct_referral_codes": set(),
        })

        if selected_kibetu:
            period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
            if period:
                ctx["selected_period"] = period
            else:
                ctx["period_error"] = "選択された期別が存在しません。"

        if q_member_code:
            direct_referral_codes = self._fetch_direct_referral_codes(q_member_code)
            ctx["direct_referral_codes"] = direct_referral_codes
            placement_tree, introducer_tree = self._build_matching_tree_context(
                q_member_code,
                tree_search,
                active_tree_type,
                direct_referral_codes,
            )
            ctx["placement_tree"] = placement_tree
            ctx["introducer_tree"] = introducer_tree

            if selected_kibetu and ctx.get("selected_period") and not ctx.get("period_error"):
                member_codes = self._collect_tree_codes(placement_tree)
                member_codes.extend(self._collect_tree_codes(introducer_tree))
                member_codes.extend(self._collect_path_codes(
                    placement_tree.get("tree_search_path_rows") or []
                ))
                member_codes.extend(self._collect_path_codes(
                    introducer_tree.get("tree_search_path_rows") or []
                ))
                badge_map = self._fetch_tree_badge_map(selected_kibetu, member_codes)
                self._apply_tree_badges(placement_tree, badge_map)
                self._apply_tree_badges(introducer_tree, badge_map)
                self._apply_path_badges(
                    placement_tree.get("tree_search_path_rows") or [],
                    badge_map,
                )
                self._apply_path_badges(
                    introducer_tree.get("tree_search_path_rows") or [],
                    badge_map,
                )
                ctx["show_tree_bonus_badges"] = True

        ctx["base_qs"] = self._build_base_qs({
            "kibetu": selected_kibetu,
            "q_member_code": q_member_code,
            "tree_search": tree_search,
            "tree_type": active_tree_type,
        })
        ctx["placement_tab_qs"] = self._build_base_qs({
            "kibetu": selected_kibetu,
            "q_member_code": q_member_code,
            "tree_search": tree_search if active_tree_type == "placement" else "",
            "tree_type": "placement",
        })
        ctx["introducer_tab_qs"] = self._build_base_qs({
            "kibetu": selected_kibetu,
            "q_member_code": q_member_code,
            "tree_search": tree_search if active_tree_type == "introducer" else "",
            "tree_type": "introducer",
        })
        return ctx
