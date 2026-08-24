MATCHING_BONUS_SQL = """
WITH RECURSIVE

-- group_by(購入者リスト)
-- 前月の購入情報50BV以上購入
sum_prev_purchasers_list AS (
SELECT
    p.jwoa_code,
    SUM(IFNULL(p.bv, 0)) AS bv
FROM bonus_db.purchase_info_list p
WHERE p.bonus_payment_date >= %s
  AND p.bonus_payment_date < %s
GROUP BY p.jwoa_code
HAVING SUM(IFNULL(p.bv, 0)) >= 50
),

-- アクティブuser
-- 前月50BV or active_status = 1（ただしactive_usersも前月のみ対象に絞込）
active_users as (
    select jwoa_code
    from bonus_db.active_users
    where active_status = 1
      and year = %s
      and month = %s

    union

    select jwoa_code
    from sum_prev_purchasers_list

),

-- ベーシックボーナス結果
basic_bonus_result AS (
    SELECT
     *
    FROM bonus_db.B_basic_bonus_result
    WHERE kibetu = %s
),

-- ベーシックボーナス取得者一覧
basic_id_list AS (
    SELECT
        placement_code AS get_basic_bonus_code,
        placement_name AS get_basic_bonus_name,
        SUM(bonus_amount) AS sum_bonus_amount
    FROM basic_bonus_result
    GROUP BY
        placement_code,
        placement_name
),

-- ベーシックボーナス紹介者数
basic_active_cnt AS (
    SELECT
        a.get_basic_bonus_code as introducer_code,
        COUNT(DISTINCT b.jmoa_code) AS active_count
    FROM basic_id_list AS a
    LEFT JOIN nexus_production.users AS b
        ON a.get_basic_bonus_code = b.introducer_code
    INNER JOIN active_users AS au
        ON au.jwoa_code = b.jmoa_code
    GROUP BY
        a.get_basic_bonus_code
),



-- 紹介者Treeで下にたどる
introducer_down_line_tree AS (

    -- 起点
    SELECT
        a.get_basic_bonus_code,
        a.get_basic_bonus_code as up_code,
        u.jmoa_code as down_code,

        -- ベーシックボーナスを受け取っているか判定
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM basic_id_list b
                WHERE b.get_basic_bonus_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS intro_basic_flg,

        -- 紹介者がアクティブか判定
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM active_users b
                WHERE b.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS intro_active_flg,

        -- ベーシック取得者 かつ アクティブ の場合 1
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM basic_id_list b
                WHERE b.get_basic_bonus_code = u.jmoa_code
            )
            AND EXISTS (
                SELECT 1
                FROM active_users au
                WHERE au.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS exist,

        -- ベーシック取得者 かつ アクティブ の場合
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM basic_id_list b
                WHERE b.get_basic_bonus_code = u.jmoa_code
            )
            AND EXISTS (
                SELECT 1
                FROM active_users au
                WHERE au.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS level,

        0 AS tree_level,

        IFNULL(bb.sum_bonus_amount, 0) AS basic_bonus

    FROM basic_id_list AS a

    INNER JOIN nexus_production.users AS u
        ON a.get_basic_bonus_code = u.introducer_code

    LEFT JOIN basic_id_list AS bb
        ON bb.get_basic_bonus_code = u.jmoa_code

    UNION ALL

    -- 下にたどる
    SELECT
     t.get_basic_bonus_code,
     t.down_code as up_code,
     u.jmoa_code as down_code,

        -- ベーシックボーナスを受け取っているか判定
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM basic_id_list b
                WHERE b.get_basic_bonus_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS intro_basic_flg,

        -- 紹介者がアクティブか判定
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM active_users b
                WHERE b.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS intro_active_flg,

        -- ベーシック取得者 かつ アクティブ の場合 1
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM basic_id_list b
                WHERE b.get_basic_bonus_code = u.jmoa_code
            )
            AND EXISTS (
                SELECT 1
                FROM active_users au
                WHERE au.jwoa_code = u.jmoa_code
            )
            THEN 1
            ELSE 0
        END AS exist,

        -- ベーシック取得者 かつ アクティブ の場合
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM basic_id_list b
                WHERE b.get_basic_bonus_code = u.jmoa_code
            )
            AND EXISTS (
                SELECT 1
                FROM active_users au
                WHERE au.jwoa_code = u.jmoa_code
            )
            THEN t.level + 1
            ELSE t.level
        END AS level,

        t.tree_level + 1 AS tree_level,

        IFNULL(bb.sum_bonus_amount, 0) AS basic_bonus

    from introducer_down_line_tree as t

    INNER JOIN nexus_production.users AS u
        ON t.down_code = u.introducer_code

    LEFT JOIN basic_id_list AS bb
        ON bb.get_basic_bonus_code = u.jmoa_code

    -- level が3未満の間だけ下にたどる
    WHERE t.level < 3
),

-- マッチング詳細テーブル
matching_detail_table AS (
    SELECT
        a.*,
        IFNULL(b.active_count, 0) AS active_count
    FROM introducer_down_line_tree AS a

    LEFT JOIN basic_active_cnt AS b
        ON a.get_basic_bonus_code = b.introducer_code

    WHERE a.exist = 1
      AND (
            -- active_count が1なら今まで通り
            IFNULL(b.active_count, 0) = 1

            -- active_count が2なら level 1〜2
            OR (
                IFNULL(b.active_count, 0) = 2
                AND a.level <= 2
            )

            -- active_count が3以上なら level 1〜3
            OR (
                IFNULL(b.active_count, 0) >= 3
                AND a.level <= 3
            )
      )
)

SELECT
 %s as kibetu,
 get_basic_bonus_code as introducer_code,
 b.send_bv_name as introducer_name,
 a.up_code as line_code,
 a.down_code as basic_code,
 c.send_bv_name as basic_name,
 a.level,
 a.tree_level,
 a.active_count,
 a.basic_bonus,
 TRUNCATE(a.basic_bonus * 0.1, 2) as matching_bonus


FROM matching_detail_table as a

left join nexus_production.users as b
on a.get_basic_bonus_code = b.jmoa_code

left join nexus_production.users as c
on a.down_code = c.jmoa_code

order by get_basic_bonus_code, level
"""