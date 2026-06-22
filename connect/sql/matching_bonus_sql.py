MATCHING_BONUS_SQL = """
WITH RECURSIVE

-- group_by(購入者リスト)
-- 前月の購入情報
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

-- アクティブuser
active_users as (
select jwoa_code
from bonus_db.active_users
where active_status = 1
union
select jwoa_code
from sum_prev_purchasers_list
),

-- ベーシックボーナス結果
basic_bonus_result AS (
    SELECT *
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

-- ベーシックボーナス取得者の紹介元確認
basic_bonus_with_direct_downline AS (
    SELECT
        a.*,
        b.introducer_code,
        c.send_bv_name,

        CASE
            WHEN parent.get_basic_bonus_code IS NOT NULL THEN 1
            ELSE 0
        END AS parent_exists_in_basic_flg

    FROM basic_id_list AS a

    LEFT JOIN bonus_db.users AS b
        ON a.get_basic_bonus_code = b.jmoa_code

    LEFT JOIN bonus_db.users AS c
        ON b.introducer_code = c.jmoa_code

    LEFT JOIN basic_id_list AS parent
        ON b.introducer_code = parent.get_basic_bonus_code
),

-- マッチングの支払いリスト
pay_matching_list AS (
    SELECT
        introducer_code,
        send_bv_name AS jwoa_name,
        get_basic_bonus_code,
        get_basic_bonus_name,
        sum_bonus_amount,
        parent_exists_in_basic_flg
    FROM basic_bonus_with_direct_downline
    WHERE parent_exists_in_basic_flg = 1
    order by introducer_code
),

-- マッチングボーナスの支払い対象者
matching_root_list AS (
    SELECT DISTINCT
        introducer_code
    FROM pay_matching_list
    WHERE introducer_code IS NOT NULL
),

-- マッチングボーナスの支払い対象者のアクティブ紹介者数
matching_active_cnt AS (
    SELECT
        a.introducer_code,
        COUNT(DISTINCT b.jmoa_code) AS active_count
    FROM matching_root_list AS a
    LEFT JOIN bonus_db.users AS b
        ON a.introducer_code = b.introducer_code
    INNER JOIN active_users AS au
        ON au.jwoa_code = b.jmoa_code
    GROUP BY
        a.introducer_code
),

-- ベーシックボーナスの支払い対象者
basic_paid_list AS (
    SELECT DISTINCT
        get_basic_bonus_code
    FROM pay_matching_list
    WHERE get_basic_bonus_code IS NOT NULL
),

-- introducer_code を起点に配置ツリーを下にたどる
introducer_downline_tree AS (

    -- 起点
    SELECT
        r.introducer_code AS root_introducer_code,

        u.placement_code,
        p.send_bv_name AS placement_name,

        u.jmoa_code,
        u.send_bv_name,

        0 AS tree_level,

        -- 起点が basic_paid_list に存在する場合
        CASE
            WHEN bp.get_basic_bonus_code IS NOT NULL THEN 1
            ELSE NULL
        END AS matching_level

    FROM matching_root_list AS r

    INNER JOIN bonus_db.users AS u
        ON u.jmoa_code = r.introducer_code

    LEFT JOIN bonus_db.users AS p
        ON p.jmoa_code = u.placement_code

    LEFT JOIN basic_paid_list AS bp
        ON bp.get_basic_bonus_code = u.jmoa_code

    UNION ALL

    -- 下にたどる
    SELECT
        t.root_introducer_code,

        u.placement_code,
        parent.send_bv_name AS placement_name,

        u.jmoa_code,
        u.send_bv_name,

        t.tree_level + 1 AS tree_level,

        -- basic_paid_list に一致した時だけ番号を増やす
        CASE
            WHEN bp.get_basic_bonus_code IS NOT NULL
                THEN COALESCE(t.matching_level, 0) + 1
            ELSE NULL
        END AS matching_level

    FROM introducer_downline_tree AS t

    INNER JOIN bonus_db.users AS u
        ON u.placement_code = t.jmoa_code

    LEFT JOIN bonus_db.users AS parent
        ON parent.jmoa_code = u.placement_code

    LEFT JOIN basic_paid_list AS bp
        ON bp.get_basic_bonus_code = u.jmoa_code
),

-- ツリー階層リスト
introducer_tree_level AS (
    SELECT
        root_introducer_code,
        placement_code,
        placement_name,
        jmoa_code,
        send_bv_name,
        tree_level,
        matching_level
    FROM introducer_downline_tree
),

-- pay_matching_list に level と matching_level を追加
pay_matching_with_level AS (
    SELECT
        pml.*,
        itl.tree_level,
        itl.matching_level

    FROM pay_matching_list AS pml

    LEFT JOIN introducer_tree_level AS itl
        ON pml.introducer_code = itl.root_introducer_code
       AND pml.get_basic_bonus_code = itl.jmoa_code

    ORDER BY
        pml.introducer_code,
        itl.tree_level,
        pml.get_basic_bonus_code
),

--
pay_matching_with_level_addcount as (
SELECT
 a.*,
 b.active_count
FROM pay_matching_with_level as a
left join matching_active_cnt as b
on a.introducer_code = b.introducer_code
order by a.introducer_code
)


SELECT
    introducer_code,
    jwoa_name,
    active_count,

    SUM(sum_bonus_amount) AS sum_bonus_amount,

    TRUNCATE(SUM(sum_bonus_amount) * 0.10, 2) AS matching_bonus_amount

FROM pay_matching_with_level_addcount
WHERE
    matching_level IS NOT NULL
    AND matching_level <= CASE
        WHEN active_count >= 3 THEN 3
        ELSE active_count
    END
GROUP BY
    introducer_code,
    jwoa_name,
    active_count
ORDER BY
    introducer_code;
"""