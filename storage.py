"""Local SQLite storage for the Vûntric Linguistic Archive.

All user data stays in the data/ folder beside this file.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "archive.sqlite3"
BACKUP_DIR = DATA_DIR / "backups"
SCHEMA_VERSION = 1

WORD_CLASSES = [
    ("class-noun", "Nouns"), ("class-verb", "Verbs"),
    ("class-adjective", "Adjectives"), ("class-adverb", "Adverbs"),
    ("class-pronoun", "Pronouns"), ("class-numeral", "Numerals"),
    ("class-adposition", "Adpositions"), ("class-conjunction", "Conjunctions"),
    ("class-particle", "Particles"), ("class-interjection", "Interjections"),
    ("class-other", "Other / unclassified"),
]

FOUNDATION_TITLES = [
    "Alphabet & Orthography", "Phonology & Phonotactics", "Morphology",
    "Syntax", "Grammar Overview", "Writing Conventions",
]

# (slug, title, parent slug)
DEFAULT_CATEGORIES = [
    ("nature", "Nature & Geography", None),
    ("terrain", "Terrain & Landforms", "nature"),
    ("waterways", "Water & Waterways", "nature"),
    ("weather", "Weather & Climate", "nature"),
    ("plants", "Plants", "nature"),
    ("animals", "Animals", "nature"),
    ("material", "Material Culture", None),
    ("clothing", "Clothing", "material"),
    ("weapons", "Weapons", "material"),
    ("armour", "Armour", "material"),
    ("tools", "Tools & Equipment", "material"),
    ("buildings", "Buildings & Architecture", "material"),
    ("food", "Food & Drink", "material"),
    ("society", "Society & Institutions", None),
    ("occupations", "Occupations", "society"),
    ("kinship", "Kinship & Family", "society"),
    ("government", "Government & Titles", "society"),
    ("warfare", "Warfare & Military", "society"),
    ("trade", "Trade & Economy", "society"),
    ("body", "Body & Anatomy", None),
    ("abstract", "Abstract Concepts", None),
    ("time", "Time & Measurement", None),
    ("motion", "Motion & Travel", None),
    ("speech", "Speech & Communication", None),
    ("perception", "Perception & Cognition", None),
    ("actions", "Actions & Processes", None),
    ("qualities", "Qualities & Properties", None),
]


def new_id(prefix="rec"):
    return f"{prefix}-{uuid.uuid4().hex}"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    with connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS languages (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                stage TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS word_classes (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                parent_id TEXT REFERENCES categories(id) ON DELETE RESTRICT,
                sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS foundations (
                id TEXT PRIMARY KEY,
                language_id TEXT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
                title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY,
                language_id TEXT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
                lemma TEXT NOT NULL,
                word_class_id TEXT NOT NULL REFERENCES word_classes(id) ON DELETE RESTRICT,
                ipa TEXT NOT NULL DEFAULT '', gloss TEXT NOT NULL DEFAULT '',
                definition TEXT NOT NULL DEFAULT '', morphology TEXT NOT NULL DEFAULT '',
                etymology TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','established','obsolete')),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entry_categories (
                entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                category_id TEXT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                PRIMARY KEY(entry_id, category_id)
            );
            CREATE INDEX IF NOT EXISTS idx_entry_language_lemma ON entries(language_id, lemma);
            CREATE INDEX IF NOT EXISTS idx_foundations_language ON foundations(language_id);
            CREATE INDEX IF NOT EXISTS idx_category_parent ON categories(parent_id);
        """)
        c.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        c.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('revision', '0')")
        if c.execute("SELECT COUNT(*) FROM languages").fetchone()[0] == 0:
            c.execute("INSERT INTO languages(id,name,stage,description) VALUES(?,?,?,?)",
                      ("lang-vuntlic", "Vûntlic", "", "Primary language archive"))
        if c.execute("SELECT COUNT(*) FROM word_classes").fetchone()[0] == 0:
            c.executemany("INSERT INTO word_classes(id,name,sort_order) VALUES(?,?,?)",
                          [(ident, label, order) for order, (ident, label) in enumerate(WORD_CLASSES)])
        if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            for order, (slug, label, parent_slug) in enumerate(DEFAULT_CATEGORIES):
                c.execute("INSERT INTO categories(id,name,parent_id,sort_order) VALUES(?,?,?,?)",
                          (f"cat-{slug}", label, f"cat-{parent_slug}" if parent_slug else None, order))
        for r in c.execute("SELECT id FROM languages").fetchall():
            ensure_foundations(c, r["id"])


