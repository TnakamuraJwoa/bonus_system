DRIVE_BONUS_SQL = """
WITH RECURSIVE

-- user + active + title 情報
users_target_rank_add_activeUser AS (
    SELECT
        a.*,
        CASE
            WHEN b.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS is_active,
        IFNULL(ut.title_id, 0) AS title_id,
        tm.title_name
    FROM bonus_db.users_target_rank AS a
    LEFT JOIN (
        SELECT DISTINCT
            jwoa_code
        FROM bonus_db.active_users
        WHERE year = %s
          AND month = %s
          AND active_status = 1
    ) AS b
        ON a.jmoa_code = b.jwoa_code
    LEFT JOIN bonus_db.user_titles AS ut
        ON a.jmoa_code = ut.jmoa_code
    LEFT JOIN bonus_db.title_master AS tm
        ON ut.title_id = tm.title_id
),

-- ① 再購入データ
repurchase_list AS (
    SELECT
        order_code,
        jwoa_code,
        bonus_payment_date,
        order_type,
        bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (101, 105)
      AND bonus_payment_date >= %s
      AND bonus_payment_date <  %s
),

-- 再購入は最大50BV
dis_repurchase_list AS (
    SELECT
        jwoa_code,
        LEAST(IFNULL(SUM(bv), 0), 50) AS custom_bv
    FROM repurchase_list
    GROUP BY jwoa_code
),

-- ② 初回購入、ランクアップデータ
rank_up_list AS (
    SELECT
        order_code,
        jwoa_code,
        bonus_payment_date,
        order_type,
        bv,
        IFNULL(bv, 0) AS custom_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (102, 103)
      AND bonus_payment_date >= %s
      AND bonus_payment_date <  %s
),

-- ① 再購入 + ② 初回購入、ランクアップ対象者
purchasers_list AS (
    SELECT
        jwoa_code
    FROM dis_repurchase_list

    UNION

    SELECT
        jwoa_code
    FROM rank_up_list
),

-- 前月再購入
prev_purchasers_list AS (
    SELECT
        p.jwoa_code,
        SUM(IFNULL(p.bv, 0)) AS bv
    FROM bonus_db.purchase_info_list AS p
    WHERE p.bonus_payment_date >= %s
      AND p.bonus_payment_date < %s
    GROUP BY p.jwoa_code
    HAVING SUM(IFNULL(p.bv, 0)) >= 50
),

-- 前月時点のランク
rankup_history AS (
    SELECT
        *
    FROM (
        SELECT
            t.*,
            ROW_NUMBER() OVER (
                PARTITION BY user_id
                ORDER BY fluctuation_up_at DESC
            ) AS rn
        FROM bonus_db.users_rank_up_history AS t
        WHERE fluctuation_up_at < %s
    ) AS x
    WHERE rn = 1
),

-- 購入対象ユーザー
user_in_purchasers_list AS (
    SELECT
        u.*
    FROM bonus_db.users_target_rank AS u
    JOIN purchasers_list AS p
        ON p.jwoa_code = u.jmoa_code
),

chain AS (
    SELECT
        u.jmoa_code,
        u.new_rank AS jmoa_rank,
        u.introducer_code AS current_code,
        1 AS lvl
    FROM user_in_purchasers_list AS u

    UNION ALL

    SELECT
        c.jmoa_code,
        c.jmoa_rank,
        up.introducer_code AS current_code,
        c.lvl + 1 AS lvl
    FROM chain AS c
    JOIN users_target_rank_add_activeUser AS up
        ON up.jmoa_code = c.current_code
    WHERE c.current_code IS NOT NULL
      AND (up.is_active = 1 OR up.new_rank = 9)
      AND c.lvl < 100
),

last_step AS (
    SELECT
        c.jmoa_code,
        MAX(c.lvl) AS max_lvl
    FROM chain AS c
    GROUP BY c.jmoa_code
),

user_in_purchasers_list_non9 AS (
    SELECT
        c.current_code AS introducer_code,
        u2.new_rank AS introducer_rank,
        c.jmoa_code,
        c.jmoa_rank,
        c.lvl
    FROM chain AS c
    JOIN last_step AS s
        ON s.jmoa_code = c.jmoa_code
       AND s.max_lvl = c.lvl
    LEFT JOIN bonus_db.users_target_rank AS u2
        ON u2.jmoa_code = c.current_code
),

user_in_purchasers_list_non9_addTitle AS (
    SELECT
        non9.introducer_code,
        non9.introducer_rank,
        non9.jmoa_code,
        u.send_bv_name,
        non9.jmoa_rank,
        non9.lvl,
        tm.title_id AS introducer_title_id,
        tm.title_name AS introducer_title_name
    FROM user_in_purchasers_list_non9 AS non9
    LEFT JOIN bonus_db.users_target_rank AS ui
        ON non9.introducer_code = ui.jmoa_code
    LEFT JOIN bonus_db.user_titles AS ut
        ON ut.jmoa_code = ui.jmoa_code
    LEFT JOIN bonus_db.title_master AS tm
        ON ut.title_id = tm.title_id
    LEFT JOIN bonus_db.users_target_rank AS u
        ON non9.jmoa_code = u.jmoa_code
),

-- 初回購入・ランクアップ用の紹介者検索
rank_chain_find AS (
    SELECT
        up.title_name,
        up.title_id,
        u.introducer_code,
        r.jwoa_code,
        u.send_bv_name AS jwoa_name,
        r.custom_bv,
        1 AS lvl,
        CASE
            WHEN up.is_active = 1
              OR up.new_rank <> 9
                THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM rank_up_list AS r
    JOIN users_target_rank_add_activeUser AS u
        ON u.jmoa_code = r.jwoa_code
    LEFT JOIN users_target_rank_add_activeUser AS up
        ON up.jmoa_code = u.introducer_code

    UNION ALL

    SELECT
        up.title_name,
        up.title_id,
        c.next_code AS introducer_code,
        c.jwoa_code,
        c.jwoa_name,
        c.custom_bv,
        c.lvl + 1 AS lvl,
        CASE
            WHEN up.is_active = 1
              OR up.new_rank <> 9
                THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM rank_chain_find AS c
    JOIN users_target_rank_add_activeUser AS up
        ON up.jmoa_code = c.next_code
    WHERE c.next_code IS NOT NULL
      AND c.found = 0
      AND c.lvl < 100
),

rank_first_found AS (
    SELECT
        jwoa_code,
        MIN(lvl) AS hit_lvl
    FROM rank_chain_find
    WHERE found = 1
    GROUP BY jwoa_code
),

-- 初回購入・ランクアップ分
rank_up_add_non9_addTitle AS (
    SELECT
        c.title_name,
        c.introducer_code,
        c.jwoa_code,
        c.jwoa_name,
        c.custom_bv,

        CASE
            WHEN c.title_id >= 4 THEN 0.20
            WHEN c.title_id = 3 THEN 0.15
            ELSE 0.10
        END AS rate,

        CASE
            WHEN c.title_id >= 4
                THEN TRUNCATE(COALESCE(c.custom_bv, 0) * 0.20, 2)

            WHEN c.title_id = 3
                THEN TRUNCATE(COALESCE(c.custom_bv, 0) * 0.15, 2)

            ELSE
                TRUNCATE(COALESCE(c.custom_bv, 0) * 0.10, 2)
        END AS bonus_amount

    FROM rank_chain_find AS c
    JOIN rank_first_found AS f
        ON f.jwoa_code = c.jwoa_code
       AND f.hit_lvl = c.lvl
    WHERE c.found = 1
),

-- 再購入用の紹介者検索
chain_find AS (
    SELECT
        u.jmoa_code,
        u.new_rank AS jmoa_rank,
        u.introducer_code AS evaluated_code,
        1 AS lvl,
        CASE
            WHEN up.is_active = 1
              OR (
                    up.new_rank <> 9
                    AND IFNULL(p.bv, 0) >= 50
                 )
                THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM user_in_purchasers_list AS u
    LEFT JOIN users_target_rank_add_activeUser AS up
        ON up.jmoa_code = u.introducer_code
    LEFT JOIN prev_purchasers_list AS p
        ON p.jwoa_code = up.jmoa_code

    UNION ALL

    SELECT
        c.jmoa_code,
        c.jmoa_rank,
        c.next_code AS evaluated_code,
        c.lvl + 1 AS lvl,
        CASE
            WHEN up.is_active = 1
              OR (
                    up.new_rank <> 9
                    AND IFNULL(p.bv, 0) >= 50
                 )
                THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM chain_find AS c
    JOIN users_target_rank_add_activeUser AS up
        ON up.jmoa_code = c.next_code
    LEFT JOIN prev_purchasers_list AS p
        ON p.jwoa_code = up.jmoa_code
    WHERE c.next_code IS NOT NULL
      AND c.found = 0
      AND c.lvl < 100
),

first_found AS (
    SELECT
        jmoa_code,
        MIN(lvl) AS hit_lvl
    FROM chain_find
    WHERE found = 1
    GROUP BY jmoa_code
),

user_in_purchasers_list_non9_2 AS (
    SELECT
        c.evaluated_code AS introducer_code,
        u.new_rank AS introducer_rank,
        c.jmoa_code,
        c.jmoa_rank,
        c.lvl
    FROM chain_find AS c
    JOIN first_found AS f
        ON f.jmoa_code = c.jmoa_code
       AND f.hit_lvl = c.lvl
    JOIN bonus_db.users_target_rank AS u
        ON u.jmoa_code = c.evaluated_code
    WHERE c.found = 1
),

user_in_purchasers_list_non9_2_addTitle AS (
    SELECT
        non9.introducer_code,
        non9.introducer_rank,
        non9.jmoa_code,
        u.send_bv_name,
        non9.jmoa_rank,
        non9.lvl,
        tm.title_id AS introducer_title_id,
        tm.title_name AS introducer_title_name
    FROM user_in_purchasers_list_non9_2 AS non9
    LEFT JOIN bonus_db.users_target_rank AS ui
        ON non9.introducer_code = ui.jmoa_code
    LEFT JOIN bonus_db.user_titles AS ut
        ON ut.jmoa_code = ui.jmoa_code
    LEFT JOIN bonus_db.title_master AS tm
        ON ut.title_id = tm.title_id
    LEFT JOIN bonus_db.users_target_rank AS u
        ON non9.jmoa_code = u.jmoa_code
),

-- 再購入分
repurchase_add_non9_2_addTitle AS (
    SELECT
        non9.introducer_title_name AS title_name,
        non9.introducer_code,
        non9.jmoa_code AS jwoa_code,
        non9.send_bv_name AS jwoa_name,
        repurchase.custom_bv,

        CASE
            WHEN non9.introducer_title_id >= 4 THEN 0.20
            WHEN non9.introducer_title_id = 3 THEN 0.15
            ELSE 0.10
        END AS rate,

        CASE
            WHEN non9.introducer_title_id >= 4
                THEN TRUNCATE(
                    COALESCE(repurchase.custom_bv, 0) * 0.20,
                    2
                )

            WHEN non9.introducer_title_id = 3
                THEN TRUNCATE(
                    COALESCE(repurchase.custom_bv, 0) * 0.15,
                    2
                )

            ELSE
                TRUNCATE(
                    COALESCE(repurchase.custom_bv, 0) * 0.10,
                    2
                )
        END AS bonus_amount

    FROM dis_repurchase_list AS repurchase
    LEFT JOIN user_in_purchasers_list_non9_2_addTitle AS non9
        ON repurchase.jwoa_code = non9.jmoa_code
    WHERE repurchase.custom_bv > 0
),

-- 初回購入・ランクアップ分と再購入分を結合
pay_drive_list AS (
    SELECT
        title_name,
        introducer_code,
        jwoa_code,
        jwoa_name,
        custom_bv,
        rate,
        bonus_amount
    FROM rank_up_add_non9_addTitle

    UNION ALL

    SELECT
        title_name,
        introducer_code,
        jwoa_code,
        jwoa_name,
        custom_bv,
        rate,
        bonus_amount
    FROM repurchase_add_non9_2_addTitle
),

-- 会員単位で集計
pay_drive_list_group_by AS (
    SELECT
        title_name,
        introducer_code,
        jwoa_code,
        jwoa_name,
        rate,
        SUM(custom_bv) AS sum_bv,
        SUM(bonus_amount) AS sum_bonus_amount
    FROM pay_drive_list
    GROUP BY
        title_name,
        introducer_code,
        jwoa_code,
        jwoa_name,
        rate
)

SELECT
    title_name,
    introducer_code,
    jwoa_code,
    jwoa_name,
    rate,
    sum_bv,
    sum_bonus_amount
FROM pay_drive_list_group_by
WHERE jwoa_code IS NOT NULL
ORDER BY
    introducer_code,
    jwoa_code
"""