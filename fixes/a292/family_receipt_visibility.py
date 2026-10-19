"""A292 - safe, reversible visibility control for receipts in the family portal.
This is a standalone helper. Integration into the authenticated Flask routes
requires verification against the live /data sources before release.
"""
import sqlite3

def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_family_receipt_visibility (
        receipt_id INTEGER PRIMARY KEY,
        hidden INTEGER NOT NULL CHECK(hidden IN (0,1)),
        reason TEXT NOT NULL,
        actor TEXT NOT NULL,
        changed_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_family_receipt_visibility_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL,
        actor TEXT NOT NULL,
        changed_at TEXT NOT NULL DEFAULT (datetime('now')))""")

def hidden(conn, receipt_id):
    try:
        row=conn.execute("SELECT hidden FROM bodymind_family_receipt_visibility WHERE receipt_id=?",(int(receipt_id),)).fetchone()
        return bool(row[0]) if row else False
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return False
        raise

def family_visible_receipts(conn, rows):
    return [r for r in rows if not hidden(conn, dict(r)["id"])]

def set_hidden(conn, receipt_id, hide, reason, actor):
    """Caller owns transaction. No UPDATE/DELETE on receipts or payments."""
    rid=int(receipt_id)
    reason=str(reason or "").strip()
    actor=str(actor or "").strip()
    if rid<=0 or not (8<=len(reason)<=500) or not actor:
        raise ValueError("Receipt, reason and operator required")
    if not conn.execute("SELECT 1 FROM ricevute WHERE id=?",(rid,)).fetchone():
        raise ValueError("Receipt does not exist")
    initialize(conn)
    flag=1 if hide else 0
    conn.execute("""INSERT INTO bodymind_family_receipt_visibility
        (receipt_id,hidden,reason,actor) VALUES(?,?,?,?)
        ON CONFLICT(receipt_id) DO UPDATE SET
        hidden=excluded.hidden,reason=excluded.reason,actor=excluded.actor,
        changed_at=datetime('now')""",(rid,flag,reason,actor))
    conn.execute("""INSERT INTO bodymind_family_receipt_visibility_audit
        (receipt_id,action,reason,actor) VALUES(?,?,?,?)""",
        (rid,"hide" if hide else "restore",reason,actor))
