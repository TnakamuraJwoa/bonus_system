import logging
from collections import defaultdict

from django.db import connections

from connect.sql.introducer_tree_sql import (
    INTRODUCER_TREE_DOWNLINE_SQL,
    INTRODUCER_TREE_FOCUS_SQL,
    INTRODUCER_TREE_MEMBER_COUNT_SQL,
    INTRODUCER_TREE_UPLINE_SQL,
)

logger = logging.getLogger(__name__)

MAX_TREE_DEPTH = 15
MAX_TREE_NODES = 500


def _row_to_dict(cursor, row):
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def _execute_rows(sql, params):
    with connections["rds"].cursor() as cursor:
        logger.info("紹介者ツリーSQLを実行します。")
        cursor.execute(sql, params)
        return [_row_to_dict(cursor, row) for row in cursor.fetchall()]


def _execute_scalar(sql, params):
    with connections["rds"].cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def _node_from_row(row):
    return {
        "jwoa_code": row.get("jwoa_code") or "",
        "jwoa_name": row.get("jwoa_name") or "",
        "send_bv_name": row.get("jwoa_name") or "",
        "rank": row.get("rank"),
        "introducer_code": row.get("introducer_code") or "",
        "rel_level": row.get("rel_level", 0),
        "children": [],
    }


def _build_children_tree(parent_code, children_by_parent):
    nodes = []
    for row in children_by_parent.get(parent_code, []):
        node = _node_from_row(row)
        node["children"] = _build_children_tree(node["jwoa_code"], children_by_parent)
        nodes.append(node)
    return nodes


def build_introducer_tree_view(jwoa_code):
    result = {
        "tree_ancestors": [],
        "tree_focus": None,
        "tree_children": [],
        "tree_truncated": False,
        "tree_unavailable_reason": None,
        "tree_node_count": 0,
    }

    member_code = (jwoa_code or "").strip()
    if not member_code:
        result["tree_unavailable_reason"] = (
            "会員コードまたは紹介者コードを入力して検索すると、紹介者Treeを表示できます。"
        )
        return result

    member_count = _execute_scalar(
        INTRODUCER_TREE_MEMBER_COUNT_SQL,
        [member_code],
    )
    if member_count == 0:
        result["tree_unavailable_reason"] = (
            f"会員コード {member_code} のデータが見つかりません。"
        )
        return result
    if member_count > 1:
        result["tree_unavailable_reason"] = (
            f"会員コード {member_code} が複数件ヒットしています。"
            "完全一致で1件に特定できるコードを入力してください。"
        )
        return result

    focus_rows = _execute_rows(INTRODUCER_TREE_FOCUS_SQL, [member_code])
    if not focus_rows:
        result["tree_unavailable_reason"] = (
            f"会員コード {member_code} のデータが見つかりません。"
        )
        return result

    focus = _node_from_row(focus_rows[0])
    focus["rel_level"] = 0

    upline_rows = _execute_rows(
        INTRODUCER_TREE_UPLINE_SQL,
        [member_code, MAX_TREE_DEPTH, MAX_TREE_NODES],
    )
    downline_rows = _execute_rows(
        INTRODUCER_TREE_DOWNLINE_SQL,
        [member_code, MAX_TREE_DEPTH, MAX_TREE_NODES],
    )

    ancestors = [_node_from_row(row) for row in upline_rows]

    children_by_parent = defaultdict(list)
    for row in downline_rows:
        children_by_parent[row["introducer_code"]].append(row)

    children = _build_children_tree(member_code, children_by_parent)
    node_count = len(ancestors) + 1 + len(downline_rows)
    truncated = (
        len(upline_rows) >= MAX_TREE_NODES
        or len(downline_rows) >= MAX_TREE_NODES
    )

    result["tree_ancestors"] = ancestors
    result["tree_focus"] = focus
    result["tree_children"] = children
    result["tree_truncated"] = truncated
    result["tree_node_count"] = node_count
    return result


def fetch_introducer_tree_search_path(root_code, tree_search):
    root = (root_code or "").strip()
    keyword = (tree_search or "").strip()
    if not root or not keyword:
        return []

    max_search_depth = 100
    code_prefix = f"{keyword}%"
    name_like = f"%{keyword}%"
    sql = """
WITH RECURSIVE scope AS (
    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name AS send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        0 AS rel_level,
        CAST(c.jwoa_code AS CHAR(20000)) AS path_codes
    FROM bonus_db.C_users_introducer_tree_cache c
    WHERE c.jwoa_code = %s

    UNION ALL

    SELECT
        c.id,
        c.introducer_code,
        c.introducer_name,
        c.introducer_rank,
        c.jwoa_code,
        c.jwoa_name AS send_bv_name,
        c.`rank`,
        c.tree_level,
        c.created_at,
        scope.rel_level + 1 AS rel_level,
        CONCAT(scope.path_codes, ',', c.jwoa_code) AS path_codes
    FROM bonus_db.C_users_introducer_tree_cache c
    INNER JOIN scope
        ON c.introducer_code = scope.jwoa_code
    WHERE scope.rel_level < %s
      AND FIND_IN_SET(c.jwoa_code, scope.path_codes) = 0
),
target AS (
    SELECT *
    FROM scope
    WHERE rel_level > 0
      AND (
          jwoa_code LIKE %s
          OR send_bv_name LIKE %s
      )
    ORDER BY
        CASE
            WHEN jwoa_code = %s THEN 0
            WHEN jwoa_code LIKE %s THEN 1
            ELSE 2
        END,
        rel_level,
        jwoa_code
    LIMIT 1
)
SELECT
    s.id,
    s.introducer_code,
    s.introducer_name,
    s.introducer_rank,
    s.jwoa_code,
    s.send_bv_name,
    s.`rank`,
    s.tree_level,
    s.created_at,
    s.rel_level,
    FIND_IN_SET(s.jwoa_code, target.path_codes) - 1 AS path_index,
    CASE WHEN s.jwoa_code = target.jwoa_code THEN 1 ELSE 0 END AS is_target
FROM scope s
INNER JOIN target
    ON FIND_IN_SET(s.jwoa_code, target.path_codes) > 0
ORDER BY path_index
    """
    params = [root, max_search_depth, code_prefix, name_like, keyword, code_prefix]
    with connections["rds"].cursor() as cursor:
        logger.info("紹介者Tree 下位会員DB検索SQLを実行します。")
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
