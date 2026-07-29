import logging

from django.db import connections, transaction


logger = logging.getLogger(__name__)


DEFAULT_BONUS_HELP = {
    "drive_bonus": {
        "title": "ドライブボーナスの説明",
        "content": "\n".join([
            "ドライブボーナスは、週次の対象期間で組織実績や条件を確認し、対象者のボーナス額を算出します。",
            "計算時は、期別の前月ユーザーランクを自動登録してから算出します。",
            "例: 2026C05W4 の場合、2026年4月（202604）のユーザーランクを使用します。",
        ]),
    },
    "basic_bonus": {
        "title": "ベーシックボーナスの説明",
        "content": "ベーシックボーナスは、週次の対象期間で基本条件を満たした実績をもとにボーナス額を算出します。",
    },
    "matching_bonus": {
        "title": "マッチングボーナスの説明",
        "content": "マッチングボーナスは、週次の対象期間で紹介・組織の条件を確認し、対象者のマッチング報酬を算出します。",
    },
    "week_bonus": {
        "title": "週ボーナスの説明",
        "content": "週ボーナスは、週次の対象期間で集計した実績をもとに、週単位のボーナスを算出します。",
    },
    "title_bonus": {
        "title": "タイトルボーナスの説明",
        "content": "\n".join([
            "当月、3スターダイヤ以上。",
            "前月、当月、アクティブ。",
            "新規登録月は、前月、当月アクティブ扱い。",
            "直紹介した傘下組織内のポジションで、当月3スターダイヤ以上の実績達成者がいること。",
            "タイトル判定のところでも、再購入・特別対応は合算して上限50BVまで。",
            "ダブルクラウンはクラウンダイヤと同じ%。",
            "傘下組織とは上位者のこと。",
        ]),
    },
    "title_diff_bonus": {
        "title": "タイトル差額ボーナスの説明",
        "content": "タイトル差額ボーナスは、対象者と下位者のタイトル差や実績を確認し、差額分のボーナスを算出します。",
    },
    "repurchase_over_bonus": {
        "title": "再購入オーバーボーナスの説明",
        "content": "再購入オーバーボーナスは、再購入実績と対象条件を確認し、条件を超過した分のボーナスを算出します。",
    },
    "three_star_global_bonus": {
        "title": "3スターダイヤグローバル配当の説明",
        "content": "3スターダイヤグローバル配当は、対象タイトルや配当条件を確認し、グローバル配当額を算出します。",
    },
    "global_bonus": {
        "title": "グローバル配当の説明",
        "content": "グローバル配当は、対象タイトルや配当条件を確認し、グローバル配当額を算出します。（計算ロジックは準備中です）",
    },
    "month_bonus": {
        "title": "月ボーナスの説明",
        "content": "月ボーナスは、指定した期別の月次実績をもとに、月単位のボーナスを算出します。",
    },
    "month_title": {
        "title": "月タイトルの説明",
        "content": "月タイトルは、指定した期別の購入情報から収入ライン系列BVと基本ライン系列BVを集計し、会員ごとのタイトルIDを算出します。",
    },
    "month_title_detail": {
        "title": "月タイトル詳細の説明",
        "content": "月タイトル詳細は、登録済み月タイトルを期別ごとに確認し、対象会員を選択すると収入ライン系列BV・基本ライン系列BVの内訳をライン別集計と購入者明細で確認する画面です。",
    },
    "member_month_title_search": {
        "title": "月タイトル検索の説明",
        "content": "月タイトル検索は、登録済みの月タイトル結果を期別・会員コード・会員名・タイトルで検索して確認する画面です。表示データは bonus_db.month_title に登録済みのデータです。",
    },
    "title_registration": {
        "title": "タイトルユーザー登録の説明",
        "content": "タイトルユーザー登録は、月タイトル登録済みの同一期別データを参照し、現在のタイトルID以上の対象者を確認します。登録時は履歴を残し、user_titles には現在より高いタイトルIDのみ反映します。",
    },
    "repurchase_last_month": {
        "title": "ボーナス購入情報(登録/削除)の説明",
        "content": "\n".join([
            "対象年月の購入情報をプレビューし、purchase_info_list への登録・削除を行います。",
            "通常注文は、ボーナス支払日（なければ入金日）が対象月内で、BV有効かつキャンセル等を除いた注文を対象にします。",
            "特別対応は api_users_bv の注文年月が一致するデータを対象にし、注文区分105として扱います。",
            "クーリングオフ有効な注文は、表示上の注文区分を200に置き換えます。",
            "★は登録済みの年月を示します。登録済み年月は削除、または手入力の追加・編集も可能です。",
        ]),
    },
    "business_personal_week_performance": {
        "title": "週別 個人業績の説明",
        "content": "登録済みの週次ボーナス結果を、期別・会員コードで検索して一覧表示します。ドライブボーナス、ベーシックボーナス、マッチングボーナス、週間ボーナスを確認できます。",
    },
    "business_personal_performance": {
        "title": "月別 個人業績の説明",
        "content": "登録済みの月次ボーナス結果を、期別・会員コードで検索して一覧表示します。タイトルボーナス、再購入オーバーボーナス、差額ボーナス、グローバル配当、月間ボーナスを確認できます。",
    },
    "business_team_week_performance": {
        "title": "週別 チーム業績の説明",
        "content": "購入情報からチーム業績明細を計算し、期別ごとに登録して参照します。上位会員コード・ライン会員コード・購入者・階層・BVの明細を確認できます。未登録の期別は「登録」、登録済みの期別は「再登録」で明細を更新します。",
    },
    "business_team_performance": {
        "title": "月別 チーム業績の説明",
        "content": "購入情報からチーム業績明細を計算し、期別ごとに登録して参照します。上位会員コード・ライン会員コード・購入者・階層・BVの明細を確認できます。未登録の期別は「登録」、登録済みの期別は「再登録」で明細を更新します。",
    },
    "business_carry_over_performance": {
        "title": "繰り越し業績照会の説明",
        "content": "ベーシックボーナス計算時に登録された繰り越しBV管理データを、期別・上位者コード・会員コードで検索して一覧表示します。BV と繰り越しBV を確認できます。",
    },
}

