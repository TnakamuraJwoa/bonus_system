TITLE_DIFF_BONUS_SQL = """
WITH RECURSIVE


-- ------------------------- drive  ----------------------------------

-- ドライブボーナス
D_drive_bonus AS (
    SELECT
        a.*,

        CASE
            WHEN a.title_name = '1スターダイヤ'
                THEN TRUNCATE(IFNULL(a.sum_bv, 0) * 0.05, 2)
            ELSE
                TRUNCATE(IFNULL(a.sum_bv, 0) * 0.10, 2)
        END AS custom_bv

    FROM bonus_db.B_drive_bonus_result AS a

    left join bonus_db.period_master as b
    on a.kibetu = b.kibetu

    WHERE
        MONTH(st_date) = %s
        AND YEAR(st_date) = %s
        AND a.title_name IN (
            'タイトルなし',
            '明日の星',
            'ニュースター',
            '1スターダイヤ'
        )
),

-- bvの合計
D_drive_sum_bv AS (
    SELECT
        introducer_code AS jwoa_code,
        SUM(custom_bv) AS sum_bv
    FROM D_drive_bonus
    GROUP BY introducer_code
),

-- ----------------------------------------------------------------------

-- タイトル結果（月タイトル登録済みデータを参照）
title_result as (
SELECT
    jwoa_code,
    jwoa_name,
    income_line_bv,
    basic_line_bv,
    title_id
FROM bonus_db.month_title
WHERE kibetu = %s
),

-- ------------------------- taitle  ----------------------------------


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
where title_id >= 4
),

-- 上位者で下を見る
introducer_down_tree AS (

    -- 1階層目：上位者
    SELECT
        a.title_id as root_title_id,
        a.bonus_rate as root_bonus_rate,
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

    left join nexus_production.users as b
    on a.jwoa_code = b.placement_code

    left join title_result_with_rate as c
    on b.jmoa_code = c.jwoa_code

    where a.title_id > c.title_id

    union all

    SELECT
        t.root_title_id,
        t.root_bonus_rate,
        t.root_jwoa_code,
        t.root_name,
        t.down_title_id as up_title_id,
        t.down_bonus_rate up_bonus_rate,
        t.down_jwoa_code AS up_jwoa_code,
        t.down_name AS up_jwoa_name,
        c.title_id as down_title_id,
        c.bonus_rate as down_bonus_rate,
        u.jmoa_code AS down_jwoa_code,
        u.send_bv_name AS down_name,
        t.tree_level + 1 AS tree_level

    FROM introducer_down_tree AS t

    JOIN nexus_production.users AS u
      ON u.placement_code = t.down_jwoa_code

    left join title_result_with_rate as c
    on u.jmoa_code = c.jwoa_code

    WHERE t.tree_level < 10000
      AND t.root_title_id > c.title_id

),


-- -------------------- タイトル差額ボーナス結果 --------------------
title_diff_bonus_result as (
select
 a.*,
 b.sum_bv,
TRUNCATE(
    (b.sum_bv * ((root_bonus_rate - down_bonus_rate) / 10)),
    2
) AS title_diff_bonus
from introducer_down_tree as a

left join D_drive_sum_bv as b
on a.down_jwoa_code = b.jwoa_code
)


SELECT
    root_title_id,
    COALESCE(root_tm.title_name, 'タイトルなし') AS root_title_name,
    root_bonus_rate,
    root_jwoa_code,
    root_name,
    up_title_id,
    COALESCE(up_tm.title_name, 'タイトルなし') AS up_title_name,
    up_bonus_rate,
    up_jwoa_code,
    up_jwoa_name,
    down_title_id,
    COALESCE(down_tm.title_name, 'タイトルなし') AS down_title_name,
    down_bonus_rate,
    down_jwoa_code,
    down_name,
    root_bonus_rate - down_bonus_rate as pay_bonus_rate,
    tree_level,
    sum_bv,
    title_diff_bonus
FROM title_diff_bonus_result AS tdr
LEFT JOIN bonus_db.title_master AS root_tm
  ON tdr.root_title_id = root_tm.title_id
LEFT JOIN bonus_db.title_master AS up_tm
  ON tdr.up_title_id = up_tm.title_id
LEFT JOIN bonus_db.title_master AS down_tm
  ON tdr.down_title_id = down_tm.title_id
WHERE title_diff_bonus > 0
"""