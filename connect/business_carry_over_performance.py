import csv
import io
import logging
import math

import openpyxl
from django.contrib import messages
from django.db import ProgrammingError, connections, transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import generic

from .views import KeysetPaginationMixin


logger = logging.getLogger(__name__)

BASIC_BV_LINE_TABLE = "bonus_db.basic_bv_line"
BASIC_BV_LINE_IMPORT_COLUMNS = {
    "placement_code": "placement_code",
    "上位者コード": "placement_code",
    "上位者id": "placement_code",
    "jmoa_code": "jmoa_code",
    "会員コード": "jmoa_code",
    "会員id": "jmoa_code",
    "bv": "bv",
    "carry_over_bv": "carry_over_bv",
    "繰り越しbv": "carry_over_bv",
    "繰越しbv": "carry_over_bv",
    "繰越bv": "carry_over_bv",
    "kibetu": "kibetu",
    "期別": "kibetu",
}
REQUIRED_IMPORT_COLUMNS = ["placement_code", "jmoa_code", "bv", "carry_over_bv", "kibetu"]


def is_missing_table_error(exc):
    return bool(exc.args and exc.args[0] == 1146)


def normalize_import_header(value):
    return str(value or "").strip().lower().replace(" ", "").replace("　", "")


def parse_import_int(value, row_number, column_label, errors):
    if value is None or str(value).strip() == "":
        return 0

    text = str(value).strip().replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        errors.append(f"{row_number}行目: {column_label} は数値で入力してください。")
        return 0


def iter_uploaded_rows(uploaded_file):
    filename = (uploaded_file.name or "").lower()

    if filename.endswith((".xlsx", ".xlsm")):
        workbook = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
        sheet = workbook.active
        return list(sheet.iter_rows(values_only=True))

    raw = uploaded_file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp932")
    return list(csv.reader(io.StringIO(text)))


def parse_basic_bv_line_import_rows(uploaded_file):
    source_rows = iter_uploaded_rows(uploaded_file)
    errors = []
    data_rows = []

    header_row = None
    header_row_number = 0
    for index, row in enumerate(source_rows, start=1):
        if any(str(cell or "").strip() for cell in row):
            header_row = row
            header_row_number = index
            break

    if not header_row:
        return [], ["取込ファイルにヘッダー行がありません。"]

    column_map = {}
    for index, header in enumerate(header_row):
        normalized_header = normalize_import_header(header)
        column_name = BASIC_BV_LINE_IMPORT_COLUMNS.get(normalized_header)
        if column_name:
            column_map[column_name] = index

    missing_columns = [
        column_name
        for column_name in REQUIRED_IMPORT_COLUMNS
        if column_name not in column_map
    ]
    if missing_columns:
        return [], [f"必須列が不足しています: {', '.join(missing_columns)}"]

    for row_number, row in enumerate(source_rows[header_row_number:], start=header_row_number + 1):
        if not any(str(cell or "").strip() for cell in row):
            continue

        def get_cell(column_name):
            index = column_map[column_name]
            return row[index] if index < len(row) else ""

        placement_code = str(get_cell("placement_code") or "").strip()
        jmoa_code = str(get_cell("jmoa_code") or "").strip()
        kibetu = str(get_cell("kibetu") or "").strip()

        if not placement_code:
            errors.append(f"{row_number}行目: 上位者コードは必須です。")
        if not jmoa_code:
            errors.append(f"{row_number}行目: 会員コードは必須です。")
        if not kibetu:
            errors.append(f"{row_number}行目: 期別は必須です。")

        bv = parse_import_int(get_cell("bv"), row_number, "BV", errors)
        carry_over_bv = parse_import_int(
            get_cell("carry_over_bv"),
            row_number,
            "繰り越しBV",
            errors,
        )

        if placement_code and jmoa_code and kibetu:
            data_rows.append([
                placement_code,
                jmoa_code,
                bv,
                carry_over_bv,
                kibetu,
            ])

    if not data_rows and not errors:
        errors.append("登録対象データがありません。")

    return data_rows, errors


def fetch_carry_over_history_rows():
    sql = f"""
        SELECT
            h.kibetu,
            h.row_count,
            h.created_at,
            h.updated_at,
            pm.st_date,
            pm.end_date,
            pm.completion_date,
            NULL AS year,
            NULL AS month,
            NULL AS payment_date
        FROM (
            SELECT
                kibetu,
                COUNT(*) AS row_count,
                MIN(created_at) AS created_at,
                MAX(created_at) AS updated_at
            FROM {BASIC_BV_LINE_TABLE}
            GROUP BY kibetu
        ) AS h
        LEFT JOIN bonus_db.period_master AS pm
          ON pm.kibetu = h.kibetu
        ORDER BY h.kibetu DESC
    """
    with connections["rds"].cursor() as cursor:
        logger.info("繰り越し業績履歴取得SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
        try:
            cursor.execute(sql)
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except ProgrammingError as exc:
            if is_missing_table_error(exc):
                logger.info("繰り越し業績テーブルが未作成です。table=%s", BASIC_BV_LINE_TABLE)
                return []
            raise


class CarryOverPerformanceTemplateView(generic.View):
    def get(self, request, *args, **kwargs):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "繰り越しBV"
        ws.append(["期別", "上位者コード", "会員コード", "BV", "繰り越しBV"])
        ws.append(["2025C03", "JP00000001", "JP05215357", 100, 50])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            'attachment; filename="carry_over_performance_template.xlsx"'
        )
        wb.save(response)
        return response


