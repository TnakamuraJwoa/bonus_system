BASIC_INCOME_LINE_DETAIL_CTE_SQL = """
WITH RECURSIVE

selected_kibetu AS (
    SELECT %s AS kibetu
),

-- 前週の期別
prev_kibetu AS (
    SELECT prev_kibetu
    FROM (
        SELECT
            kibetu,
            LAG(kibetu) OVER (ORDER BY st_date) AS prev_kibetu
        FROM bonus_db.period_master
    ) t
    WHERE kibetu = (SELECT kibetu FROM selected_kibetu)
),

-- アクティブ会員
is_active_users AS (
    SELECT *, 50 AS bv
    FROM bonus_db.active_users
    WHERE year = %s
      AND month = %s
      AND active_status = 1
),

-- 前週のベーシック繰り越しBV
prev_basic_carry_over_bv AS (
    SELECT
        kibetu,
        placement_code,
        jmoa_code AS jwoa_code,
        carry_over_bv
    FROM bonus_db.basic_bv_line
    WHERE kibetu = (
        SELECT prev_kibetu
        FROM prev_kibetu
    )
),

-- 前月の購入情報 + アクティブ会員50BV
sum_prev_purchasers_list AS (
    SELECT
        x.jwoa_code,
        SUM(IFNULL(x.bv, 0)) AS bv
    FROM (
        SELECT
            p.jwoa_code,
            p.bv
        FROM bonus_db.purchase_info_list p
        WHERE p.bonus_payment_date >= %s
          AND p.bonus_payment_date < %s

        UNION ALL

        SELECT
            iau.jwoa_code,
            iau.bv
        FROM is_active_users iau
    ) x
    GROUP BY x.jwoa_code
    HAVING SUM(IFNULL(x.bv, 0)) >= 50
),

-- アクティブ上位者分だけ、前回繰り越しBVを対象にする
active_prev_basic_carry_over_bv AS (
    SELECT a.*
    FROM prev_basic_carry_over_bv AS a
    JOIN sum_prev_purchasers_list AS b
      ON a.placement_code = b.jwoa_code
),

-- 再購入リスト
repurchase_list AS (
    SELECT
        order_code,
        jwoa_code,
        bonus_payment_date,
        order_type,
        bv,
        LEAST(IFNULL(bv, 0), 50) AS custom_bv
    FROM bonus_db.purchase_info_list AS p
    WHERE order_type IN (101, 105)
      AND bonus_payment_date >= %s
      AND bonus_payment_date < %s
),

-- ランクアップ、初回購入情報リスト
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
      AND bonus_payment_date < %s
),

purchase_list_union AS (
    SELECT *
    FROM repurchase_list
    WHERE custom_bv > 0

    UNION ALL

    SELECT *
    FROM rank_up_list
    WHERE custom_bv > 0
),

purchase_sum_bv AS (
    SELECT
        jwoa_code,
        SUM(custom_bv) AS sum_bv
    FROM purchase_list_union
    GROUP BY jwoa_code
),

purchase_users AS (
    SELECT DISTINCT
        jwoa_code
    FROM purchase_list_union
),

-- 購入者から上位者へTreeを上る
payer_tree AS (
    SELECT
        u.jmoa_code AS payer_code,
        u.send_bv_name AS payer_name,
        u.jmoa_code AS line_code,
        u.placement_code AS upper_code,
        0 AS lvl,
        CAST(u.jmoa_code AS CHAR(4000)) AS path_codes
    FROM bonus_db.users AS u
    JOIN purchase_users AS pu
      ON pu.jwoa_code = u.jmoa_code

    UNION ALL

    SELECT
        t.payer_code,
        t.payer_name,
        up.jmoa_code AS line_code,
        up.placement_code AS upper_code,
        t.lvl + 1 AS lvl,
        CONCAT(t.path_codes, '>', up.jmoa_code) AS path_codes
    FROM payer_tree AS t
    JOIN bonus_db.users AS up
      ON up.jmoa_code = t.upper_code
    WHERE t.lvl < 1000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
),

payer_list AS (
    SELECT
        t.payer_code AS purchaser_code,
        t.payer_name AS purchaser_name,
        t.line_code,
        t.upper_code AS placement_code,
        up.send_bv_name AS placement_name,
        t.lvl + 1 AS tree_level,
        t.path_codes
    FROM payer_tree AS t
    LEFT JOIN bonus_db.users AS up
      ON up.jmoa_code = t.upper_code
    WHERE t.upper_code IS NOT NULL
      AND t.upper_code <> ''
),

-- 支払い者のリスト in 前月アクティブ上位者
payer_list_prev_month_users AS (
    SELECT
        pl.*,
        ur.new_rank AS placement_rank,
        p_sum_bv.sum_bv
    FROM payer_list AS pl
    JOIN sum_prev_purchasers_list AS spl
      ON spl.jwoa_code = pl.placement_code
    LEFT JOIN bonus_db.users_target_rank AS ur
      ON pl.placement_code = ur.jmoa_code
    LEFT JOIN purchase_sum_bv AS p_sum_bv
      ON pl.purchaser_code = p_sum_bv.jwoa_code
),

income_detail_source AS (
    SELECT
        (SELECT kibetu FROM selected_kibetu) AS kibetu,
        placement_code,
        placement_name,
        placement_rank,
        line_code,
        purchaser_code,
        purchaser_name,
        path_codes,
        IFNULL(sum_bv, 0) AS purchase_bv,
        0 AS carry_over_bv,
        IFNULL(sum_bv, 0) AS calc_bv,
        'purchase' AS detail_type,
        '購入' AS detail_type_label,
        1 AS detail_sort
    FROM payer_list_prev_month_users

    UNION ALL

    SELECT
        (SELECT kibetu FROM selected_kibetu) AS kibetu,
        a.placement_code,
        IFNULL(u.send_bv_name, '') AS placement_name,
        ur.new_rank AS placement_rank,
        a.jwoa_code AS line_code,
        '' AS purchaser_code,
        '' AS purchaser_name,
        '' AS path_codes,
        0 AS purchase_bv,
        IFNULL(a.carry_over_bv, 0) AS carry_over_bv,
        IFNULL(a.carry_over_bv, 0) AS calc_bv,
        'carry_over' AS detail_type,
        '繰り越し' AS detail_type_label,
        2 AS detail_sort
    FROM active_prev_basic_carry_over_bv AS a
    LEFT JOIN bonus_db.users AS u
      ON u.jmoa_code = a.placement_code
    LEFT JOIN bonus_db.users_target_rank AS ur
      ON a.placement_code = ur.jmoa_code
),

line_sum AS (
    SELECT
        placement_code,
        line_code,
        SUM(calc_bv) AS line_total_bv
    FROM income_detail_source
    GROUP BY
        placement_code,
        line_code
),

-- line_rank=1 が基本ライン、line_rank=2〜5 が収入ライン
line_flg AS (
    SELECT
        a.*,
        ROW_NUMBER() OVER (
            PARTITION BY a.placement_code
            ORDER BY a.line_total_bv DESC, a.line_code
        ) AS line_rank
    FROM line_sum AS a
),

line_flg_with_cap AS (
    SELECT
        lf.*,
        CASE
            WHEN IFNULL(ur.new_rank, 0) = 1 THEN 5000
            ELSE 125000
        END AS income_line_cap,
        CASE
            WHEN lf.line_rank BETWEEN 2 AND 5 THEN
                LEAST(
                    IFNULL(lf.line_total_bv, 0),
                    CASE
                        WHEN IFNULL(ur.new_rank, 0) = 1 THEN 5000
                        ELSE 125000
                    END
                )
            ELSE IFNULL(lf.line_total_bv, 0)
        END AS capped_line_total_bv,
        CASE
            WHEN lf.line_rank BETWEEN 2 AND 5 THEN
                GREATEST(
                    IFNULL(lf.line_total_bv, 0) -
                    CASE
                        WHEN IFNULL(ur.new_rank, 0) = 1 THEN 5000
                        ELSE 125000
                    END,
                    0
                )
            ELSE 0
        END AS line_over_cap_bv
    FROM line_flg AS lf
    LEFT JOIN bonus_db.users_target_rank AS ur
      ON lf.placement_code = ur.jmoa_code
),

line_role_summary AS (
    SELECT
        placement_code,
        SUM(CASE WHEN line_rank = 1 THEN line_total_bv ELSE 0 END) AS basic_line_bv,
        SUM(CASE WHEN line_rank BETWEEN 2 AND 5 THEN capped_line_total_bv ELSE 0 END) AS income_line_bv,
        SUM(CASE WHEN line_rank BETWEEN 2 AND 5 THEN line_over_cap_bv ELSE 0 END) AS income_line_over_cap_bv
    FROM line_flg_with_cap
    GROUP BY placement_code
),

line_diff AS (
    SELECT
        placement_code,
        IFNULL(basic_line_bv, 0) AS basic_line_bv,
        IFNULL(income_line_bv, 0) AS income_line_bv,
        IFNULL(income_line_over_cap_bv, 0) AS income_line_over_cap_bv,
        GREATEST(IFNULL(basic_line_bv, 0) - IFNULL(income_line_bv, 0), 0) AS next_carry_over_bv
    FROM line_role_summary
),

income_line_detail AS (
    SELECT
        d.kibetu,
        d.placement_code,
        d.placement_name,
        d.placement_rank,
        d.line_code,
        d.purchaser_code,
        d.purchaser_name,
        d.path_codes,
        d.purchase_bv,
        d.carry_over_bv,
        d.calc_bv,
        lf.line_rank,
        CASE
            WHEN lf.line_rank = 1 THEN '基本ライン'
            ELSE '収入ライン'
        END AS line_role_label,
        lf.line_total_bv,
        lf.capped_line_total_bv,
        lf.income_line_cap,
        lf.line_over_cap_bv,
        ld.income_line_bv,
        ld.basic_line_bv,
        ld.income_line_over_cap_bv,
        ld.next_carry_over_bv,
        d.detail_type,
        d.detail_type_label,
        d.detail_sort
    FROM income_detail_source AS d
    JOIN line_flg_with_cap AS lf
      ON d.placement_code = lf.placement_code
     AND d.line_code = lf.line_code
     AND lf.line_rank BETWEEN 1 AND 5
    LEFT JOIN line_diff AS ld
      ON d.placement_code = ld.placement_code
    WHERE d.calc_bv > 0
)
"""