ALLOWED_BONUS_HELP_KEYS = set(DEFAULT_BONUS_HELP.keys())


def _db_help_rows():
    help_keys = sorted(ALLOWED_BONUS_HELP_KEYS)
    placeholders = ", ".join(["%s"] * len(help_keys))
    with connections["rds"].cursor() as cursor:
        logger.info("ヘルプテキスト一覧取得SQLを実行します。")
        cursor.execute(
            f"""
                SELECT help_key, title, content, updated_at
                FROM bonus_db.help_text
                WHERE help_key IN ({placeholders})
                ORDER BY help_key
            """,
            help_keys,
        )
        return cursor.fetchall()


def get_bonus_help(help_key, fallback_title=""):
    default_help = DEFAULT_BONUS_HELP.get(
        help_key,
        {
            "title": f"{fallback_title}の説明" if fallback_title else "説明",
            "content": "この画面で計算するボーナスの概要を表示します。",
        },
    )

    if help_key not in ALLOWED_BONUS_HELP_KEYS:
        return default_help

    try:
        with connections["rds"].cursor() as cursor:
            logger.info("ヘルプテキスト取得SQLを実行します。help_key=%s", help_key)
            cursor.execute(
                """
                    SELECT title, content
                    FROM bonus_db.help_text
                    WHERE help_key = %s
                    LIMIT 1
                """,
                [help_key],
            )
            row = cursor.fetchone()
    except Exception:
        logger.exception("ヘルプテキストの取得に失敗しました。help_key=%s", help_key)
        return default_help

    if not row:
        return default_help

    title, content = row
    content = (content or "").strip()
    if not content:
        return default_help

    return {
        "title": title or default_help["title"],
        "content": content,
    }


def list_bonus_help():
    db_rows = {}
    try:
        db_rows = {
            help_key: {
                "title": title,
                "content": content,
                "updated_at": updated_at,
            }
            for help_key, title, content, updated_at in _db_help_rows()
        }
    except Exception:
        logger.exception("ヘルプテキスト一覧の取得に失敗しました。")

    items = []
    for help_key, default_help in DEFAULT_BONUS_HELP.items():
        db_help = db_rows.get(help_key) or {}
        content = (db_help.get("content") or "").strip()
        title = (db_help.get("title") or "").strip()
        items.append({
            "help_key": help_key,
            "title": title or default_help["title"],
            "content": content or default_help["content"],
            "updated_at": db_help.get("updated_at"),
            "is_saved": bool(content),
        })
    return items


def save_bonus_help(help_key, title, content):
    if help_key not in ALLOWED_BONUS_HELP_KEYS:
        raise ValueError("不正なヘルプ識別キーです。")

    content = (content or "").strip()
    if not content:
        raise ValueError("ヘルプ本文を入力してください。")

    title = (title or "").strip() or DEFAULT_BONUS_HELP[help_key]["title"]

    with transaction.atomic(using="rds"):
        with connections["rds"].cursor() as cursor:
            logger.info("ヘルプテキスト保存SQLを実行します。help_key=%s", help_key)
            cursor.execute(
                """
                    INSERT INTO bonus_db.help_text (
                        help_key,
                        title,
                        content
                    ) VALUES (
                        %s,
                        %s,
                        %s
                    )
                    ON DUPLICATE KEY UPDATE
                        title = VALUES(title),
                        content = VALUES(content),
                        updated_at = CURRENT_TIMESTAMP
                """,
                [help_key, title, content],
            )

