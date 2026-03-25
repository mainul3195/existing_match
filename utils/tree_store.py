from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from utils.dom_tree import DOMNode

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db.sqlite")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trees (
    url          TEXT PRIMARY KEY,
    scraper_name TEXT NOT NULL DEFAULT '',
    tree_json    TEXT NOT NULL,
    timestamp    TEXT NOT NULL
)
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(_CREATE_TABLE)
    return conn


MIN_NODES = 30


def count_nodes(node: DOMNode) -> int:
    return 1 + sum(count_nodes(c) for c in node.children)


def save_tree(url: str, tree: DOMNode, scraper_name: str = "") -> None:
    """Serialize and store a DOM tree keyed by URL.

    Raises ValueError if the tree has fewer than MIN_NODES nodes
    (likely a Cloudflare/bot-protection page or empty JS shell).
    """
    node_count = count_nodes(tree)
    if node_count < MIN_NODES:
        raise ValueError(
            f"Tree too small ({node_count} nodes, minimum {MIN_NODES}). "
            f"Page may be a Cloudflare challenge or JS-rendered shell."
        )
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO trees (url, scraper_name, tree_json, timestamp) VALUES (?, ?, ?, ?)",
            (url, scraper_name, json.dumps(tree.to_dict()), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def load_all_trees() -> dict[str, dict]:
    """Load all stored trees, keyed by URL.

    Returns dict of {url: {"tree": DOMNode, "scraper_name": str}}.
    """
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT url, scraper_name, tree_json FROM trees").fetchall()
        return {
            url: {
                "tree": DOMNode.from_dict(json.loads(tree_json)),
                "scraper_name": scraper_name,
            }
            for url, scraper_name, tree_json in rows
        }
    finally:
        conn.close()
