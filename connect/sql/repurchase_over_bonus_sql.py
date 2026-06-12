REPURCHASE_OVER_BONUS_SQL = """

WITH RECURSIVE

repurchase_users AS (
    SELECT *
    FROM bonus_db.purchase_info_list
    WHERE register_year = %s
      AND register_month = %s
      AND order_type = 101
),

repurchase_100bv_users AS (
    SELECT
        jwoa_code,
        send_bv_name AS jwoa_name,
        SUM(bv) AS sum_bv
    FROM repurchase_users
    GROUP BY
        jwoa_code,
        send_bv_name
    HAVING SUM(bv) >= 100
),

repurchase_50bv_users AS (
    SELECT
        jwoa_code,
        send_bv_name AS jwoa_name,
        SUM(bv) AS sum_bv,
        SUM(bv)-50 as custom_bv
    FROM repurchase_users
    GROUP BY
        jwoa_code,
        send_bv_name
    HAVING SUM(bv) >= 51
),

tree AS (
    SELECT
        a.jwoa_code AS root_code,
        b.send_bv_name AS root_name,
        a.jwoa_code AS up_code,
        b.send_bv_name AS up_name,
        c.jmoa_code AS down_code,
        c.send_bv_name AS down_name,
        1 AS tree_level,

        CASE
            WHEN r50.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS matched_flg,

        CASE
            WHEN r50.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS match_count,

        r50.custom_bv AS sum_bv

    FROM repurchase_100bv_users AS a

    LEFT JOIN bonus_db.users AS b
        ON a.jwoa_code = b.jmoa_code

    JOIN bonus_db.users AS c
        ON a.jwoa_code = c.placement_code

    LEFT JOIN repurchase_50bv_users AS r50
        ON c.jmoa_code = r50.jwoa_code

    UNION ALL

    SELECT
        a.root_code,
        a.root_name,
        a.down_code AS up_code,
        a.down_name AS up_name,
        b.jmoa_code AS down_code,
        b.send_bv_name AS down_name,
        a.tree_level + 1 AS tree_level,

        CASE
            WHEN r50.jwoa_code IS NOT NULL THEN 1
            ELSE 0
        END AS matched_flg,

        a.match_count
        + CASE
            WHEN r50.jwoa_code IS NOT NULL THEN 1
            ELSE 0
          END AS match_count,

        r50.custom_bv AS sum_bv

    FROM tree AS a

    JOIN bonus_db.users AS b
        ON a.down_code = b.placement_code

    LEFT JOIN repurchase_50bv_users AS r50
        ON b.jmoa_code = r50.jwoa_code

    WHERE a.match_count <= 10
),

-- 再購入オーバーボーナス結果
repurchase_over_bonus_result as (
SELECT
    root_code,
    root_name,
    up_code,
    up_name,
    down_code,
    down_name,
    tree_level,
    match_count,
    CASE
        WHEN match_count in (1, 2, 4, 5, 7, 8) THEN 0.1
        WHEN match_count in (3, 6, 9) THEN 0.05
        ELSE 0
    END AS rate,
    sum_bv,
    CASE
        WHEN match_count in (1, 2, 4, 5, 7, 8) THEN sum_bv * 0.1
        WHEN match_count in (3, 6, 9) THEN sum_bv * 0.05
        ELSE 0
    END AS over_bonus
FROM tree
WHERE matched_flg = 1
ORDER BY
    root_code,
    tree_level,
    match_count
)

SELECT * FROM repurchase_over_bonus_result

"""