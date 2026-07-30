import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.shortcuts import redirect
from django.views import generic


logger = logging.getLogger(__name__)


def _parse_date(value, label):
    value = (value or "").strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"{label}の日付形式が不正です。（例: 2026-07-01）")


class CampaignListView(generic.TemplateView):
    template_name = "campaign_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_campaign_name = (self.request.GET.get("q_campaign_name") or "").strip()
        q_campaign_code = (self.request.GET.get("q_campaign_code") or "").strip()
        q_status = (self.request.GET.get("q_status") or "").strip()

        ctx["q_campaign_name"] = q_campaign_name
        ctx["q_campaign_code"] = q_campaign_code
        ctx["q_status"] = q_status
        ctx["rows"] = self._get_rows(q_campaign_name, q_campaign_code, q_status)

        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        next_query = (request.POST.get("next_query") or "").strip()
        base_url = redirect("connect:campaign_list").url
        redirect_target = f"{base_url}?{next_query}" if next_query else base_url

        try:
            if action == "create":
                if self._create(request):
                    messages.success(request, "キャンペーンを登録しました。")
            elif action == "update":
                if self._update(request):
                    messages.success(request, "キャンペーンを更新しました。")
            elif action == "delete":
                if self._delete(request):
                    messages.success(request, "キャンペーンを削除しました。")
            else:
                messages.error(request, "不正な操作です。")
        except ValueError as e:
            messages.error(request, str(e))
        except IntegrityError:
            logger.exception("キャンペーンの登録・更新エラー")
            messages.error(request, "同じキャンペーンコードがすでに登録されています。")
        except Exception as e:
            logger.exception("キャンペーン操作エラー")
            messages.error(request, f"エラーが発生しました: {e}")

        return redirect(redirect_target)

    def _get_rows(self, q_campaign_name="", q_campaign_code="", q_status=""):
        where = []
        params = []

        if q_campaign_name:
            where.append("campaign_name LIKE %s")
            params.append(f"%{q_campaign_name}%")

        if q_campaign_code:
            where.append("campaign_code LIKE %s")
            params.append(f"%{q_campaign_code}%")

        if q_status in ("0", "1"):
            where.append("status = %s")
            params.append(int(q_status))

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT
                id,
                campaign_code,
                campaign_name,
                description,
                start_date,
                end_date,
                display_order,
                status,
                created_at
            FROM bonus_db.campaign_master
            {where_sql}
            ORDER BY display_order ASC, start_date DESC, id DESC
        """

        try:
            with connections["rds"].cursor() as cursor:
                logger.info("キャンペーン一覧取得SQLを実行します。")
                cursor.execute(sql, params)
                cols = [c[0] for c in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except DatabaseError:
            logger.exception("キャンペーン一覧の取得に失敗しました。")
            messages.error(
                self.request,
                "キャンペーンデータを取得できませんでした。bonus_db.campaign_master テーブルを確認してください。",
            )
            return []

    def _read_form(self, request):
        campaign_code = (request.POST.get("campaign_code") or "").strip()
        campaign_name = (request.POST.get("campaign_name") or "").strip()
        description = (request.POST.get("description") or "").strip()

        if not campaign_code:
            raise ValueError("キャンペーンコードを入力してください。")

        if len(campaign_code) > 50:
            raise ValueError("キャンペーンコードは50文字以内で入力してください。")

        if not campaign_name:
            raise ValueError("キャンペーン名を入力してください。")

        if len(campaign_name) > 255:
            raise ValueError("キャンペーン名は255文字以内で入力してください。")

        try:
            status = int(request.POST.get("status", 1))
        except (TypeError, ValueError):
            raise ValueError("状態の値が不正です。")

        if status not in (0, 1):
            raise ValueError("状態の値が不正です。")

        try:
            display_order = int(request.POST.get("display_order") or 0)
        except (TypeError, ValueError):
            raise ValueError("表示順は数値で入力してください。")

        start_date = _parse_date(request.POST.get("start_date"), "開始日")
        end_date = _parse_date(request.POST.get("end_date"), "終了日")

        if start_date and end_date and start_date > end_date:
            raise ValueError("終了日は開始日以降で入力してください。")

        return {
            "campaign_code": campaign_code,
            "campaign_name": campaign_name,
            "description": description or None,
            "start_date": start_date,
            "end_date": end_date,
            "display_order": display_order,
            "status": status,
        }

    def _read_row_id(self, request, label):
        raw_id = (request.POST.get("id") or "").strip()

        try:
            return int(raw_id)
        except (TypeError, ValueError):
            raise ValueError(f"{label}対象が不正です。")

    def _create(self, request):
        form = self._read_form(request)

        sql = """
            INSERT INTO bonus_db.campaign_master (
                campaign_code,
                campaign_name,
                description,
                start_date,
                end_date,
                display_order,
                status
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
        """

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                logger.info("キャンペーン登録SQLを実行します。code=%s", form["campaign_code"])
                cursor.execute(
                    sql,
                    [
                        form["campaign_code"],
                        form["campaign_name"],
                        form["description"],
                        form["start_date"],
                        form["end_date"],
                        form["display_order"],
                        form["status"],
                    ],
                )

        return True

    def _update(self, request):
        row_id = self._read_row_id(request, "更新")
        form = self._read_form(request)

        sql = """
            UPDATE bonus_db.campaign_master
            SET
                campaign_code = %s,
                campaign_name = %s,
                description = %s,
                start_date = %s,
                end_date = %s,
                display_order = %s,
                status = %s
            WHERE id = %s
        """

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                if not self._exists(cursor, row_id):
                    messages.error(request, "更新対象データがありません。")
                    return False

                logger.info("キャンペーン更新SQLを実行します。id=%s", row_id)
                cursor.execute(
                    sql,
                    [
                        form["campaign_code"],
                        form["campaign_name"],
                        form["description"],
                        form["start_date"],
                        form["end_date"],
                        form["display_order"],
                        form["status"],
                        row_id,
                    ],
                )

        return True

    def _delete(self, request):
        row_id = self._read_row_id(request, "削除")

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                if not self._exists(cursor, row_id):
                    messages.error(request, "削除対象データがありません。")
                    return False

                member_count = self._count_eligible_members(cursor, row_id)
                if member_count:
                    messages.error(
                        request,
                        f"対象会員が{member_count}件登録されているため削除できません。"
                        "先にキャンペーン対象を削除してください。",
                    )
                    return False

                logger.info("キャンペーン削除SQLを実行します。id=%s", row_id)
                cursor.execute(
                    "DELETE FROM bonus_db.campaign_master WHERE id = %s",
                    [row_id],
                )

        return True

    def _exists(self, cursor, row_id):
        cursor.execute(
            """
            SELECT id
            FROM bonus_db.campaign_master
            WHERE id = %s
            FOR UPDATE
            """,
            [row_id],
        )
        return cursor.fetchone() is not None

    def _count_eligible_members(self, cursor, campaign_id):
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM bonus_db.campaign_eligible_members
            WHERE campaign_id = %s
            """,
            [campaign_id],
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0


class CampaignTargetView(generic.TemplateView):
    template_name = "campaign_target.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_campaign_id = (self.request.GET.get("q_campaign_id") or "").strip()
        q_jwoa_code = (self.request.GET.get("q_jwoa_code") or "").strip()
        q_eligible_status = (self.request.GET.get("q_eligible_status") or "").strip()
        q_payment_status = (self.request.GET.get("q_payment_status") or "").strip()

        rows = self._get_rows(
            q_campaign_id,
            q_jwoa_code,
            q_eligible_status,
            q_payment_status,
        )

        ctx["q_campaign_id"] = q_campaign_id
        ctx["q_jwoa_code"] = q_jwoa_code
        ctx["q_eligible_status"] = q_eligible_status
        ctx["q_payment_status"] = q_payment_status
        ctx["campaigns"] = self._get_campaigns()
        ctx["rows"] = rows
        ctx["total_bonus_amount"] = sum(r["bonus_amount"] or 0 for r in rows)

        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        next_query = (request.POST.get("next_query") or "").strip()
        base_url = redirect("connect:campaign_target").url
        redirect_target = f"{base_url}?{next_query}" if next_query else base_url

        try:
            if action == "create":
                if self._create(request):
                    messages.success(request, "キャンペーン対象を登録しました。")
            elif action == "update":
                if self._update(request):
                    messages.success(request, "キャンペーン対象を更新しました。")
            elif action == "delete":
                if self._delete(request):
                    messages.success(request, "キャンペーン対象を削除しました。")
            else:
                messages.error(request, "不正な操作です。")
        except ValueError as e:
            messages.error(request, str(e))
        except IntegrityError:
            logger.exception("キャンペーン対象の登録・更新エラー")
            messages.error(
                request,
                "同じキャンペーンに同じ会員IDがすでに登録されています。",
            )
        except Exception as e:
            logger.exception("キャンペーン対象操作エラー")
            messages.error(request, f"エラーが発生しました: {e}")

        return redirect(redirect_target)

    def _get_campaigns(self):
        sql = """
            SELECT
                id,
                campaign_code,
                campaign_name,
                status
            FROM bonus_db.campaign_master
            ORDER BY display_order ASC, start_date DESC, id DESC
        """

        try:
            with connections["rds"].cursor() as cursor:
                cursor.execute(sql)
                cols = [c[0] for c in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except DatabaseError:
            logger.exception("キャンペーンマスタの取得に失敗しました。")
            return []

    def _get_rows(
        self,
        q_campaign_id="",
        q_jwoa_code="",
        q_eligible_status="",
        q_payment_status="",
    ):
        where = []
        params = []

        if q_campaign_id.isdigit():
            where.append("m.campaign_id = %s")
            params.append(int(q_campaign_id))

        if q_jwoa_code:
            where.append("m.jwoa_code LIKE %s")
            params.append(f"%{q_jwoa_code}%")

        if q_eligible_status in ("0", "1"):
            where.append("m.eligible_status = %s")
            params.append(int(q_eligible_status))

        if q_payment_status in ("0", "1"):
            where.append("m.payment_status = %s")
            params.append(int(q_payment_status))

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT
                m.id,
                m.campaign_id,
                c.campaign_code,
                c.campaign_name,
                m.jwoa_code,
                COALESCE(NULLIF(u.send_bv_name, ''), u.name) AS member_name,
                m.bonus_amount,
                m.eligible_status,
                m.payment_status,
                m.payment_date,
                m.note,
                m.created_at
            FROM bonus_db.campaign_eligible_members AS m
            LEFT JOIN bonus_db.campaign_master AS c
                ON m.campaign_id = c.id
            LEFT JOIN nexus_production.users AS u
                ON m.jwoa_code = u.jmoa_code
            {where_sql}
            ORDER BY c.display_order ASC, c.id DESC, m.jwoa_code ASC
        """

        try:
            with connections["rds"].cursor() as cursor:
                logger.info("キャンペーン対象一覧取得SQLを実行します。")
                cursor.execute(sql, params)
                cols = [c[0] for c in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except DatabaseError:
            logger.exception("キャンペーン対象一覧の取得に失敗しました。")
            messages.error(
                self.request,
                "キャンペーン対象データを取得できませんでした。"
                "bonus_db.campaign_eligible_members テーブルを確認してください。",
            )
            return []

    def _read_form(self, request):
        raw_campaign_id = (request.POST.get("campaign_id") or "").strip()
        jwoa_code = (request.POST.get("jwoa_code") or "").strip()
        note = (request.POST.get("note") or "").strip()

        if not raw_campaign_id.isdigit():
            raise ValueError("キャンペーンを選択してください。")

        campaign_id = int(raw_campaign_id)

        if not jwoa_code:
            raise ValueError("会員IDを入力してください。")

        if len(jwoa_code) > 20:
            raise ValueError("会員IDは20文字以内で入力してください。")

        if len(note) > 500:
            raise ValueError("備考は500文字以内で入力してください。")

        try:
            bonus_amount = Decimal(request.POST.get("bonus_amount") or "0")
        except (InvalidOperation, TypeError):
            raise ValueError("ボーナス金額は数値で入力してください。")

        if bonus_amount < 0:
            raise ValueError("ボーナス金額は0以上で入力してください。")

        if bonus_amount >= Decimal("10000000000000"):
            raise ValueError("ボーナス金額が大きすぎます。")

        try:
            eligible_status = int(request.POST.get("eligible_status", 1))
            payment_status = int(request.POST.get("payment_status", 0))
        except (TypeError, ValueError):
            raise ValueError("対象状態・支払状態の値が不正です。")

        if eligible_status not in (0, 1) or payment_status not in (0, 1):
            raise ValueError("対象状態・支払状態の値が不正です。")

        payment_date = _parse_date(request.POST.get("payment_date"), "支払日")

        if payment_status == 1 and payment_date is None:
            raise ValueError("支払済にする場合は支払日を入力してください。")

        return {
            "campaign_id": campaign_id,
            "jwoa_code": jwoa_code,
            "bonus_amount": bonus_amount,
            "eligible_status": eligible_status,
            "payment_status": payment_status,
            "payment_date": payment_date,
            "note": note or None,
        }

    def _read_row_id(self, request, label):
        raw_id = (request.POST.get("id") or "").strip()

        try:
            return int(raw_id)
        except (TypeError, ValueError):
            raise ValueError(f"{label}対象が不正です。")

    def _create(self, request):
        form = self._read_form(request)

        sql = """
            INSERT INTO bonus_db.campaign_eligible_members (
                campaign_id,
                jwoa_code,
                bonus_amount,
                eligible_status,
                payment_status,
                payment_date,
                note
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
        """

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                if not self._campaign_exists(cursor, form["campaign_id"]):
                    messages.error(request, "選択されたキャンペーンが存在しません。")
                    return False

                if not self._user_exists(cursor, form["jwoa_code"]):
                    messages.error(
                        request,
                        f"会員ID {form['jwoa_code']} は会員マスタに存在しません。",
                    )
                    return False

                logger.info(
                    "キャンペーン対象登録SQLを実行します。campaign_id=%s jwoa_code=%s",
                    form["campaign_id"],
                    form["jwoa_code"],
                )
                cursor.execute(
                    sql,
                    [
                        form["campaign_id"],
                        form["jwoa_code"],
                        form["bonus_amount"],
                        form["eligible_status"],
                        form["payment_status"],
                        form["payment_date"],
                        form["note"],
                    ],
                )

        return True

    def _update(self, request):
        row_id = self._read_row_id(request, "更新")
        form = self._read_form(request)

        sql = """
            UPDATE bonus_db.campaign_eligible_members
            SET
                campaign_id = %s,
                jwoa_code = %s,
                bonus_amount = %s,
                eligible_status = %s,
                payment_status = %s,
                payment_date = %s,
                note = %s
            WHERE id = %s
        """

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                if not self._exists(cursor, row_id):
                    messages.error(request, "更新対象データがありません。")
                    return False

                if not self._campaign_exists(cursor, form["campaign_id"]):
                    messages.error(request, "選択されたキャンペーンが存在しません。")
                    return False

                if not self._user_exists(cursor, form["jwoa_code"]):
                    messages.error(
                        request,
                        f"会員ID {form['jwoa_code']} は会員マスタに存在しません。",
                    )
                    return False

                logger.info("キャンペーン対象更新SQLを実行します。id=%s", row_id)
                cursor.execute(
                    sql,
                    [
                        form["campaign_id"],
                        form["jwoa_code"],
                        form["bonus_amount"],
                        form["eligible_status"],
                        form["payment_status"],
                        form["payment_date"],
                        form["note"],
                        row_id,
                    ],
                )

        return True

    def _delete(self, request):
        row_id = self._read_row_id(request, "削除")

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                if not self._exists(cursor, row_id):
                    messages.error(request, "削除対象データがありません。")
                    return False

                logger.info("キャンペーン対象削除SQLを実行します。id=%s", row_id)
                cursor.execute(
                    "DELETE FROM bonus_db.campaign_eligible_members WHERE id = %s",
                    [row_id],
                )

        return True

    def _exists(self, cursor, row_id):
        cursor.execute(
            """
            SELECT id
            FROM bonus_db.campaign_eligible_members
            WHERE id = %s
            FOR UPDATE
            """,
            [row_id],
        )
        return cursor.fetchone() is not None

    def _campaign_exists(self, cursor, campaign_id):
        cursor.execute(
            "SELECT id FROM bonus_db.campaign_master WHERE id = %s",
            [campaign_id],
        )
        return cursor.fetchone() is not None

    def _user_exists(self, cursor, jwoa_code):
        cursor.execute(
            "SELECT jmoa_code FROM nexus_production.users WHERE jmoa_code = %s LIMIT 1",
            [jwoa_code],
        )
        return cursor.fetchone() is not None
