MATCHING_BONUS_DETAIL_SQL = """
WITH RECURSIVE

sum_prev_purchasers_list AS (
    SELECT
        p.jwoa_code,
        SUM(IFNULL(p.bv, 0)) AS bv
    FROM bonus_db.purchase_info_list p
    WHERE p.bonus_payment_date >= %s
      AND p.bonus_payment_date <  %s
    GROUP BY p.jwoa_code
    HAVING SUM(IFNULL(p.bv, 0)) >= 50
),

active_users AS (
    SELECT jwoa_code
    FROM bonus_db.active_users
    WHERE active_status = 1
    UNION
    SELECT jwoa_code
    FROM sum_prev_purchasers_list
),

basic_bonus_member AS (
    SELECT
        placement_code AS member_code,
        MAX(placement_name) AS member_name,
        SUM(CASE WHEN bonus_amount > 0 THEN bonus_amount ELSE 0 END) AS basic_bonus_amount,
        SUM(CASE WHEN bonus_amount > 0 THEN 1 ELSE 0 END) AS positive_row_count
    FROM bonus_db.B_basic_bonus_result
    WHERE kibetu = %s
    GROUP BY placement_code
),

basic_paid_list AS (
    SELECT
        member_code,
        member_name,
        basic_bonus_amount
    FROM basic_bonus_member
    WHERE basic_bonus_amount > 0
),

member_with_introducer AS (
    SELECT
        b.member_code,
        COALESCE(u.send_bv_name, b.member_name) AS member_name,
        b.basic_bonus_amount,
        CASE WHEN b.basic_bonus_amount > 0 THEN 1 ELSE 0 END AS basic_acquired_flg,
        u.introducer_code,
        intro.send_bv_name AS introducer_name,
        IFNULL(parent_basic.basic_bonus_amount, 0) AS introducer_basic_bonus_amount,
        CASE WHEN IFNULL(parent_basic.basic_bonus_amount, 0) > 0 THEN 1 ELSE 0 END AS introducer_basic_acquired_flg
    FROM basic_bonus_member AS b
    LEFT JOIN bonus_db.users AS u
        ON b.member_code = u.jmoa_code
    LEFT JOIN bonus_db.users AS intro
        ON u.introducer_code = intro.jmoa_code
    LEFT JOIN basic_paid_list AS parent_basic
        ON u.introducer_code = parent_basic.member_code
),

matching_root_list AS (
    SELECT DISTINCT
        introducer_code AS root_introducer_code
    FROM member_with_introducer
    WHERE introducer_code IS NOT NULL
      AND basic_acquired_flg = 1
      AND introducer_basic_acquired_flg = 1
),

matching_active_cnt AS (
    SELECT
        r.root_introducer_code,
        COUNT(DISTINCT child.jmoa_code) AS active_count
    FROM matching_root_list AS r
    LEFT JOIN bonus_db.users AS child
        ON r.root_introducer_code = child.introducer_code
    INNER JOIN active_users AS au
        ON au.jwoa_code = child.jmoa_code
    GROUP BY r.root_introducer_code
),

introducer_downline_tree AS (
    SELECT
        r.root_introducer_code,
        u.jmoa_code,
        u.placement_code,
        0 AS tree_level,
        CASE
            WHEN bp.member_code IS NOT NULL THEN 1
            ELSE NULL
        END AS matching_level
    FROM matching_root_list AS r
    INNER JOIN bonus_db.users AS u
        ON u.jmoa_code = r.root_introducer_code
    LEFT JOIN basic_paid_list AS bp
        ON bp.member_code = u.jmoa_code

    UNION ALL

    SELECT
        t.root_introducer_code,
        u.jmoa_code,
        u.placement_code,
        t.tree_level + 1 AS tree_level,
        CASE
            WHEN bp.member_code IS NOT NULL THEN COALESCE(t.matching_level, 0) + 1
            ELSE NULL
        END AS matching_level
    FROM introducer_downline_tree AS t
    INNER JOIN bonus_db.users AS u
        ON u.placement_code = t.jmoa_code
    LEFT JOIN basic_paid_list AS bp
        ON bp.member_code = u.jmoa_code
),

detail_with_level AS (
    SELECT
        m.*,
        t.tree_level,
        t.matching_level,
        IFNULL(ac.active_count, 0) AS active_count,
        CASE
            WHEN IFNULL(ac.active_count, 0) >= 3 THEN 3
            ELSE IFNULL(ac.active_count, 0)
        END AS payable_level_limit
    FROM member_with_introducer AS m
    LEFT JOIN introducer_downline_tree AS t
        ON m.introducer_code = t.root_introducer_code
       AND m.member_code = t.jmoa_code
    LEFT JOIN matching_active_cnt AS ac
        ON m.introducer_code = ac.root_introducer_code
)

SELECT
    %s AS kibetu,
    member_code,
    member_name,
    basic_acquired_flg,
    basic_bonus_amount,
    introducer_code,
    introducer_name,
    introducer_basic_acquired_flg,
    introducer_basic_bonus_amount,
    active_count,
    tree_level,
    matching_level,
    payable_level_limit,
    CASE
        WHEN basic_acquired_flg = 0 THEN 0
        WHEN introducer_code IS NULL OR introducer_code = '' THEN 0
        WHEN introducer_basic_acquired_flg = 0 THEN 0
        WHEN matching_level IS NULL THEN 0
        WHEN matching_level > payable_level_limit THEN 0
        ELSE 1
    END AS payable_flg,
    CASE
        WHEN basic_acquired_flg = 0 THEN 'ベーシック未取得'
        WHEN introducer_code IS NULL OR introducer_code = '' THEN '直紹介者なし'
        WHEN introducer_basic_acquired_flg = 0 THEN '直紹介者ベーシック未取得'
        WHEN matching_level IS NULL THEN '配置ツリー上の対象外'
        WHEN matching_level > payable_level_limit THEN '段数上限超過'
        ELSE '支払対象'
    END AS status_reason,
    CASE
        WHEN matching_level IS NOT NULL
         AND matching_level <= payable_level_limit
         AND basic_acquired_flg = 1
         AND introducer_basic_acquired_flg = 1
        THEN TRUNCATE(basic_bonus_amount * 0.10, 2)
        ELSE 0
    END AS matching_bonus_amount
FROM detail_with_level
"""
