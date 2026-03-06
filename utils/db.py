from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

from utils.dom_tree import DOMNode

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db.json")


def _load_db() -> dict:
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_db(data: dict) -> None:
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_tree(url: str, tree: DOMNode) -> None:
    """Serialize and store a DOM tree keyed by URL."""
    db = _load_db()
    db[url] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tree": tree.to_dict(),
    }
    _save_db(db)


def load_tree(url: str) -> Optional[DOMNode]:
    """Retrieve and deserialize a stored DOM tree."""
    db = _load_db()
    entry = db.get(url)
    if entry is None:
        return None
    return DOMNode.from_dict(entry["tree"])


def load_all_trees() -> dict[str, DOMNode]:
    """Load all stored trees, keyed by URL."""
    db = _load_db()
    return {
        url: DOMNode.from_dict(entry["tree"])
        for url, entry in db.items()
    }


def list_entries() -> list[dict]:
    """List all stored URLs with their timestamps."""
    db = _load_db()
    return [
        {"url": url, "timestamp": entry["timestamp"]}
        for url, entry in db.items()
    ]
