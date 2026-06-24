
USERS_TARGET_RANK_INSERT_SQL = """
INSERT INTO bonus_db.users_target_rank
(
  `jmoa_code`,
  `introducer_code`,
  `placement_code`,
  `group_code`,
  `send_bv_name`,
  `status_code`,
  `rank`,
  `salon_administrator`,
  `salon_name`,
  `interim_at`,
  `activated_at`,
  `created_at`,
  `target_rank`,
  `max_up_at`,
  `new_rank`
)
SELECT
  t.jmoa_code,
  t.introducer_code,
  t.placement_code,
  t.group_code,
  t.send_bv_name,
  t.status_code,
  t.`rank`,
  t.salon_administrator,
  t.salon_name,
  t.interim_at,
  t.activated_at,
  t.created_at,

  CASE
    WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
    ELSE NULL
  END AS target_rank,

  x.created_at AS max_up_at,

  CASE
    WHEN t.status_code <> 1 THEN 9
    WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
    ELSE t.`rank`
  END AS new_rank

FROM bonus_db.users t
LEFT JOIN (
  SELECT user_id, fluctuation_name, created_at
  FROM (
    SELECT
      user_id,
      fluctuation_name,
      created_at,
      id,
      ROW_NUMBER() OVER (
        PARTITION BY user_id
        ORDER BY created_at DESC, id DESC
      ) AS rn
    FROM bonus_db.users_rank_up_history
    WHERE created_at <= %s
  ) r
  WHERE rn = 1
) x
  ON t.jmoa_code = x.user_id
"""


## ベーシックボーナス
def get_basic_bonus_insert_data(selected_kibetu, rows):

    insert_sql = """
        INSERT INTO bonus_db.B_basic_bonus_result (
            kibetu,
            placement_code,
            placement_name,
            placement_rank,
            line_code,
            purchaser_code,
            purchaser_name,
            sum_bv,
            bonus_rate,
            bonus_amount,
            blue_daiya_flg,
            created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
        )
        ON DUPLICATE KEY UPDATE
            placement_name = VALUES(placement_name),
            placement_rank = VALUES(placement_rank),
            purchaser_name = VALUES(purchaser_name),
            sum_bv = VALUES(sum_bv),
            bonus_rate = VALUES(bonus_rate),
            bonus_amount = VALUES(bonus_amount),
            blue_daiya_flg = VALUES(blue_daiya_flg),
            created_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
    """

    insert_params = []

    for r in rows:
        insert_params.append([
            selected_kibetu,
            r.get("上位者コード") or "",
            r.get("上位者名") or "",
            r.get("上位者ランク") or 0,
            r.get("line_code") or "",
            r.get("購入者コード") or "",
            r.get("購入者名") or "",
            r.get("sum_bv") or 0,
            r.get("bonus_rate") or 0,
            r.get("bonus_amount") or 0,
            r.get("blue_daiya_flg") or 0,
        ])

    return insert_sql, insert_params


## タイトルボーナス
def get_title_bonus_insert_data(selected_kibetu, rows):

    insert_sql = """
        INSERT INTO bonus_db.B_title_bonus_result (
            kibetu,
            root_jwoa_code,
            root_name,
            up_jwoa_code,
            down_jwoa_code,
            down_name,
            tree_level,
            match_level,
            title_id,
            sum_bv,
            rate,
            bonus_amount,
            created_at,
            updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo'),
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
        )
        ON DUPLICATE KEY UPDATE
            root_name = VALUES(root_name),
            up_jwoa_code = VALUES(up_jwoa_code),
            down_name = VALUES(down_name),
            tree_level = VALUES(tree_level),
            match_level = VALUES(match_level),
            title_id = VALUES(title_id),
            sum_bv = VALUES(sum_bv),
            rate = VALUES(rate),
            bonus_amount = VALUES(bonus_amount),
            updated_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
    """

    insert_params = []

    for r in rows:
        insert_params.append([
            selected_kibetu,
            r.get("root_jmoa_code") or "",
            r.get("root_name") or "",
            r.get("up_jwoa_code") or "",
            r.get("down_jwoa_code") or "",
            r.get("down_name") or "",
            r.get("tree_level") or 0,
            r.get("match_level") or 0,
            r.get("title_id") or 0,
            r.get("sum_bv") or 0,
            r.get("rate") or 0,
            r.get("bonus_amount") or 0,
        ])

    return insert_sql, insert_params

