import logging
import math
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.db import connections
from django.utils.timezone import make_aware
from django.views import generic

from connect.models import PeriodMaster
from connect.sql.basic_income_line_detail_sql import BASIC_INCOME_LINE_DETAIL_CTE_SQL


logger = logging.getLogger(__name__)


class BasicIncomeLineDetailView(generic.TemplateView):
    template_name = "basic_income_line_detail.html"
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
        st_date = period.st_date
        end_date = period.end_date

        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])

        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_dt = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)
        prev_year = prev_month_last.year
        prev_month = prev_month_last.month

        prev_month_start_dt = make_aware(datetime(prev_year, prev_month, 1, 0, 0, 0))
        prev_month_end_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))

        return [
            selected_kibetu,
            prev_year,
            prev_month,
            prev_month_start_dt,
            prev_month_end_dt,
            start_dt,
            end_dt,
            start_dt,
            end_dt,
        ]

    @staticmethod
    def _build_where(filters):
        where = ["1 = 1"]
        params = []

        if filters["q_placement_code"]:
            where.append("placement_code LIKE %s")
            params.append(f"%{filters['q_placement_code']}%")
        if filters["q_line_code"]:
            where.append("line_code LIKE %s")
            params.append(f"%{filters['q_line_code']}%")
        if filters["q_purchaser_code"]:
            where.append("purchaser_code LIKE %s")
            params.append(f"%{filters['q_purchaser_code']}%")
        if filters["q_purchaser_name"]:
            where.append("purchaser_name LIKE %s")
            params.append(f"%{filters['q_purchaser_name']}%")
        if filters["detail_type"] in ("purchase", "carry_over"):
            where.append("detail_type = %s")
            params.append(filters["detail_type"])
        if filters["line_role"] == "basic":
            where.append("line_rank = 1")
        elif filters["line_role"] == "income":
            where.append("line_rank BETWEEN 2 AND 5")

        return "WHERE " + " AND ".join(where), params

    def _count_rows(self, base_params, filters):
        where_sql, filter_params = self._build_where(filters)
        sql = f"""
            {BASIC_INCOME_LINE_DETAIL_CTE_SQL}
            SELECT COUNT(*) AS cnt
            FROM income_line_detail
            {where_sql}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, base_params + filter_params)
            logger.info("収入ライン購入者詳細 COUNT SQLを実行します。")
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def _fetch_rows(self, base_params, filters, limit, offset):
        where_sql, filter_params = self._build_where(filters)
        sql = f"""
            {BASIC_INCOME_LINE_DETAIL_CTE_SQL}
            SELECT
                kibetu,
                placement_code,
                placement_name,
                placement_rank,
                line_code,
                purchaser_code,
                purchaser_name,
                path_codes,
                purchase_bv,
                carry_over_bv,
                calc_bv,
                line_rank,
                line_role_label,
                line_total_bv,
                income_line_bv,
                basic_line_bv,
                next_carry_over_bv,
                detail_type,
                detail_type_label
            FROM income_line_detail
            {where_sql}
            ORDER BY
                placement_code,
                line_total_bv DESC,
                line_code,
                detail_sort,
                purchaser_code
            LIMIT %s OFFSET %s
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, base_params + filter_params + [limit, offset])
            logger.info("収入ライン購入者詳細 SELECT SQLを実行します。")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetch_tree_rows(self, base_params, filters):
        where_sql, filter_params = self._build_where(filters)
        sql = f"""
            {BASIC_INCOME_LINE_DETAIL_CTE_SQL}
            SELECT
                kibetu,
                placement_code,
                placement_name,
                placement_rank,
                line_code,
                purchaser_code,
                purchaser_name,
                path_codes,
                purchase_bv,
                carry_over_bv,
                calc_bv,
                line_rank,
                line_role_label,
                line_total_bv,
                income_line_bv,
                basic_line_bv,
                next_carry_over_bv,
                detail_type,
                detail_type_label
            FROM income_line_detail
            {where_sql}
            ORDER BY
                placement_code,
                line_rank,
                line_total_bv DESC,
                line_code,
                detail_sort,
                purchaser_code
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, base_params + filter_params)
            logger.info("収入ライン購入者詳細 Tree SELECT SQLを実行します。")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetch_member_purchase_map(self, base_params, rows):
        codes = set()
        for row in rows:
            placement_code = (row.get("placement_code") or "").strip()
            if placement_code:
                codes.add(placement_code)
            line_code = (row.get("line_code") or "").strip()
            if line_code:
                codes.add(line_code)
            for code in (row.get("path_codes") or "").split(">"):
                code = code.strip()
                if code:
                    codes.add(code)

        if not codes:
            return {}

        placeholders = ", ".join(["%s"] * len(codes))
        sql = f"""
            WITH purchase_list_union AS (
                SELECT
                    p.jwoa_code,
                    LEAST(IFNULL(p.bv, 0), 50) AS custom_bv
                FROM bonus_db.purchase_info_list AS p
                WHERE p.order_type IN (101, 105)
                  AND p.bonus_payment_date >= %s
                  AND p.bonus_payment_date < %s

                UNION ALL

                SELECT
                    p.jwoa_code,
                    IFNULL(p.bv, 0) AS custom_bv
                FROM bonus_db.purchase_info_list AS p
                WHERE p.order_type IN (102, 103)
                  AND p.bonus_payment_date >= %s
                  AND p.bonus_payment_date < %s
            ),
            purchase_sum AS (
                SELECT
                    jwoa_code,
                    SUM(custom_bv) AS purchase_bv
                FROM purchase_list_union
                WHERE custom_bv > 0
                GROUP BY jwoa_code
            )
            SELECT
                u.jmoa_code,
                u.send_bv_name,
                IFNULL(ps.purchase_bv, 0) AS purchase_bv,
                utr.new_rank,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM bonus_db.active_users au
                        WHERE au.jwoa_code = u.jmoa_code
                          AND au.year = %s
                          AND au.month = %s
                          AND au.active_status = 1
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM bonus_db.purchase_info_list p
                        WHERE p.jwoa_code = u.jmoa_code
                          AND p.register_year = %s
                          AND p.register_month = %s
                          AND IFNULL(p.bv, 0) >= 50
                    )
                    THEN 1
                    ELSE 0
                END AS is_prev_month_active
            FROM bonus_db.users AS u
            LEFT JOIN purchase_sum AS ps
              ON ps.jwoa_code = u.jmoa_code
            LEFT JOIN bonus_db.users_target_rank AS utr
              ON utr.jmoa_code = u.jmoa_code
            WHERE u.jmoa_code IN ({placeholders})
        """
        period_params = base_params[5:9]
        prev_month_params = base_params[1:3] + base_params[1:3]
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, period_params + prev_month_params + list(codes))
            logger.info("収入ラインTree会員購入状況 SELECT SQLを実行します。")
            return {
                row[0]: {
                    "code": row[0],
                    "name": row[1] or "",
                    "purchase_bv": row[2] or 0,
                    "has_purchase": (row[2] or 0) > 0,
                    "new_rank": row[3],
                    "is_prev_month_active": bool(row[4]),
                }
                for row in cursor.fetchall()
            }

    @staticmethod
    def _build_purchase_path_nodes(row, member_purchase_map):
        path_codes = [
            code.strip()
            for code in (row.get("path_codes") or "").split(">")
            if code.strip()
        ]
        path_codes = list(reversed(path_codes))
        nodes = []
        for depth, code in enumerate(path_codes):
            member = member_purchase_map.get(code, {"code": code, "name": "", "purchase_bv": 0, "has_purchase": False})
            nodes.append({
                **member,
                "depth": depth,
                "indent_px": depth * 22,
                "is_line_root": depth == 0,
                "is_purchaser": code == (row.get("purchaser_code") or ""),
            })
        return nodes

    @staticmethod
    def _build_tree_groups(rows, member_purchase_map=None):
        member_purchase_map = member_purchase_map or {}
        placement_map = {}

        for row in rows:
            placement_code = row.get("placement_code") or ""
            line_code = row.get("line_code") or ""

            placement = placement_map.setdefault(
                placement_code,
                {
                    "placement_code": placement_code,
                    "placement_name": row.get("placement_name") or "",
                    "placement_rank": row.get("placement_rank") or 0,
                    "placement_member": member_purchase_map.get(
                        placement_code,
                        {
                            "code": placement_code,
                            "name": row.get("placement_name") or "",
                            "purchase_bv": 0,
                            "has_purchase": False,
                            "new_rank": None,
                            "is_prev_month_active": False,
                        },
                    ),
                    "income_line_bv": row.get("income_line_bv") or 0,
                    "basic_line_bv": row.get("basic_line_bv") or 0,
                    "next_carry_over_bv": row.get("next_carry_over_bv") or 0,
                    "lines": {},
                },
            )
            line = placement["lines"].setdefault(
                line_code,
                {
                    "line_code": line_code,
                    "line_member": member_purchase_map.get(
                        line_code,
                        {
                            "code": line_code,
                            "name": "",
                            "purchase_bv": 0,
                            "has_purchase": False,
                            "new_rank": None,
                            "is_prev_month_active": False,
                        },
                    ),
                    "line_rank": row.get("line_rank") or 0,
                    "line_role_label": row.get("line_role_label") or "収入ライン",
                    "line_total_bv": row.get("line_total_bv") or 0,
                    "carry_over_rows": [],
                    "purchase_rows": [],
                },
            )

            if row.get("detail_type") == "carry_over":
                line["carry_over_rows"].append(row)
            else:
                row["path_nodes"] = BasicIncomeLineDetailView._build_purchase_path_nodes(
                    row,
                    member_purchase_map,
                )
                row["intermediate_count"] = sum(
                    1
                    for node in row["path_nodes"]
                    if not node.get("is_line_root") and not node.get("is_purchaser")
                )
                line["purchase_rows"].append(row)

        tree_groups = []
        for placement in placement_map.values():
            placement["lines"] = sorted(
                placement["lines"].values(),
                key=lambda item: (item.get("line_rank") or 0, item.get("line_code") or ""),
            )
            tree_groups.append(placement)

        return sorted(tree_groups, key=lambda item: item.get("placement_code") or "")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        selected_kibetu = (self.request.GET.get("kibetu") or "").strip()
        filters = {
            "q_placement_code": (self.request.GET.get("q_placement_code") or "").strip(),
            "q_line_code": (self.request.GET.get("q_line_code") or "").strip(),
            "q_purchaser_code": (self.request.GET.get("q_purchaser_code") or "").strip(),
            "q_purchaser_name": (self.request.GET.get("q_purchaser_name") or "").strip(),
            "detail_type": (self.request.GET.get("detail_type") or "").strip(),
            "line_role": (self.request.GET.get("line_role") or "").strip(),
        }
        view_mode = "tree" if self.request.GET.get("view_mode") == "tree" else "list"
        per_page = self._get_per_page()

        ctx.update(filters)
        ctx.update({
            "object_list": self._get_period_choices(),
            "selected_kibetu": selected_kibetu,
            "selected_period": None,
            "view_mode": view_mode,
            "return_qs": (self.request.GET.get("return_qs") or "").strip(),
            "rows": [],
            "show_tree": False,
            "tree_groups": [],
            "total_count": 0,
            "display_from": 0,
            "display_to": 0,
            "per_page": per_page,
            "page": 1,
            "total_pages": 1,
            "has_prev": False,
            "has_next": False,
            "prev_page": 1,
            "next_page": 1,
            "pagination_pages": [],
            "base_qs": "",
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
        page = self._get_page(total_pages)
        offset = (page - 1) * per_page
        rows = self._fetch_rows(base_params, filters, per_page, offset) if total_count else []
        show_tree = view_mode == "tree" and bool(filters["q_placement_code"] and total_count)
        tree_rows = self._fetch_tree_rows(base_params, filters) if show_tree else []
        member_purchase_map = self._fetch_member_purchase_map(base_params, tree_rows) if tree_rows else {}

        base_qs_params = {
            "kibetu": selected_kibetu,
            "q_placement_code": filters["q_placement_code"],
            "q_line_code": filters["q_line_code"],
            "q_purchaser_code": filters["q_purchaser_code"],
            "q_purchaser_name": filters["q_purchaser_name"],
            "detail_type": filters["detail_type"],
            "line_role": filters["line_role"],
            "view_mode": view_mode,
        }
        if per_page != self.DEFAULT_PER_PAGE:
            base_qs_params["per_page"] = per_page

        ctx.update({
            "rows": rows,
            "show_tree": show_tree,
            "tree_groups": self._build_tree_groups(tree_rows, member_purchase_map) if tree_rows else [],
            "total_count": total_count,
            "display_from": (page - 1) * per_page + 1 if total_count else 0,
            "display_to": min(page * per_page, total_count) if total_count else 0,
            "per_page": per_page,
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
            "pagination_pages": self._pagination_pages(page, total_pages),
            "base_qs": self._build_base_qs(base_qs_params),
        })
        return ctx
