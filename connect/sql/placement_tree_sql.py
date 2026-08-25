PLACEMENT_TREE_REBUILD_CACHE_SQL = """
INSERT INTO bonus_db.C_users_placement_tree_cache (
    placement_code,
    placement_name,
    placement_rank,
    jwoa_code,
    send_bv_name,
    `rank`,
    tree_level
)
WITH RECURSIVE user_tree (
    placement_code,
    placement_name,
    placement_rank,
    jmoa_code,
    send_bv_name,
    `rank`,
    tree_level
) AS (
    SELECT
        u.placement_code,
        CAST(NULL AS CHAR(50) CHARSET cp932),
        CAST(NULL AS SIGNED),
        u.jmoa_code,
        u.send_bv_name,
        u.`rank`,
        0
    FROM nexus_production.users u
    WHERE u.jmoa_code = 'JP1873001'

    UNION ALL

    SELECT
        u.placement_code,
        parent.send_bv_name,
        parent.`rank`,
        u.jmoa_code,
        u.send_bv_name,
        u.`rank`,
        ut.tree_level + 1
    FROM user_tree ut
    INNER JOIN bonus_db.users_target_rank u
        ON u.placement_code = ut.jmoa_code
    LEFT JOIN bonus_db.users_target_rank parent
        ON parent.jmoa_code = u.placement_code
)
SELECT
    placement_code,
    placement_name,
    placement_rank,
    jmoa_code,
    send_bv_name,
    `rank`,
    tree_level
FROM user_tree
ORDER BY tree_level, jmoa_code
"""


PLACEMENT_TREE_MEMBER_COUNT_SQL = """
    SELECT COUNT(*)
    FROM bonus_db.C_users_placement_tree_cache
    WHERE jwoa_code = %s
"""

PLACEMENT_TREE_FOCUS_SQL = """
    SELECT
        c.id,
        c.placement_code,
        c.placement_name,
        c.placement_rank,
        c.jwoa_code,
        c.send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at
    FROM bonus_db.C_users_placement_tree_cache c
    WHERE c.jwoa_code = %s
    ORDER BY c.id
    LIMIT 1
"""

PLACEMENT_TREE_UPLINE_SQL = """
WITH RECURSIVE upline AS (
    SELECT
        c.id,
        c.placement_code,
        c.placement_name,
        c.placement_rank,
        c.jwoa_code,
        c.send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        0 AS rel_level
    FROM bonus_db.C_users_placement_tree_cache c
    WHERE c.jwoa_code = %s

    UNION ALL

    SELECT
        c.id,
        c.placement_code,
        c.placement_name,
        c.placement_rank,
        c.jwoa_code,
        c.send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        u.rel_level - 1 AS rel_level
    FROM bonus_db.C_users_placement_tree_cache c
    INNER JOIN upline u
        ON c.jwoa_code = u.placement_code
    WHERE u.rel_level > -%s
      AND u.placement_code IS NOT NULL
      AND u.placement_code <> ''
)
SELECT
    id,
    placement_code,
    placement_name,
    placement_rank,
    jwoa_code,
    send_bv_name,
    `rank`,
    tree_level,
    created_at,
    rel_level
FROM upline
WHERE rel_level < 0
ORDER BY rel_level ASC
LIMIT %s
"""

PLACEMENT_TREE_DOWNLINE_SQL = """
WITH RECURSIVE downline AS (
    SELECT
        c.id,
        c.placement_code,
        c.placement_name,
        c.placement_rank,
        c.jwoa_code,
        c.send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        1 AS rel_level
    FROM bonus_db.C_users_placement_tree_cache c
    WHERE c.placement_code = %s

    UNION ALL

    SELECT
        c.id,
        c.placement_code,
        c.placement_name,
        c.placement_rank,
        c.jwoa_code,
        c.send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        d.rel_level + 1 AS rel_level
    FROM bonus_db.C_users_placement_tree_cache c
    INNER JOIN downline d
        ON c.placement_code = d.jwoa_code
    WHERE d.rel_level < %s
)
SELECT
    id,
    placement_code,
    placement_name,
    placement_rank,
    jwoa_code,
    send_bv_name,
    `rank`,
    tree_level,
    created_at,
    rel_level
FROM downline
ORDER BY rel_level ASC, jwoa_code ASC
LIMIT %s
"""
