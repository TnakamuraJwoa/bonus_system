from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from connect.templatetags.custom_filters import as_db_datetime, db_datetime, jp_date, jst_datetime
from connect.views import (
    BonusPaymentDateView,
    OrdersDistributionBvView,
    S_MonthBonusView,
    S_WeekBonusView,
    UsersView,
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
