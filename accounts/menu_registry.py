"""
画面・メニュー単位のアクセス権限レジストリ。

menu_permissions が null のユーザーは従来どおり全メニュー閲覧可。
リストで明示したキーのみ閲覧可（未選択＝その画面は不可）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuFeature:
    key: str
    label: str
    group: str
    url_names: tuple


MENU_GROUPS = (
    ("users", "会員"),
    ("orders", "注文"),
    ("bonus_search", "ボーナス検索"),
    ("bonus_calc", "ボーナス計算"),
    ("business_search", "業務検索"),
    ("settings", "設定・マスタ"),
)

MENU_FEATURES = (
    # --- 会員 ---
    MenuFeature("users", "会員一覧", "users", ("users",)),
    MenuFeature("title_user", "ピンタイトル一覧", "users", ("title_user",)),
    # --- 注文 ---
    MenuFeature("orders", "注文一覧", "orders", ("orders", "order_detail")),
    MenuFeature(
        "orders_distribution_bv",
        "BV振分情報",
        "orders",
        ("orders_distribution_bv",),
    ),
    MenuFeature("api_users_bv", "会員BV特別反映情報", "orders", ("api_users_bv",)),
    MenuFeature("repurchase_last_month", "ボーナス購入情報登録", "orders", ("repurchase_last_month",)),
    MenuFeature("repurchase_list", "ボーナス購入情報一覧", "orders", ("repurchase_list",)),
    MenuFeature("bonus_payment_date", "注文別ボーナス支払日", "orders", ("bonus_payment_date",)),
    MenuFeature("cooling_off", "クーリングオフ", "orders", ("cooling_off",)),
    # --- ボーナス検索（個人） ---
    MenuFeature("s_drive_bonus", "ドライブボーナス（検索）", "bonus_search", ("s_drive_bonus",)),
    MenuFeature("s_basic_bonus", "ベーシックボーナス（検索）", "bonus_search", ("s_basic_bonus",)),
    MenuFeature(
        "s_matching_bonus",
        "マッチングボーナス（検索）",
        "bonus_search",
        ("s_matching_bonus",),
    ),
    MenuFeature("s_month_title", "月タイトル（検索）", "bonus_search", ("s_month_title",)),
    MenuFeature("s_title_bonus", "タイトルボーナス（検索）", "bonus_search", ("s_title_bonus",)),
    MenuFeature(
        "s_title_diff_bonus",
        "タイトル差額ボーナス（検索）",
        "bonus_search",
        ("s_title_diff_bonus",),
    ),
    MenuFeature(
        "s_repurchase_over_bonus",
        "再購入オーバーボーナス（検索）",
        "bonus_search",
        ("s_repurchase_over_bonus",),
    ),
    MenuFeature(
        "s_three_star_global_bonus",
        "3スターダイヤグローバル配当（検索）",
        "bonus_search",
        ("s_three_star_global_bonus",),
    ),
    # --- ボーナス検索（合計） ---
    MenuFeature("s_week_bonus", "週間ボーナス（検索）", "bonus_search", ("s_week_bonus",)),
    MenuFeature("s_month_bonus", "月間ボーナス（検索）", "bonus_search", ("s_month_bonus",)),
    # --- ボーナス計算（個人） ---
    MenuFeature("drive_bonus", "ドライブボーナス（計算）", "bonus_calc", ("drive_bonus",)),
    MenuFeature("basic_bonus", "ベーシックボーナス（計算）", "bonus_calc", ("basic_bonus",)),
    MenuFeature("matching_bonus", "マッチングボーナス（計算）", "bonus_calc", ("matching_bonus",)),
    MenuFeature("title_bonus", "タイトルボーナス（計算）", "bonus_calc", ("title_bonus",)),
    MenuFeature(
        "title_diff_bonus",
        "タイトル差額ボーナス（計算）",
        "bonus_calc",
        ("title_diff_bonus",),
    ),
    MenuFeature(
        "repurchase_over_bonus",
        "再購入オーバーボーナス（計算）",
        "bonus_calc",
        ("repurchase_over_bonus",),
    ),
    MenuFeature(
        "three_star_global_bonus",
        "3スターダイヤグローバル配当（計算）",
        "bonus_calc",
        ("three_star_global_bonus",),
    ),
    # --- ボーナス計算（合計・履歴） ---
    MenuFeature("week_bonus", "週間ボーナス（計算）", "bonus_calc", ("week_bonus",)),
    MenuFeature("month_title", "月タイトル（計算）", "bonus_calc", ("month_title",)),
    MenuFeature("month_bonus", "月間ボーナス（計算）", "bonus_calc", ("month_bonus",)),
    MenuFeature("bonus_histry", "個人実績の登録履歴", "bonus_calc", ("bonus_histry", "bonus_histry_month")),
    # --- 業務検索 ---
    MenuFeature(
        "business_personal_performance",
        "月別 個人業績",
        "business_search",
        ("business_personal_performance",),
    ),
    MenuFeature(
        "business_team_performance",
        "月別 チーム業績",
        "business_search",
        ("business_team_performance",),
    ),
    MenuFeature(
        "business_personal_week_performance",
        "週別 個人業績",
        "business_search",
        ("business_personal_week_performance",),
    ),
    MenuFeature(
        "business_team_week_performance",
        "週別 チーム業績",
        "business_search",
        ("business_team_week_performance",),
    ),
    MenuFeature(
        "business_carry_over_performance",
        "繰り越し業績照会",
        "business_search",
        ("business_carry_over_performance",),
    ),
    # --- 設定・マスタ ---
    MenuFeature("kibetu", "期別（週）", "settings", ("kibetu",)),
    MenuFeature("kibetu_month", "期別（月）", "settings", ("kibetu_month",)),
    MenuFeature("settings", "設定", "settings", ("settings",)),
    MenuFeature("help_text", "ヘルプテキスト", "settings", ("help_text",)),
    MenuFeature("user_target_rank", "ユーザーランク（指定月）", "settings", ("user_target_rank",)),
    MenuFeature("title_list", "タイトル表", "settings", ("title_list",)),
    MenuFeature("active_users", "アクティブ会員登録", "settings", ("active_users",)),
    MenuFeature("title_registration", "タイトルユーザー登録", "settings", ("title_registration",)),
    MenuFeature("placement_tree", "上位者ツリー", "settings", ("placement_tree",)),
)

MENU_BY_KEY = {feature.key: feature for feature in MENU_FEATURES}

URL_NAME_TO_MENU_KEY = {}
for _feature in MENU_FEATURES:
    for _url_name in _feature.url_names:
        URL_NAME_TO_MENU_KEY[_url_name] = _feature.key

# export 等は親画面の権限に紐づける
URL_NAME_TO_MENU_KEY["repurchase_export"] = "repurchase_list"

ALL_MENU_KEYS = tuple(feature.key for feature in MENU_FEATURES)

GROUP_MENU_KEYS = {
    group_id: tuple(f.key for f in MENU_FEATURES if f.group == group_id)
    for group_id, _ in MENU_GROUPS
}

NAV_GROUP_MAP = {
    "users": "users",
    "orders": "orders",
    "bonus_search": "bonus_search",
    "bonus_calc": "bonus_calc",
    "business_search": "business_search",
    "settings": "settings",
}


def menu_choices_for_admin():
    choices = []
    group_labels = dict(MENU_GROUPS)
    for feature in MENU_FEATURES:
        prefix = group_labels.get(feature.group, feature.group)
        choices.append((feature.key, f"[{prefix}] {feature.label}"))
    return choices


def menu_key_for_url_name(url_name):
    if not url_name:
        return None
    return URL_NAME_TO_MENU_KEY.get(url_name)


def nav_group_for_url_name(url_name):
    menu_key = menu_key_for_url_name(url_name)
    if not menu_key:
        return None
    feature = MENU_BY_KEY.get(menu_key)
    return feature.group if feature else None


BONUS_TOTAL_URL_NAMES = frozenset({
    "s_week_bonus",
    "s_month_bonus",
    "week_bonus",
    "month_bonus",
    "bonus_histry",
    "bonus_histry_month",
})


def bonus_nav_section(url_name):
    if not url_name:
        return None
    if url_name in BONUS_TOTAL_URL_NAMES:
        return "total"
    menu_key = menu_key_for_url_name(url_name)
    if not menu_key:
        return None
    feature = MENU_BY_KEY.get(menu_key)
    if feature and feature.group in ("bonus_search", "bonus_calc"):
        return "individual"
    return None
