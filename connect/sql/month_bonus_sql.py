MONTH_BONUS_SQL = """
WITH

title_bonus AS (
    SELECT
        root_jwoa_code AS pay_code,
        SUM(bonus_amount) AS sum_bv
    FROM bonus_db.B_title_bonus_result
    WHERE kibetu = %s
      AND bonus_amount > 0
    GROUP BY root_jwoa_code
),

title_diff_bonus AS (
    SELECT
        root_jwoa_code AS pay_code,
        SUM(title_diff_bonus) AS sum_bv
    FROM bonus_db.B_title_diff_bonus_result
    WHERE kibetu = %s
      AND title_diff_bonus > 0
    GROUP BY root_jwoa_code
),

repurchase_over_bonus AS (
    SELECT
        root_code AS pay_code,
        SUM(sum_bv) AS sum_bv
    FROM bonus_db.B_repurchase_over_bonus_result
    WHERE kibetu = %s
      AND sum_bv > 0
    GROUP BY root_code
),

month_user_list AS (
    SELECT
        a.pay_code,
        IFNULL(b.send_bv_name, '') AS jwoa_name
    FROM (
        SELECT pay_code FROM title_bonus
        UNION
        SELECT pay_code FROM title_diff_bonus
        UNION
        SELECT pay_code FROM repurchase_over_bonus
    ) AS a
    INNER JOIN bonus_db.users AS b
        ON a.pay_code = b.jmoa_code
),

month_bonus AS (
    SELECT
        %s AS kibetu,
        a.pay_code AS jwoa_code,
        a.jwoa_name AS jwoa_name,

        CAST(IFNULL(b.sum_bv, 0) AS DECIMAL(18,2)) AS title_bonus,
        CAST(IFNULL(d.sum_bv, 0) AS DECIMAL(18,2)) AS repurchase_over_bonus,
        CAST(IFNULL(c.sum_bv, 0) AS DECIMAL(18,2)) AS title_diff_bonus,

        CAST(0 AS DECIMAL(18,2)) AS three_star_diamond_global_bonus,
        CAST(0 AS DECIMAL(18,2)) AS crown_three_star_diamond_global_bonus,

        CAST(
            IFNULL(b.sum_bv, 0)
            + IFNULL(c.sum_bv, 0)
            + IFNULL(d.sum_bv, 0)
            AS DECIMAL(18,2)
        ) AS month_bonus

    FROM month_user_list AS a

    LEFT JOIN title_bonus AS b
        ON a.pay_code = b.pay_code

    LEFT JOIN title_diff_bonus AS c
        ON a.pay_code = c.pay_code

    LEFT JOIN repurchase_over_bonus AS d
        ON a.pay_code = d.pay_code
)

SELECT *
FROM month_bonus
ORDER BY jwoa_code;
"""