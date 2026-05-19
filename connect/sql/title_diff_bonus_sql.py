TITLE_DIFF_BONUS_SQL = """
WITH RECURSIVE


-- ------------------------- drive  ----------------------------------

-- ドライブボーナス
D_drive_bonus AS (
    SELECT *
    FROM bonus_db.B_drive_bonus_result
    WHERE SUBSTRING(kibetu, 6, 2) = %s
      AND SUBSTRING(kibetu, 1, 4) = %s
),

-- bvの合計
D_drive_sum_bv AS (
    SELECT
        introducer_code AS jwoa_code,
        SUM(sum_bonus_amount) AS sum_bv
    FROM D_drive_bonus
    GROUP BY introducer_code
),

-- ----------------------------------------------------------------------




-- (taitle 当月購入情報)
T_this_month_purchase_info_list as (
SELECT
    p.*,

    CASE
        WHEN p.order_type = 101
        THEN LEAST(IFNULL(p.bv, 0), 50)

        ELSE IFNULL(p.bv, 0)
    END AS custom_bv

FROM bonus_db.purchase_info_list AS p
WHERE p.register_year = 2026
  AND p.register_month = 1
),

-- (taitle 当月購入情報)合計
T_sum_this_month_purchase_info_list as (
SELECT
    jwoa_code,
    send_bv_name,
    SUM(custom_bv) AS sum_bv
FROM T_this_month_purchase_info_list
GROUP BY
    jwoa_code,
    send_bv_name
HAVING SUM(custom_bv) > 0
),

-- line_codeは購入者　⇒上位者(ラインコード) ⇒　その上位者(上位者こーど)
-- 支払い者のtree
payer_tree AS (

    -- ① 起点 = 支払い者本人
    SELECT
        u.jmoa_code AS payer_code,
        u.send_bv_name AS payer_name,
        u.jmoa_code AS line_code,
        u.placement_code AS upper_code,
        0 AS lvl,
        pu.sum_bv
    FROM bonus_db.users AS u
    JOIN T_sum_this_month_purchase_info_list AS pu
      ON pu.jwoa_code = u.jmoa_code

    UNION ALL

    -- ② 上にさかのぼる
    SELECT
        t.payer_code,
        t.payer_name,
        up.jmoa_code AS line_code,
        up.placement_code AS upper_code,
        t.lvl + 1 AS lvl,
        pu.sum_bv
    FROM payer_tree AS t
    JOIN bonus_db.users AS up
      ON up.jmoa_code = t.upper_code
    left join T_sum_this_month_purchase_info_list as pu
      ON t.payer_code = pu.jwoa_code
    WHERE t.lvl < 5000
      AND t.upper_code IS NOT NULL
      AND t.upper_code <> ''
),

-- 紹介者ごとの合計BV
introducer_total_bv AS (
    SELECT
        upper_code,
        line_code,
        SUM(sum_bv) AS sum_bv,

        CASE
            WHEN ROW_NUMBER() OVER (
                PARTITION BY upper_code
                ORDER BY SUM(sum_bv) DESC
            ) >= 3
            THEN 2

            ELSE ROW_NUMBER() OVER (
                PARTITION BY upper_code
                ORDER BY SUM(sum_bv) DESC
            )
        END AS rn

    FROM payer_tree

    GROUP BY
        upper_code,
        line_code

    ORDER BY
        upper_code,
        rn
),

-- 収入ライン or 基本ラインごとの合計
line_type_total_bv AS (
    SELECT
        upper_code,
        rn,
        SUM(sum_bv) AS sum_bv

    FROM introducer_total_bv

    GROUP BY
        upper_code,
        rn
),

-- 収入ライン or 基本ラインごとの合計2
line_type_total_bv2 AS (
    SELECT
        upper_code,
        send_bv_name,
        IFNULL(MAX(CASE WHEN rn = 1 THEN sum_bv END),0) AS income_line_bv,
        IFNULL(MAX(CASE WHEN rn = 2 THEN sum_bv END),0) AS basic_line_bv

    FROM line_type_total_bv as a
    left join bonus_db.users as b
    on a.upper_code = b.jmoa_code

    GROUP BY
        upper_code
),

-- タイトル結果
title_result as (
SELECT
    upper_code as jwoa_code,
    send_bv_name as jwoa_name,
    income_line_bv,
    basic_line_bv,
    CASE
        WHEN income_line_bv >= 562500
         AND basic_line_bv >= 562500
        THEN 11

        WHEN income_line_bv >= 375000
         AND basic_line_bv >= 375000
        THEN 10

        WHEN income_line_bv >= 250000
         AND basic_line_bv >= 250000
        THEN 9

        WHEN income_line_bv >= 125000
         AND basic_line_bv >= 125000
        THEN 8

        WHEN income_line_bv >= 62500
         AND basic_line_bv >= 62500
        THEN 7

        WHEN income_line_bv >= 31250
         AND basic_line_bv >= 31250
        THEN 6

        WHEN income_line_bv >= 15000
         AND basic_line_bv >= 15000
        THEN 5

        WHEN income_line_bv >= 7500
         AND basic_line_bv >= 7500
        THEN 4

        WHEN income_line_bv >= 2500
         AND basic_line_bv >= 2500
        THEN 3

        WHEN income_line_bv >= 1250
         AND basic_line_bv >= 1250
        THEN 2

        WHEN income_line_bv >= 750
         AND basic_line_bv >= 750
        THEN 1

        ELSE 0
    END AS title_id
FROM line_type_total_bv2
),

-- ------------------------- taitle  ----------------------------------
-- 変数
var as (
 select
  2 as set_title,          -- ２スターダイヤ以上の実績を達成した会員が対象
  1 as minimum_title_id    -- 一番低いタイトル
),


title_result_with_rate as (
select
 *,
    CASE
        WHEN title_id = 10
        THEN 9

        WHEN title_id = 9
        THEN 9

        WHEN title_id = 8
        THEN 8

        WHEN title_id = 7
        THEN 7

        WHEN title_id = 6
        THEN 6

        WHEN title_id = 5
        THEN 4

        WHEN title_id = 4
        THEN 2

        ELSE 0
    END AS bonus_rate
from title_result
),

-- 当月、2スターダイヤ以上
this_month_two_star_dia as (
select *
from title_result_with_rate
where title_id >= (select set_title from var)
),

-- 上位者で下を見る
introducer_down_tree AS (

    -- 1階層目：上位者
    SELECT
        a.jwoa_code as root_jwoa_code,
        a.jwoa_name as root_name,
        a.title_id as up_title_id,
        a.bonus_rate as up_bonus_rate,
        a.jwoa_code AS up_jwoa_code,
        a.jwoa_name as up_jwoa_name,
        c.title_id as down_title_id,
        c.bonus_rate as down_bonus_rate,
        b.jmoa_code as down_jwoa_code,
        b.send_bv_name as down_name,
        0 as tree_level
    FROM this_month_two_star_dia as a

    left join bonus_db.users as b
    on a.jwoa_code = b.placement_code

    left join title_result_with_rate as c
    on b.jmoa_code = c.jwoa_code

    where a.title_id > b.jmoa_code

    union all

    SELECT
        t.root_jwoa_code,
        t.root_name,
        t.down_title_id as up_title_id,
        t.up_bonus_rate up_bonus_rate,
        t.down_jwoa_code AS up_jwoa_code,
        t.down_name AS up_jwoa_name,
        c.title_id as down_title_id,
        c.bonus_rate as down_bonus_rate,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        t.tree_level + 1 AS tree_level

    FROM introducer_down_tree AS t

    JOIN bonus_db.users AS u
      ON u.placement_code = t.down_jwoa_code

    left join title_result_with_rate as c
    on t.down_jwoa_code = c.jwoa_code

    WHERE t.tree_level < 10000
      AND t.down_title_id > u.jmoa_code

),

-- 2スター以上のダウンを表示
two_star_or_hith as (
select
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
 up_bonus_rate - down_bonus_rate as pay_bonus_rate,
 tree_level


from introducer_down_tree
where
 down_title_id >= (select minimum_title_id from var)
 and up_bonus_rate > down_bonus_rate
),


-- -------------------- タイトル差額ボーナス結果 --------------------
title_diff_bonus_result as (
select
 a.*,
 b.sum_bv,
TRUNCATE(
    (b.sum_bv * (pay_bonus_rate / 100)),
    2
) AS title_diff_bonus
from two_star_or_hith as a
left join D_drive_sum_bv as b
on a.down_jwoa_code = b.jwoa_code
)


select *
from title_diff_bonus_result
where sum_bv > 0
"""