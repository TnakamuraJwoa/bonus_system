
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