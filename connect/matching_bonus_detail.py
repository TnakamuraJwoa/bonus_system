import logging
from datetime import datetime, timedelta
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


logger = logging.getLogger(__name__)


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
                "prev_month_repurchase_flg": False,
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
                        badge_map[code]["prev_month_repurchase_flg"] = True

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
        active_tree_type = (self.request.GET.get("tree_type") or "introducer").strip()
        if active_tree_type not in ("placement", "introducer"):
            active_tree_type = "introducer"

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
