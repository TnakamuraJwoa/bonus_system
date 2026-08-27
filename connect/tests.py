from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from connect.legacy_orders import LegacyOrdersView
from connect.templatetags.custom_filters import as_db_datetime, db_datetime, jp_date, jst_datetime
from connect.views import (
    BonusPaymentDateView,
    ensure_user_target_rank_for_kibetu,
    register_users_target_rank,
    OrdersDistributionBvExportView,
    OrdersDistributionBvView,
    S_MonthBonusView,
    S_WeekBonusView,
    UsersView,
    WeekBonusView,
)


@override_settings(TIME_ZONE="Asia/Tokyo", USE_TZ=True)
class JstDatetimeFilterTests(SimpleTestCase):
    def test_naive_datetime_is_treated_as_utc(self):
        result = jst_datetime(datetime(2026, 1, 15, 0, 30))

        self.assertEqual(result.utcoffset().total_seconds(), 9 * 60 * 60)
        self.assertEqual(result.replace(tzinfo=None), datetime(2026, 1, 15, 9, 30))

    def test_aware_datetime_is_converted_without_double_conversion(self):
        result = jst_datetime(datetime(2026, 1, 15, 0, 30, tzinfo=timezone.utc))

        self.assertEqual(result.replace(tzinfo=None), datetime(2026, 1, 15, 9, 30))

    def test_date_is_unchanged(self):
        value = date(2026, 1, 15)

        self.assertIs(jst_datetime(value), value)

    def test_empty_values_are_unchanged(self):
        self.assertIsNone(jst_datetime(None))
        self.assertEqual(jst_datetime(""), "")

    def test_jp_date_converts_before_extracting_date(self):
        value = datetime(2026, 1, 15, 16, 0, tzinfo=timezone.utc)

        self.assertEqual(jp_date(value), "2026年1月16日")


@override_settings(TIME_ZONE="Asia/Tokyo", USE_TZ=True)
class DbDatetimeFilterTests(SimpleTestCase):
    def test_naive_datetime_keeps_db_wall_clock(self):
        result = db_datetime(datetime(2026, 1, 15, 0, 30))

        self.assertEqual(result, "2026/01/15 00:30:00")

    def test_aware_utc_datetime_does_not_add_jst_offset(self):
        result = db_datetime(datetime(2026, 1, 15, 0, 30, tzinfo=timezone.utc))

        self.assertEqual(result, "2026/01/15 00:30:00")

    def test_date_has_no_time(self):
        self.assertEqual(db_datetime(date(2026, 7, 24)), "2026/07/24")

    def test_empty_values_are_unchanged(self):
        self.assertIsNone(db_datetime(None))
        self.assertEqual(db_datetime(""), "")

    def test_as_db_datetime_strips_timezone_without_conversion(self):
        value = datetime(2026, 1, 15, 0, 30, tzinfo=timezone.utc)

        result = as_db_datetime(value)

        self.assertEqual(result, datetime(2026, 1, 15, 0, 30))
        self.assertIsNone(result.tzinfo)


class WeekBonusAllPeriodsSearchTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _build_view(self, query):
        view = S_WeekBonusView()
        view.request = self.factory.get("/s_week_bonus/", query)
        view.object_list = []
        return view

    def test_all_periods_requires_member_filter(self):
        view = self._build_view({"kibetu": S_WeekBonusView.ALL_KIBETU_VALUE})

        context = view.get_context_data()

        self.assertTrue(context["all_kibetu_requires_member_filter"])
        self.assertEqual(context["rows"], [])

    def test_member_code_search_does_not_limit_kibetu(self):
        view = self._build_view(
            {
                "kibetu": S_WeekBonusView.ALL_KIBETU_VALUE,
                "jwoa_code": "JP001",
            }
        )
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = []
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            view.get_context_data()

        sql, params = cursor.execute.call_args.args
        self.assertNotIn("AND kibetu = %s", sql)
        self.assertIn("AND jwoa_code LIKE %s", sql)
        self.assertEqual(params, ["%JP001%"])


class MonthBonusAllPeriodsSearchTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _build_view(self, query):
        view = S_MonthBonusView()
        view.request = self.factory.get("/s_month_bonus/", query)
        view.object_list = []
        return view

    def test_all_periods_requires_member_filter(self):
        view = self._build_view({"kibetu": S_MonthBonusView.ALL_KIBETU_VALUE})

        context = view.get_context_data()

        self.assertTrue(context["all_kibetu_requires_member_filter"])
        self.assertEqual(context["rows"], [])

    def test_member_name_search_does_not_limit_kibetu(self):
        view = self._build_view(
            {
                "kibetu": S_MonthBonusView.ALL_KIBETU_VALUE,
                "jwoa_name": "山田",
            }
        )
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = []
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            view.get_context_data()

        sql, params = cursor.execute.call_args.args
        self.assertNotIn("AND kibetu = %s", sql)
        self.assertIn("AND jwoa_name LIKE %s", sql)
        self.assertEqual(params, ["%山田%"])


class UsersViewQueryTests(SimpleTestCase):
    def setUp(self):
        self.view = UsersView()
        self.view.request = RequestFactory().get("/users/")

    def test_member_ids_use_prefix_match(self):
        where_sql, params = self.view._build_where(
            q_jpid="JP0419",
            q_introducer="JP1",
            q_placement="JP2",
        )

        self.assertIn("u.jmoa_code LIKE %s", where_sql)
        self.assertEqual(params, ["JP0419%", "JP1%", "JP2%"])

    def test_list_sql_skips_purchase_join_when_only_displaying_active(self):
        sql, params = self.view._build_rows_sql(
            active_year=2026,
            active_month=8,
            active_start_date=date(2026, 8, 1),
            active_end_date=date(2026, 9, 1),
            order_sql="u.created_at DESC",
        )

        self.assertNotIn("purchase_info_list", sql)
        self.assertEqual(params, [])

    def test_list_sql_joins_purchase_when_filtering_active(self):
        sql, params = self.view._build_rows_sql(
            active_year=2026,
            active_month=8,
            active_start_date=date(2026, 8, 1),
            active_end_date=date(2026, 9, 1),
            q_active_result="active",
            order_sql="u.created_at DESC",
        )

        self.assertIn("purchase_info_list", sql)
        self.assertEqual(
            params,
            [2026, 8, date(2026, 8, 1), date(2026, 9, 1)],
        )

    def test_count_uses_simple_count_without_active_filter(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (10,)
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            self.view._fetch_total_count(q_jpid="JP0419")

        sql, params = cursor.execute.call_args.args
        self.assertIn("COUNT(*)", sql)
        self.assertNotIn("purchase_info_list", sql)
        self.assertEqual(params, ["JP0419%"])


class OrdersDistributionBvViewQueryTests(SimpleTestCase):
    def setUp(self):
        self.view = OrdersDistributionBvView()
        self.view.request = RequestFactory().get("/orders_distribution_bv/")

    def test_created_at_sort_uses_id(self):
        order_by = self.view._build_order_by(self.view._get_sort_context())

        self.assertEqual(order_by, "a.id DESC")

    def test_indexed_sort_keeps_id_in_the_same_direction(self):
        self.view.request = RequestFactory().get(
            "/orders_distribution_bv/",
            {"sort": "jwoa_code", "direction": "desc"},
        )

        order_by = self.view._build_order_by(self.view._get_sort_context())

        self.assertEqual(order_by, "a.jwoa_code DESC, a.id DESC")

    def test_order_code_mf_uses_prefix_match(self):
        _where_sql, params = self.view._build_where(q_order_code="MF30")

        self.assertEqual(params, ["MF30%"])

    def test_order_code_without_mf_uses_infix_match(self):
        _where_sql, params = self.view._build_where(q_order_code="1234")

        self.assertEqual(params, ["%1234%"])

    def test_member_id_jp_uses_prefix_match(self):
        _where_sql, params = self.view._build_where(q_jwoa_code="JP0512")

        self.assertEqual(params, ["JP0512%"])

    def test_count_skips_orders_join_without_purchaser_filters(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (10,)
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.cache") as mock_cache, patch(
            "connect.views.connections", {"rds": connection}
        ):
            mock_cache.get.return_value = None
            self.view._fetch_total_count(q_order_code="MF30")

        sql, params = cursor.execute.call_args.args
        self.assertIn("COUNT(*)", sql)
        self.assertNotIn("LEFT JOIN nexus_production.orders", sql)
        self.assertEqual(params, ["MF30%"])

    def test_count_joins_orders_when_filtering_purchaser(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (10,)
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.cache") as mock_cache, patch(
            "connect.views.connections", {"rds": connection}
        ):
            mock_cache.get.return_value = None
            self.view._fetch_total_count(q_purchaser_jwoa_code="JP05")

        sql, params = cursor.execute.call_args.args
        self.assertIn("LEFT JOIN nexus_production.orders", sql)
        self.assertIn("b.jwoa_code LIKE %s", sql)
        self.assertEqual(params, ["JP05%"])

    def test_list_sql_defers_orders_join_on_default_sort(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [
            ("id",),
            ("order_code",),
            ("user_id",),
            ("jwoa_code",),
            ("distribution_bv",),
            ("usage_fee",),
            ("created_at",),
            ("updated_at",),
        ]
        cursor.fetchall.side_effect = [
            [(1, "MF1", 10, "JP1", 100, 0, None, None)],
            [("MF1", "JP9", 1)],
        ]
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            rows = self.view._fetch_rows(limit=200, offset=0, order_sql="a.id DESC")

        list_sql, list_params = cursor.execute.call_args_list[0].args
        self.assertNotIn("LEFT JOIN nexus_production.orders", list_sql)
        self.assertIn("ORDER BY a.id DESC", list_sql)
        self.assertEqual(list_params, [200, 0])
        self.assertEqual(rows[0]["purchaser_jwoa_code"], "JP9")
        self.assertEqual(rows[0]["bv_actived_flg"], 1)

    def test_list_sql_joins_orders_when_sorting_by_purchaser(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [
            ("id",),
            ("order_code",),
            ("user_id",),
            ("jwoa_code",),
            ("distribution_bv",),
            ("usage_fee",),
            ("created_at",),
            ("updated_at",),
            ("purchaser_jwoa_code",),
            ("bv_actived_flg",),
        ]
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            self.view._fetch_rows(
                limit=200,
                offset=0,
                order_sql="b.jwoa_code DESC, a.id DESC",
                sort="purchaser_jwoa_code",
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("LEFT JOIN nexus_production.orders", sql)
        self.assertIn("b.jwoa_code AS purchaser_jwoa_code", sql)
        self.assertEqual(params, [200, 0])


class OrdersDistributionBvExportTests(SimpleTestCase):
    def setUp(self):
        self.view = OrdersDistributionBvExportView()
        self.view.request = RequestFactory().get(
            "/orders_distribution_bv/export/",
            {
                "q_order_code": " MF30 ",
                "q_bv_actived_flg": "1",
            },
        )

    def test_filters_match_list_search_conditions(self):
        filters = self.view._get_filters()

        self.assertEqual(filters["q_order_code"], "MF30")
        self.assertEqual(filters["q_bv_actived_flg"], "1")

    def test_export_query_uses_keyset_and_includes_display_columns(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            self.view._fetch_export_rows(
                last_id=500,
                limit=100,
                q_order_code="MF30",
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("LEFT JOIN nexus_production.orders", sql)
        self.assertIn("a.id < %s", sql)
        self.assertIn("ORDER BY a.id DESC", sql)
        self.assertEqual(params, ["MF30%", 500, 100])

    def test_excel_row_converts_flag_and_datetimes(self):
        created_at = datetime(2026, 8, 26, 10, 20, 30)
        updated_at = datetime(2026, 8, 26, 11, 20, 30)

        values = self.view._row_to_excel(
            (
                10,
                "MF30",
                "JP001",
                "JP002",
                120,
                10,
                1,
                created_at,
                updated_at,
            )
        )

        self.assertEqual(
            values,
            [
                "MF30",
                "JP001",
                "JP002",
                120,
                10,
                "反映済",
                created_at,
                updated_at,
            ],
        )


class BonusPaymentDateDeleteTests(SimpleTestCase):
    def setUp(self):
        self.view = BonusPaymentDateView()
        self.factory = RequestFactory()

    @staticmethod
    def _build_cursor(fetchone_results, rowcount=1):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = fetchone_results
        cursor.rowcount = rowcount
        connection = MagicMock()
        connection.cursor.return_value = cursor
        return cursor, connection

    @staticmethod
    def _executed(cursor, needle):
        return [
            call.args
            for call in cursor.execute.call_args_list
            if needle in call.args[0]
        ]

    def test_source_payment_date_uses_deposit_at(self):
        cursor, connection = self._build_cursor([(date(2026, 8, 25),)])

        with patch("connect.views.connections", {"rds": connection}):
            source_date = self.view._fetch_source_payment_date("MF1")

        self.assertEqual(source_date, date(2026, 8, 25))
        sql, params = cursor.execute.call_args.args
        self.assertIn("nexus_production.orders", sql)
        self.assertEqual(params, ["MF1"])

    def test_source_payment_date_falls_back_to_api_users_bv(self):
        cursor, connection = self._build_cursor([None, (date(2026, 7, 10),)])

        with patch("connect.views.connections", {"rds": connection}):
            source_date = self.view._fetch_source_payment_date("MF1")

        self.assertEqual(source_date, date(2026, 7, 10))
        self.assertEqual(len(self._executed(cursor, "nexus_production.api_users_bv")), 1)

    def test_source_payment_date_returns_none_when_no_source(self):
        cursor, connection = self._build_cursor([None, None])

        with patch("connect.views.connections", {"rds": connection}):
            source_date = self.view._fetch_source_payment_date("MF1")

        self.assertIsNone(source_date)

    def _post_delete(self, cursor, connection):
        request = self.factory.post(
            "/bonus_payment_date/",
            {"action": "delete", "order_code": "MF1", "q_order_code": ""},
        )

        with patch("connect.views.connections", {"rds": connection}), patch(
            "connect.views.transaction"
        ), patch("connect.views.messages") as mock_messages, patch(
            "connect.views.record_change_audit"
        ) as mock_audit, patch(
            "connect.views.fetch_one_dict",
            return_value={
                "order_code": "MF1",
                "bonus_payment_date": date(2026, 8, 30),
            },
        ):
            self.view.post(request)

        return mock_messages, mock_audit

    def test_delete_reverts_purchase_info_to_deposit_at(self):
        cursor, connection = self._build_cursor([(date(2026, 8, 25),)])

        mock_messages, mock_audit = self._post_delete(cursor, connection)

        self.assertEqual(len(self._executed(cursor, "DELETE FROM bonus_db.bonus_payment_date")), 1)
        revert_calls = self._executed(cursor, "UPDATE bonus_db.purchase_info_list")
        self.assertEqual(len(revert_calls), 1)
        self.assertEqual(revert_calls[0][1], [date(2026, 8, 25), 2026, 8, "MF1"])
        mock_messages.warning.assert_not_called()
        self.assertEqual(
            mock_audit.call_args.kwargs["after_values"],
            {
                "purchase_info_list.bonus_payment_date": date(2026, 8, 25),
                "reverted_count": 1,
            },
        )

    def test_delete_keeps_purchase_info_when_no_source_date(self):
        cursor, connection = self._build_cursor([None, None])

        mock_messages, _mock_audit = self._post_delete(cursor, connection)

        self.assertEqual(len(self._executed(cursor, "DELETE FROM bonus_db.bonus_payment_date")), 1)
        self.assertEqual(self._executed(cursor, "UPDATE bonus_db.purchase_info_list"), [])
        mock_messages.warning.assert_called_once()


class LegacyOrdersUpdateTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = LegacyOrdersView()

    def _request(self):
        request = self.factory.post(
            "/legacy_orders/",
            {
                "action": "update",
                "id": "123",
                "order_code": "ORD-UPDATED",
                "member_no": "JP9999999",
                "order_status": "20",
                "order_type": "30",
                "order_year": "2025",
                "order_month": "2",
                "order_name": "更新 太郎",
                "total_price": "12,345.67",
                "total_bv": "890.5",
                "bonus_date": "2025-02-20T12:34:56",
            },
        )
        request.user = MagicMock()
        return request

    def test_update_requires_legacy_orders_update_permission(self):
        access = SimpleNamespace(can_menu=lambda _key: True, can_update=False)

        with patch("connect.legacy_orders.get_user_access", return_value=access), patch(
            "connect.legacy_orders.fetch_one_dict"
        ) as mock_fetch:
            response = self.view.post(self._request())

        self.assertEqual(response.status_code, 403)
        mock_fetch.assert_not_called()

    def test_update_changes_editable_fields_and_records_audit(self):
        access = SimpleNamespace(can_menu=lambda _key: True, can_update=True)
        before_row = {
            "ID": 123,
            "DOC_NO": "ORD-123",
            "MEMBER_ID": "100",
            "ORDER_STATUS": "35",
            "ORDER_TYPE": "20",
            "ORDER_DATE": datetime(2024, 1, 31, 8, 15, 0),
            "FIRSTNAME": "変更前",
            "TOTAL_NET_AMOUNT": 1000,
            "TOTAL_BV": 100,
            "BONUS_DATE": None,
        }
        cursor = MagicMock()
        cursor.rowcount = 1
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch("connect.legacy_orders.get_user_access", return_value=access), patch(
            "connect.legacy_orders.fetch_one_dict",
            side_effect=[{"ID": 999}, before_row],
        ), patch("connect.legacy_orders.connections", {"rds": connection}), patch(
            "connect.legacy_orders.transaction"
        ), patch("connect.legacy_orders.messages"), patch(
            "connect.legacy_orders.record_change_audit"
        ) as mock_audit, patch.object(
            self.view, "_invalidate_total_count_cache"
        ) as mock_invalidate:
            response = self.view.post(self._request())

        self.assertEqual(response.status_code, 302)
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[0:4], ["ORD-UPDATED", "999", "20", "30"])
        self.assertEqual(update_params[4], datetime(2025, 2, 28, 8, 15, 0))
        self.assertEqual(update_params[5], "更新 太郎")
        self.assertEqual(str(update_params[6]), "12345.67")
        self.assertEqual(str(update_params[7]), "890.5")
        self.assertEqual(update_params[8], datetime(2025, 2, 20, 12, 34, 56))
        self.assertEqual(update_params[9], 123)
        mock_audit.assert_called_once()
        self.assertEqual(mock_audit.call_args.kwargs["target_pk"], 123)
        self.assertEqual(mock_audit.call_args.kwargs["after_values"]["DOC_NO"], "ORD-UPDATED")
        self.assertEqual(mock_audit.call_args.kwargs["after_values"]["MEMBER_ID"], "999")
        mock_invalidate.assert_called_once()

    def test_update_keeps_unknown_member_no_as_is(self):
        """会員テーブルに無い会員コードは、入力値をそのまま MEMBER_ID に保存する。"""
        access = SimpleNamespace(can_menu=lambda _key: True, can_update=True)
        before_row = {
            "ID": 123,
            "DOC_NO": "ORD-123",
            "MEMBER_ID": "100",
            "ORDER_STATUS": "35",
            "ORDER_TYPE": "20",
            "ORDER_DATE": datetime(2024, 1, 31, 8, 15, 0),
            "FIRSTNAME": "変更前",
            "TOTAL_NET_AMOUNT": 1000,
            "TOTAL_BV": 100,
            "BONUS_DATE": None,
        }
        cursor = MagicMock()
        cursor.rowcount = 1
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch("connect.legacy_orders.get_user_access", return_value=access), patch(
            "connect.legacy_orders.fetch_one_dict",
            side_effect=[None, before_row],
        ), patch("connect.legacy_orders.connections", {"rds": connection}), patch(
            "connect.legacy_orders.transaction"
        ), patch("connect.legacy_orders.messages") as mock_messages, patch(
            "connect.legacy_orders.record_change_audit"
        ) as mock_audit, patch.object(
            self.view, "_invalidate_total_count_cache"
        ):
            response = self.view.post(self._request())

        self.assertEqual(response.status_code, 302)
        mock_messages.error.assert_not_called()
        mock_messages.warning.assert_called_once()
        update_params = cursor.execute.call_args.args[1]
        self.assertEqual(update_params[1], "JP9999999")
        self.assertEqual(
            mock_audit.call_args.kwargs["after_values"]["MEMBER_ID"], "JP9999999"
        )

    def test_update_rejects_too_long_unknown_member_no(self):
        access = SimpleNamespace(can_menu=lambda _key: True, can_update=True)
        request = self._request()
        request.POST = request.POST.copy()
        request.POST["member_no"] = "J" * 61

        with patch("connect.legacy_orders.get_user_access", return_value=access), patch(
            "connect.legacy_orders.fetch_one_dict", return_value=None
        ), patch("connect.legacy_orders.messages") as mock_messages:
            response = self.view.post(request)

        self.assertEqual(response.status_code, 302)
        mock_messages.error.assert_called_once()
        self.assertEqual(
            mock_messages.error.call_args.args[1],
            "会員IDは60文字以内で入力してください。",
        )


class UserTargetRankRegisterTests(SimpleTestCase):
    """user_add_rank が保存できずに毎回 78,000件の再構築が走っていた不具合の回帰テスト。"""

    def test_setting_is_upserted_so_it_survives_a_missing_row(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.rowcount = 78553
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch("connect.views.connections", {"rds": connection}):
            inserted_count, target_rank = register_users_target_rank(2026, 7)

        self.assertEqual(inserted_count, 78553)
        self.assertEqual(target_rank, "202607")

        setting_sql, setting_params = cursor.execute.call_args.args
        self.assertIn("INSERT INTO bonus_db.settings", setting_sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", setting_sql)
        self.assertIn("'user_add_rank'", setting_sql)
        self.assertEqual(setting_params, ["202607"])
        # 他の設定行を巻き込まないこと
        self.assertNotIn("old_gyouseki_kibetu", setting_sql)
        self.assertNotIn("set_title", setting_sql)


class EnsureUserTargetRankTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/week_bonus/")
        self.request.user = SimpleNamespace(username="admin")

    def _run(self, current_rank, has_history):
        with patch("connect.views.get_user_add_rank_setting", return_value=current_rank), patch(
            "connect.views.has_user_target_rank_history", return_value=has_history
        ), patch("connect.views.register_users_target_rank") as mock_register, patch(
            "connect.views.insert_bonus_register_history"
        ) as mock_history, patch(
            "connect.views.transaction"
        ), patch("connect.views.messages"):
            result = ensure_user_target_rank_for_kibetu(self.request, "2026C08W3")
        return result, mock_register, mock_history

    def test_same_rank_skips_the_rebuild(self):
        result, mock_register, _ = self._run("202607", has_history=True)

        self.assertTrue(result)
        mock_register.assert_not_called()

    def test_same_rank_does_not_add_another_history_row(self):
        _result, _mock_register, mock_history = self._run("202607", has_history=True)

        mock_history.assert_not_called()

    def test_same_rank_records_history_once_when_it_is_missing(self):
        _result, mock_register, mock_history = self._run("202607", has_history=False)

        mock_register.assert_not_called()
        mock_history.assert_called_once()
        self.assertEqual(mock_history.call_args.args[1], "202607")

    def test_different_rank_still_rebuilds(self):
        mock_register_return = (78553, "202607")
        with patch("connect.views.get_user_add_rank_setting", return_value="202606"), patch(
            "connect.views.has_user_target_rank_history", return_value=False
        ), patch(
            "connect.views.register_users_target_rank", return_value=mock_register_return
        ) as mock_register, patch(
            "connect.views.insert_bonus_register_history"
        ), patch("connect.views.transaction"), patch("connect.views.messages"):
            result = ensure_user_target_rank_for_kibetu(self.request, "2026C08W3")

        self.assertTrue(result)
        mock_register.assert_called_once_with(2026, 7)


class WeekBonusPreRegisterFlowTests(SimpleTestCase):
    """「計算」の事前登録はGETの副作用なので、成功したらクリーンなURLへ逃がす。"""

    def setUp(self):
        self.factory = RequestFactory()

    def _view(self, query):
        request = self.factory.get("/week_bonus/", query)
        request.user = SimpleNamespace(username="admin")
        view = WeekBonusView()
        view.setup(request)
        return view, request

    @staticmethod
    def _patched_period_master():
        mock_pm = patch("connect.views.PeriodMaster").start()
        mock_pm.objects.using.return_value.filter.return_value.first.return_value = (
            SimpleNamespace(kibetu="2026C08W3")
        )
        mock_pm.objects.using.return_value.all.return_value = []
        return mock_pm

    def test_checked_boxes_run_pre_register_then_redirect_to_clean_url(self):
        view, request = self._view(
            {"kibetu": "2026C08W3", "pre_register": ["drive", "basic", "matching"]}
        )

        self.addCleanup(patch.stopall)
        self._patched_period_master()
        mock_pre = patch.object(
            WeekBonusView, "_pre_register_selected_bonuses", return_value=True
        ).start()

        response = view.get(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/week_bonus/?kibetu=2026C08W3")
        mock_pre.assert_called_once()
        self.assertEqual(
            mock_pre.call_args.args[2], ["drive", "basic", "matching"]
        )

    def test_clean_url_does_not_re_register(self):
        """リダイレクト後のURLをF5しても登録が走らないこと。"""
        view, request = self._view({"kibetu": "2026C08W3"})

        self.addCleanup(patch.stopall)
        self._patched_period_master()
        mock_pre = patch.object(
            WeekBonusView, "_pre_register_selected_bonuses"
        ).start()
        patch.object(WeekBonusView, "_get_week_bonus_rows", return_value=[]).start()
        patch("connect.views.get_week_bonus_history_rows", return_value=[]).start()
        patch("connect.views.insert_empty_bonus_history_on_display").start()

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        mock_pre.assert_not_called()
        self.assertEqual(response.context_data["pre_register_targets"], [])

    def test_pre_register_failure_shows_no_rows_and_does_not_redirect(self):
        view, request = self._view({"kibetu": "2026C08W3", "pre_register": ["drive"]})

        self.addCleanup(patch.stopall)
        self._patched_period_master()
        patch.object(
            WeekBonusView, "_pre_register_selected_bonuses", return_value=False
        ).start()
        mock_rows = patch.object(WeekBonusView, "_get_week_bonus_rows").start()
        patch("connect.views.get_week_bonus_history_rows", return_value=[]).start()

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["rows"], [])
        mock_rows.assert_not_called()

    def test_first_visit_defaults_to_all_bonuses_checked(self):
        view, _request = self._view({})

        self.assertEqual(
            view._get_pre_register_targets(), ["drive", "basic", "matching"]
        )