## 月タイトル
def get_month_title_delete_insert_data(selected_kibetu, rows):
    delete_sql = """
        DELETE FROM bonus_db.month_title
        WHERE kibetu = %s
    """

    insert_sql = """
        INSERT INTO bonus_db.month_title (
            kibetu,
            jwoa_code,
            jwoa_name,
            income_line_bv,
            basic_line_bv,
            title_id
        ) VALUES (
            %s, %s, %s, %s, %s, %s
        )
    """

    insert_params = []

    for r in rows:
        insert_params.append([
            selected_kibetu,
            r.get("jwoa_code") or "",
            r.get("jwoa_name") or "",
            r.get("income_line_bv") or 0,
            r.get("basic_line_bv") or 0,
            r.get("title_id") or 0,
        ])

    return delete_sql, [selected_kibetu], insert_sql, insert_params


## basic_bv_line
## 繰り越しBV
def get_basic_bv_line_insert_data(selected_kibetu, rows):

    insert_sql = """
        INSERT INTO bonus_db.basic_bv_line (
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

    insert_params = []

    for r in rows:
        insert_params.append([
            r.get("placement_code") or "",
            r.get("jmoa_code") or "",
            r.get("bv") or 0,
            r.get("carry_over_bv") or 0,
            selected_kibetu,
        ])

    return insert_sql, insert_params


def get_basic_bonus_delete_insert_data(selected_kibetu, bonus_rows, bv_line_rows):
    delete_bonus_result_sql = """
        DELETE FROM bonus_db.B_basic_bonus_result
        WHERE kibetu = %s
    """
    delete_bv_line_sql = """
        DELETE FROM bonus_db.basic_bv_line
        WHERE kibetu = %s
    """
    bonus_insert_sql, bonus_insert_params = get_basic_bonus_insert_data(
        selected_kibetu,
        bonus_rows,
    )
    bv_line_insert_sql, bv_line_insert_params = get_basic_bv_line_insert_data(
        selected_kibetu,
        bv_line_rows,
    )
    return (
        delete_bonus_result_sql,
        delete_bv_line_sql,
        [selected_kibetu],
        bonus_insert_sql,
        bonus_insert_params,
        bv_line_insert_sql,
        bv_line_insert_params,
    )


## タイトル差額ボーナス
def get_title_diff_bonus_insert_data(selected_kibetu, rows):

    insert_sql = """
        INSERT INTO bonus_db.B_title_diff_bonus_result (
            kibetu,
            root_title_id,
            root_bonus_rate,
            root_jwoa_code,
            root_name,
            up_title_id,
            up_bonus_rate,
            up_jwoa_code,
            up_jwoa_name,
            down_title_id,
            down_bonus_rate,
            down_jwoa_code,
            down_name,
            pay_bonus_rate,
            tree_level,
            sum_bv,
            title_diff_bonus
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            root_title_id = VALUES(root_title_id),
            root_bonus_rate = VALUES(root_bonus_rate),
            root_name = VALUES(root_name),
            up_title_id = VALUES(up_title_id),
            up_bonus_rate = VALUES(up_bonus_rate),
            up_jwoa_name = VALUES(up_jwoa_name),
            down_title_id = VALUES(down_title_id),
            down_bonus_rate = VALUES(down_bonus_rate),
            down_name = VALUES(down_name),
            pay_bonus_rate = VALUES(pay_bonus_rate),
            tree_level = VALUES(tree_level),
            sum_bv = VALUES(sum_bv),
            title_diff_bonus = VALUES(title_diff_bonus),
            updated_at = CURRENT_TIMESTAMP
    """

    insert_params = []

    for r in rows:
        insert_params.append([
            selected_kibetu,

            r.get("root_title_id") or 0,
            r.get("root_bonus_rate") or 0,
            r.get("root_jwoa_code") or "",
            r.get("root_name") or "",

            r.get("up_title_id") or 0,
            r.get("up_bonus_rate") or 0,
            r.get("up_jwoa_code") or "",
            r.get("up_jwoa_name") or "",

            r.get("down_title_id") or 0,
            r.get("down_bonus_rate") or 0,
            r.get("down_jwoa_code") or "",
            r.get("down_name") or "",

            r.get("pay_bonus_rate") or 0,
            r.get("tree_level") or 0,
            r.get("sum_bv") or 0,
            r.get("title_diff_bonus") or 0,
        ])

    return insert_sql, insert_params

## 再購入オーバーボーナス
def get_repurchase_over_bonus_insert_data(selected_kibetu, rows):

    insert_sql = """
        INSERT INTO bonus_db.B_repurchase_over_bonus_result (
            kibetu,
            root_code,
            root_name,
            up_code,
            up_name,
            down_code,
            down_name,
            tree_level,
            match_count,
            rate,
            sum_bv,
            over_bonus
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        )
        ON DUPLICATE KEY UPDATE
            root_name = VALUES(root_name),
            up_code = VALUES(up_code),
            up_name = VALUES(up_name),
            down_name = VALUES(down_name),
            tree_level = VALUES(tree_level),
            match_count = VALUES(match_count),
            rate = VALUES(rate),
            sum_bv = VALUES(sum_bv),
            over_bonus = VALUES(over_bonus),
            updated_at = CURRENT_TIMESTAMP
    """

    insert_params = []

    for r in rows:
        insert_params.append([
            selected_kibetu,
            r.get("root_code"),
            r.get("root_name"),
            r.get("up_code"),
            r.get("up_name"),
            r.get("down_code"),
            r.get("down_name"),
            r.get("tree_level"),
            r.get("match_count"),
            r.get("rate"),
            r.get("sum_bv"),
            r.get("over_bonus"),
        ])

    return insert_sql, insert_params

## 3スターダイヤグローバル配当
def get_three_star_global_bonus_insert_data(selected_kibetu, rows):

    insert_sql = """
        INSERT INTO bonus_db.B_three_star_global_bonus_result (
            kibetu,
            jwoa_code,
            jwoa_name,
            title_id,
            score,
            total_over_bv,
            one_score_bonus,
            bonus_amount,
            created_at,
            updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo'),
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
        )
        ON DUPLICATE KEY UPDATE
            jwoa_name = VALUES(jwoa_name),
            title_id = VALUES(title_id),
            score = VALUES(score),
            total_over_bv = VALUES(total_over_bv),
            one_score_bonus = VALUES(one_score_bonus),
            bonus_amount = VALUES(bonus_amount),
            updated_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
    """

    insert_params = []

    for r in rows:
        insert_params.append([
            selected_kibetu,
            r.get("jwoa_code") or "",
            r.get("jwoa_name") or "",
            r.get("title_id") or 0,
            r.get("score") or 0,
            r.get("total_over_bv") or 0,
            r.get("one_score_bonus") or 0,
            r.get("bonus_amount") or 0,
        ])

    return insert_sql, insert_params


def get_week_team_performance_insert_data(selected_kibetu, rows):
    insert_sql = """
        INSERT INTO bonus_db.B_team_business_search_result (
            kibetu,
            period_type,
            upper_code,
            line_code,
            purchaser_code,
            purchaser_name,
            lvl,
            sum_bv,
            created_at,
            updated_at
        ) VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo'),
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
        )
    """

    insert_params = []
    for row in rows:
        insert_params.append([
            selected_kibetu,
            "weekly",
            row.get("upper_code") or "",
            row.get("line_code") or "",
            row.get("purchaser_code") or "",
            row.get("purchaser_name") or "",
            row.get("lvl") or 0,
            row.get("sum_bv") or 0,
        ])

    return insert_sql, insert_params


def get_month_team_performance_insert_data(selected_kibetu, rows):
    insert_sql = """
        INSERT INTO bonus_db.B_team_business_search_result (
            kibetu,
            period_type,
            upper_code,
            line_code,
            purchaser_code,
            purchaser_name,
            lvl,
            sum_bv,
            created_at,
            updated_at
        ) VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo'),
            CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
        )
    """

    insert_params = []
    for row in rows:
        insert_params.append([
            selected_kibetu,
            "monthly",
            row.get("upper_code") or "",
            row.get("line_code") or "",
            row.get("purchaser_code") or "",
            row.get("purchaser_name") or "",
            row.get("lvl") or 0,
            row.get("sum_bv") or 0,
        ])

    return insert_sql, insert_params