def ensure_foundations(c, language_id):
    count = c.execute("SELECT COUNT(*) FROM foundations WHERE language_id=?", (language_id,)).fetchone()[0]
    if count == 0:
        for i, title in enumerate(FOUNDATION_TITLES):
            c.execute("INSERT INTO foundations(id,language_id,title,content,sort_order,updated_at) VALUES(?,?,?,?,?,?)",
                      (new_id("foundation"), language_id, title, "", i, now()))


def rows(table, where="", params=(), order=""):
    allowed = {"languages", "word_classes", "categories", "foundations", "entries", "entry_categories"}
    if table not in allowed:
        raise ValueError("Unsupported table")
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def revision(c=None):
    if c is not None:
        return int(c.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
    with connect() as db:
        return revision(db)


def bump(c):
    c.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def save_record(collection, data, ident=None):
    """Save a user-edited record. IDs are immutable; entries accept category_ids."""
    with connect() as c:
        record = dict(data)
        categories = record.pop("category_ids", None)
        if ident:
            allowed = FIELDS[collection] - {"id"}
            invalid = set(record) - allowed
            if invalid:
                raise ValueError(f"Unsupported fields: {sorted(invalid)}")
            if collection == "entries":
                record["updated_at"] = now()
            elif collection == "foundations":
                record["updated_at"] = now()
            if record:
                assignments = ",".join(f"{key}=?" for key in record)
                cursor = c.execute(f"UPDATE {collection} SET {assignments} WHERE id=?", [*record.values(), ident])
                if cursor.rowcount == 0:
                    raise ValueError("Record not found")
            result_id = ident
        else:
            record["id"] = new_id(collection[:-1])
            if collection == "entries":
                record["created_at"] = now()
                record["updated_at"] = now()
            if collection == "foundations":
                record["updated_at"] = now()
            invalid = set(record) - FIELDS[collection]
            if invalid:
                raise ValueError(f"Unsupported fields: {sorted(invalid)}")
            cols = ",".join(record)
            placeholders = ",".join("?" for _ in record)
            c.execute(f"INSERT INTO {collection}({cols}) VALUES({placeholders})", list(record.values()))
            result_id = record["id"]
        if collection == "entries" and categories is not None:
            c.execute("DELETE FROM entry_categories WHERE entry_id=?", (result_id,))
            for category_id in dict.fromkeys(categories):
                c.execute("INSERT INTO entry_categories(entry_id, category_id) VALUES(?,?)", (result_id, category_id))
        bump(c)
        return result_id


FIELDS = {
    "languages": {"id", "name", "stage", "description"},
    "word_classes": {"id", "name", "sort_order"},
    "categories": {"id", "name", "parent_id", "sort_order"},
    "foundations": {"id", "language_id", "title", "content", "sort_order", "updated_at"},
    "entries": {"id", "language_id", "lemma", "word_class_id", "ipa", "gloss", "definition", "morphology", "etymology", "notes", "status", "created_at", "updated_at"},
}


def entry_list(language_id=None):
    with connect() as c:
        query = "SELECT * FROM entries"
        args = ()
        if language_id:
            query += " WHERE language_id=?"
            args = (language_id,)
        query += " ORDER BY lemma COLLATE NOCASE, id"
        result = [dict(r) for r in c.execute(query, args)]
        categories = {}
        for r in c.execute("SELECT entry_id,category_id FROM entry_categories"):
            categories.setdefault(r["entry_id"], []).append(r["category_id"])
        for record in result:
            record["category_ids"] = categories.get(record["id"], [])
        return result


def snapshot():
    with connect() as c:
        data = {"format": "vuntric-archive", "schema_version": SCHEMA_VERSION,
                "kind": "snapshot", "revision": revision(c), "exported_at": now()}
        for table in ("languages", "word_classes", "categories", "foundations", "entries"):
            data[table] = [dict(x) for x in c.execute(f"SELECT * FROM {table} ORDER BY id")]
        category_links = {}
        for link in c.execute("SELECT * FROM entry_categories ORDER BY entry_id,category_id"):
            category_links.setdefault(link["entry_id"], []).append(link["category_id"])
        for entry in data["entries"]:
            entry["category_ids"] = category_links.get(entry["id"], [])
        return data


def make_patch_template():
    return {
        "format": "vuntric-archive", "schema_version": SCHEMA_VERSION,
        "kind": "patch", "base_revision": revision(), "changes": [],
    }


def backup_database():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = BACKUP_DIR / f"archive-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return destination


def _check_import_header(doc, expected_kind):
    if not isinstance(doc, dict):
        raise ValueError("The uploaded JSON must be an object")
    if doc.get("format") != "vuntric-archive":
        raise ValueError("Not a Vûntric Archive file")
    if type(doc.get("schema_version")) is not int or doc["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported schema version")
    if doc.get("kind") != expected_kind:
        raise ValueError(f"Expected a {expected_kind} file")


def _put(c, collection, data, op, ident=None):
    if collection not in FIELDS:
        raise ValueError(f"Unsupported collection: {collection}")
    if not isinstance(data, dict):
        raise ValueError("Record data must be an object")
    if not data:
        raise ValueError("Record data cannot be empty")
    fields = FIELDS[collection]
    unknown = set(data) - fields - ({"category_ids"} if collection == "entries" else set())
    if unknown:
        raise ValueError(f"Unsupported fields in {collection}: {', '.join(sorted(unknown))}")
    values = data.copy()
    category_ids = values.pop("category_ids", None)
    if category_ids is not None and (not isinstance(category_ids, list) or not all(isinstance(x,str) for x in category_ids)):
        raise ValueError("category_ids must be a list of strings")
    if op == "add":
        values.setdefault("id", new_id(collection[:-1]))
        if collection == "entries":
            values.setdefault("created_at", now())
            values.setdefault("updated_at", now())
        if collection == "foundations":
            values.setdefault("updated_at", now())
        keys = list(values)
        c.execute(f"INSERT INTO {collection} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [values[k] for k in keys])
        ident = values["id"]
    elif op == "update":
        if not isinstance(ident, str) or not ident:
            raise ValueError("Update requires an existing record ID")
        if "id" in values:
            raise ValueError("IDs cannot be modified")
        if collection in ("entries", "foundations"):
            values["updated_at"] = now()
        if values:
            keys = list(values)
            cursor = c.execute(f"UPDATE {collection} SET {','.join(f'{k}=?' for k in keys)} WHERE id=?", [*[values[k] for k in keys], ident])
            if cursor.rowcount == 0:
                raise ValueError(f"Unknown {collection} ID: {ident}")
    else:
        raise ValueError("Unsupported operation")
    if collection == "entries" and category_ids is not None:
        c.execute("DELETE FROM entry_categories WHERE entry_id=?", (ident,))
        for cat_id in dict.fromkeys(category_ids):
            c.execute("INSERT INTO entry_categories(entry_id,category_id) VALUES (?,?)", (ident, cat_id))
    return ident


def _run_patch(c, doc):
    _check_import_header(doc, "patch")
    if type(doc.get("base_revision")) is not int or doc["base_revision"] != revision(c):
        raise ValueError(f"Outdated update: base_revision={doc.get('base_revision')}, current revision={revision(c)}. Export a fresh snapshot before generating a new patch.")
    changes = doc.get("changes")
    if not isinstance(changes, list) or len(changes) > 100000:
        raise ValueError("Changes must be a list of at most 100,000 operations")
    for index, change in enumerate(changes, 1):
        try:
            if not isinstance(change, dict):
                raise ValueError("Operation must be an object")
            collection, op = change.get("collection"), change.get("op")
            if collection not in FIELDS:
                raise ValueError("Unsupported collection")
            if op in ("add", "update"):
                _put(c, collection, change.get("data"), op, change.get("id"))
            elif op == "delete":
                if collection not in {"entries", "foundations", "categories"}:
                    raise ValueError("Deletion of languages and word classes is disabled for safety")
                ident = change.get("id")
                if not isinstance(ident, str):
                    raise ValueError("Deletion requires ID")
                if collection == "categories":
                    if c.execute("SELECT 1 FROM categories WHERE parent_id=? LIMIT 1", (ident,)).fetchone():
                        raise ValueError("Category has child categories; move them first")
                    if c.execute("SELECT 1 FROM entry_categories WHERE category_id=? LIMIT 1", (ident,)).fetchone():
                        raise ValueError("Category is in use by entries")
                cursor = c.execute(f"DELETE FROM {collection} WHERE id=?", (ident,))
                if cursor.rowcount == 0:
                    raise ValueError(f"Unknown {collection} ID: {ident}")
            else:
                raise ValueError(f"Unsupported operation: {op}")
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise ValueError(f"Change #{index}: {exc}") from exc
    if changes:
        bump(c)


def _run_snapshot_restore(c, doc):
    _check_import_header(doc, "snapshot")
    required = ("languages", "word_classes", "categories", "foundations", "entries")
    if type(doc.get("revision")) is not int or doc["revision"] < 0:
        raise ValueError("Snapshot revision must be a nonnegative integer")
    for collection in required:
        if not isinstance(doc.get(collection), list):
            raise ValueError(f"Snapshot has no valid {collection} list")
    if not doc["languages"] or not doc["word_classes"]:
        raise ValueError("A snapshot needs at least one language and one word class")
    for collection in ("entry_categories", "entries", "foundations"):
        c.execute(f"DELETE FROM {collection}")
    # Foreign keys are enforced. Remove leaf categories before their parents.
    while c.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
        c.execute("DELETE FROM categories WHERE id NOT IN "
                  "(SELECT parent_id FROM categories WHERE parent_id IS NOT NULL)")
    for collection in ("word_classes", "languages"):
        c.execute(f"DELETE FROM {collection}")
    for collection in ("languages", "word_classes"):
        for record in doc[collection]:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError(f"Invalid record in {collection}")
            _put(c, collection, record, "add")
    # Parents must be inserted ahead of children, regardless of export order.
    remaining = list(doc["categories"])
    inserted = set()
    while remaining:
        later = []
        progressed = False
        for record in remaining:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError("Invalid record in categories")
            if record.get("parent_id") is None or record["parent_id"] in inserted:
                _put(c, "categories", record, "add")
                inserted.add(record["id"])
                progressed = True
            else:
                later.append(record)
        if not progressed:
            raise ValueError("Category tree has a cycle or a missing parent")
        remaining = later
    for collection in ("foundations", "entries"):
        for record in doc[collection]:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError(f"Invalid record in {collection}")
            _put(c, collection, record, "add")
    c.execute("UPDATE meta SET value=? WHERE key='revision'", (str(doc["revision"]),))


def preview_import(doc):
    """Attempt all mutations inside a savepoint, then roll back, verifying references and constraints."""
    kind = doc.get("kind") if isinstance(doc, dict) else None
    with connect() as c:
        c.execute("SAVEPOINT preflight")
        try:
            if kind == "patch":
                _run_patch(c, doc)
                summary = {"kind": "patch", "total": len(doc["changes"]),
                           "add": sum(x.get("op") == "add" for x in doc["changes"]),
                           "update": sum(x.get("op") == "update" for x in doc["changes"]),
                           "delete": sum(x.get("op") == "delete" for x in doc["changes"])}
            elif kind == "snapshot":
                _run_snapshot_restore(c, doc)
                summary = {"kind": "snapshot", "entries": len(doc["entries"]),
                           "languages": len(doc["languages"]), "foundations": len(doc["foundations"]),
                           "categories": len(doc["categories"])}
            else:
                raise ValueError("Unsupported file kind: expected 'patch' or 'snapshot'")
            categories = [dict(r) for r in c.execute("SELECT id,parent_id FROM categories")]
            parents = {x["id"]: x["parent_id"] for x in categories}
            for ident in parents:
                seen = set()
                current = ident
                while current is not None:
                    if current in seen:
                        raise ValueError("A category cannot be nested inside itself or a descendant")
                    seen.add(current)
                    current = parents.get(current)
            bad = c.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise ValueError(f"Broken references: {len(bad)} foreign key violation(s)")
            return summary
        finally:
            c.execute("ROLLBACK TO SAVEPOINT preflight")
            c.execute("RELEASE SAVEPOINT preflight")


def execute_import(doc):
    # Validate first, before making a backup, then validate again during atomic execution.
    summary = preview_import(doc)
    backup_path = backup_database()
    with connect() as c:
        if doc["kind"] == "patch":
            _run_patch(c, doc)
        else:
            _run_snapshot_restore(c, doc)
    return summary, backup_path


def category_path_map(categories):
    lookup = {item["id"]: item for item in categories}
    result = {}
    for category in categories:
        segments, seen, current = [], set(), category
        while current:
            if current["id"] in seen:
                segments.append("[cycle]")
                break
            seen.add(current["id"])
            segments.append(current["name"])
            current = lookup.get(current["parent_id"])
        result[category["id"]] = " › ".join(reversed(segments))
    return result


def can_set_parent(category_id, parent_id, categories):
    lookup = {x["id"]: x for x in categories}
    seen = {category_id}
    while parent_id:
        if parent_id in seen:
            return False
        seen.add(parent_id)
        parent_id = lookup.get(parent_id, {}).get("parent_id")
    return True