class CarryOverPerformanceView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "business_carry_over_performance.html"

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("carry_over_file")
        if not uploaded_file:
            messages.error(request, "取込ファイルを選択してください。")
            return redirect("connect:business_carry_over_performance")

        try:
            rows, errors = parse_basic_bv_line_import_rows(uploaded_file)
            if errors:
                for error in errors[:10]:
                    messages.error(request, error)
                if len(errors) > 10:
                    messages.error(request, f"他 {len(errors) - 10} 件のエラーがあります。")
                return redirect("connect:business_carry_over_performance")

            insert_sql = f"""
                INSERT INTO {BASIC_BV_LINE_TABLE} (
                    placement_code,
                    jmoa_code,
                    bv,
                    carry_over_bv,
                    kibetu,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
                )
                ON DUPLICATE KEY UPDATE
                    bv = VALUES(bv),
                    carry_over_bv = VALUES(carry_over_bv),
                    created_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
            """
            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    logger.info("繰り越しBV一括登録SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
                    cursor.executemany(insert_sql, rows)

            messages.success(request, f"{len(rows)}件を繰り越しBV管理に一括登録しました。")
        except Exception as exc:
            logger.exception("繰り越しBV一括登録エラー")
            messages.error(request, f"登録中にエラーが発生しました: {exc}")

        return redirect("connect:business_carry_over_performance")

    def _build_where(self, q_kibetu="", q_placement_code="", q_jmoa_code=""):
        where = []
        params = []

        if q_kibetu:
            where.append("kibetu = %s")
            params.append(q_kibetu)

        if q_placement_code:
            where.append("placement_code LIKE %s")
            params.append(f"%{q_placement_code}%")

        if q_jmoa_code:
            where.append("jmoa_code LIKE %s")
            params.append(f"%{q_jmoa_code}%")

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return where_sql, params

    def _fetch_total_count(self, q_kibetu="", q_placement_code="", q_jmoa_code=""):
        where_sql, params = self._build_where(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
        )
        sql = f"""
            SELECT COUNT(*)
            FROM {BASIC_BV_LINE_TABLE}
            {where_sql}
        """
        with connections["rds"].cursor() as cursor:
            logger.info("繰り越し業績件数取得SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("繰り越し業績テーブルが未作成です。table=%s", BASIC_BV_LINE_TABLE)
                    return 0
                raise
        return int(row[0]) if row else 0

    def _fetch_rows(self, q_kibetu="", q_placement_code="", q_jmoa_code="", limit=200, offset=0):
        where_sql, params = self._build_where(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
        )
        sql = f"""
            SELECT
                id,
                kibetu,
                placement_code,
                jmoa_code,
                bv,
                carry_over_bv,
                created_at
            FROM {BASIC_BV_LINE_TABLE}
            {where_sql}
            ORDER BY kibetu DESC, placement_code, jmoa_code
            LIMIT %s OFFSET %s
        """
        with connections["rds"].cursor() as cursor:
            logger.info("繰り越し業績一覧取得SQLを実行します。table=%s", BASIC_BV_LINE_TABLE)
            try:
                cursor.execute(sql, params + [limit, offset])
                cols = [col[0] for col in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("繰り越し業績テーブルが未作成です。table=%s", BASIC_BV_LINE_TABLE)
                    return []
                raise

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q_kibetu = (self.request.GET.get("q_kibetu") or "").strip()
        q_placement_code = (self.request.GET.get("q_placement_code") or "").strip()
        q_jmoa_code = (self.request.GET.get("q_jmoa_code") or "").strip()
        kibetu_choice_mode = self.request.GET.get("kibetu_choice_mode") or "recent"

        per_page = self.get_per_page()
        total_count = self._fetch_total_count(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
        )
        total_pages = max(1, math.ceil(total_count / per_page))
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page

        rows = self._fetch_rows(
            q_kibetu=q_kibetu,
            q_placement_code=q_placement_code,
            q_jmoa_code=q_jmoa_code,
            limit=per_page,
            offset=offset,
        )

        ctx["q_kibetu"] = q_kibetu
        ctx["q_placement_code"] = q_placement_code
        ctx["q_jmoa_code"] = q_jmoa_code
        ctx["active_menu"] = "business_carry_over_performance"
        ctx["registration_history_rows"] = fetch_carry_over_history_rows()
        ctx["registration_history_modal_id"] = "carryOverPerformanceHistoryModal"
        ctx["registration_modal_title"] = "登録履歴（繰り越し業績照会）"
        ctx["registration_target_url_name"] = "connect:business_carry_over_performance"
        return self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params={
                "q_kibetu": q_kibetu,
                "q_placement_code": q_placement_code,
                "q_jmoa_code": q_jmoa_code,
                "per_page": per_page,
                "kibetu_choice_mode": kibetu_choice_mode,
            },
        )
