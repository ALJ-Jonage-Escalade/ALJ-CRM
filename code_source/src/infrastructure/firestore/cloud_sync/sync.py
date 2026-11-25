"""Réception (`pull`) et envoi (`flush`) des modifications entre le cache et Firestore."""
import datetime
import json
import sqlite3
from typing import Any, Dict, List, NamedTuple, Optional

from infrastructure.firestore.client import FirestoreConflictError
from infrastructure.firestore.cloud_sync.cache import (
    _Applying,
    _get_base,
    _pk_string,
    _read_row,
    _Resume,
    _set_base,
    _upsert_row,
    _where,
    get_state,
    set_state,
    table_columns,
    table_exists,
    table_pk,
    tracked_tables,
)
from infrastructure.firestore.cloud_sync.common import (
    COMMIT_CHUNK,
    PULL_MARGIN_SECONDS,
    REFERENCES,
    TOMBSTONE_FIELDS,
    SyncReport,
    _same,
    collection_for,
    doc_id_for,
    ts_key,
    ts_minus,
    upgrade_legacy_fields,
)

def renumber_row(conn, store, table: str, old_id: int, report: SyncReport) -> int:
    """Donne un nouvel identifiant à une ligne locale dont l'ID est déjà utilisé
    dans Firestore par une autre ligne (deux postes ont créé en même temps).
    Les références (REFERENCES) sont mises à jour ; les déclencheurs notent tout."""
    pk = table_pk(conn, table)[0]
    local_max = conn.execute(f'SELECT COALESCE(MAX("{pk}"), 0) FROM "{table}"').fetchone()[0]  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
    remote_max = store.max_int_id(collection_for(table), pk)
    new_id = max(local_max, remote_max) + 1
    conn.execute(f'UPDATE "{table}" SET "{pk}" = ? WHERE "{pk}" = ?', (new_id, old_id))  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
    for ref_table, ref_col in REFERENCES.get(table, []):
        if table_exists(conn, ref_table):
            conn.execute(f'UPDATE "{ref_table}" SET "{ref_col}" = ? WHERE "{ref_col}" = ?', (new_id, old_id))  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
    report.setdefault("renumbered", []).append(f"{table} {old_id} -> {new_id}")
    return new_id


def apply_remote_docs(conn, store, table: str, docs: List[Dict[str, Any]], report: SyncReport):
    """Intègre des documents Firestore dans le cache (fusion à 3 voies si besoin)."""
    if not docs:
        return
    cols = table_columns(conn, table)
    pk = table_pk(conn, table)
    conn.execute("BEGIN IMMEDIATE")
    try:
        with _Applying(conn):
            for d in docs:
                vals = [d["fields"].get(c) for c in pk]
                if any(v is None for v in vals):
                    continue
                pk_str = _pk_string(conn, vals)
                base, base_ut = _get_base(conn, table, pk_str)
                if base_ut and ts_key(base_ut) >= ts_key(d["update_time"]):
                    continue
                dirty = conn.execute("SELECT 1 FROM _fs_changes WHERE tbl = ? AND pk = ?",
                                     (table, pk_str)).fetchone() is not None
                local = _read_row(conn, table, pk, vals)
                if d["deleted"]:
                    if base is None and dirty and local is not None:
                        # Ligne créée ici avec un ID supprimé ailleurs : on la garde.
                        continue
                    conn.execute(f'DELETE FROM "{table}" WHERE {_where(pk)}', vals)  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
                    conn.execute("DELETE FROM _fs_base WHERE tbl = ? AND pk = ?", (table, pk_str))
                    conn.execute("DELETE FROM _fs_changes WHERE tbl = ? AND pk = ?", (table, pk_str))
                    report["pulled"] = report.get("pulled", 0) + 1
                    continue
                fields = upgrade_legacy_fields(table, d["fields"])
                remote = {c: fields[c] for c in cols if c in fields}
                if dirty and base is None and local is not None:
                    # Même ID créé sur deux postes : renuméroter la ligne locale.
                    if len(pk) == 1 and isinstance(vals[0], int):
                        with _Resume(conn):
                            renumber_row(conn, store, table, vals[0], report)
                        local = None
                    else:
                        merged = dict(remote)
                        merged.update(local)
                        _upsert_row(conn, table, cols, pk, merged)
                        _set_base(conn, table, pk_str, remote, d["update_time"])
                        continue
                if dirty and local is not None and base is not None:
                    merged = dict(remote)
                    for c, v in local.items():
                        if not _same(v, base.get(c)) and (c in base or v is not None):
                            merged[c] = v
                    _upsert_row(conn, table, cols, pk, merged)
                elif dirty and local is None and base is not None:
                    pass  # supprimée ici : la suppression sera envoyée
                else:
                    try:
                        _upsert_row(conn, table, cols, pk, remote)
                    except sqlite3.IntegrityError as e:
                        report.setdefault("errors", []).append(f"{table}/{d['id']} : {e}")
                        continue
                _set_base(conn, table, pk_str, remote, d["update_time"])
                report["pulled"] = report.get("pulled", 0) + 1
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise



def pull(conn, store, report: Optional[SyncReport] = None) -> SyncReport:
    """Récupère les documents modifiés depuis la dernière synchronisation."""
    report = report if report is not None else SyncReport()
    for table in tracked_tables(conn):
        watermark = get_state(conn, f"wm:{table}") or "1970-01-01T00:00:00Z"
        docs = store.list_modified_since(collection_for(table), ts_minus(watermark, PULL_MARGIN_SECONDS))
        apply_remote_docs(conn, store, table, docs, report)
        if docs:
            newest = max((d["modified_at"] for d in docs if d.get("modified_at")), key=ts_key, default=watermark)
            if ts_key(newest) > ts_key(watermark):
                set_state(conn, f"wm:{table}", newest)
    set_state(conn, "last_pull", datetime.datetime.now().isoformat(timespec="seconds"))
    return report


class PendingWrite(NamedTuple):
    """A local change ready to be sent: its row in _fs_changes and the store write built from it."""
    table: str
    pk_str: str
    seq: int
    write: Dict[str, Any]  # Any: a store write (collection, doc_id, fields, mask, precondition…)
    row: Optional[Dict[str, Any]]  # Any: the cached row; None for a deletion


def _build_write(conn, table: str, pk: List[str], pk_str: str, author: str
                 ) -> Optional[tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    """The store write of a changed row and the row itself (None for a deletion), or None when there is nothing to
    send: a row deleted before it was ever sent, or a row unchanged since the last synchronised version."""
    vals = json.loads(pk_str)
    row = _read_row(conn, table, pk, vals)
    base, base_ut = _get_base(conn, table, pk_str)
    write: Dict[str, Any] = {"collection": collection_for(table), "doc_id": doc_id_for(vals), "by": author}
    if row is None:
        if base is None:
            return None
        kept = {c: base[c] for c in TOMBSTONE_FIELDS.get(table, ()) if c in base}
        write.update(fields={**kept, **dict(zip(pk, vals, strict=False))}, mask=None, deleted=True,
                     precondition={"updateTime": base_ut} if base_ut else None)
        return write, None
    if base is None:
        write.update(fields=row, mask=None, deleted=False, precondition=None, create=True)
        return write, row
    diff = {c: v for c, v in row.items() if c not in base or not _same(v, base.get(c))}
    if not diff:
        return None
    write.update(fields=diff, mask=list(diff.keys()), deleted=False,
                 precondition={"updateTime": base_ut} if base_ut else {"exists": True})
    return write, row


MAX_FLUSH_RETRIES = 3


def flush(conn, store, author: str = "", report: Optional[SyncReport] = None,
          _depth: int = 0) -> SyncReport:
    """Envoie les lignes modifiées localement vers Firestore."""
    report = report if report is not None else SyncReport()
    changes = conn.execute("SELECT tbl, pk, seq FROM _fs_changes ORDER BY seq").fetchall()
    if not changes:
        return report
    primary_keys: Dict[str, List[str]] = {}
    pending: List[PendingWrite] = []
    for change in changes:
        table, pk_str, seq = change["tbl"], change["pk"], change["seq"]
        if table not in primary_keys:
            if not table_exists(conn, table):
                conn.execute("DELETE FROM _fs_changes WHERE tbl = ?", (table,))
                continue
            primary_keys[table] = table_pk(conn, table)
        built = _build_write(conn, table, primary_keys[table], pk_str, author)
        if built is None:
            conn.execute("DELETE FROM _fs_changes WHERE tbl = ? AND pk = ? AND seq <= ?", (table, pk_str, seq))
            continue
        pending.append(PendingWrite(table, pk_str, seq, built[0], built[1]))

    def retry_or_give_up(error: str) -> SyncReport:
        if _depth < MAX_FLUSH_RETRIES:
            return flush(conn, store, author, report, _depth + 1)
        report.setdefault("errors", []).append(error)
        return report

    # Créations : vérifier que l'ID n'est pas déjà pris (tombe => on écrase la tombe)
    collisions: List[PendingWrite] = []
    creations_by_table: Dict[str, List[PendingWrite]] = {}
    for item in pending:
        if item.write.get("create"):
            creations_by_table.setdefault(item.table, []).append(item)
    for table, creations in creations_by_table.items():
        found = store.get_many(collection_for(table), [item.write["doc_id"] for item in creations])
        for item in creations:
            remote = found.get(item.write["doc_id"])
            if remote is None:
                item.write["precondition"] = {"exists": False}
            elif remote["deleted"]:
                item.write["precondition"] = {"updateTime": remote["update_time"]}
            else:
                same = all(_same(remote["fields"].get(c), v) for c, v in (item.row or {}).items())
                if same or len(primary_keys[table]) != 1 or not isinstance(json.loads(item.pk_str)[0], int):
                    # Contenu identique, ou clé « métier » (texte) : on adopte / écrase.
                    item.write["precondition"] = {"updateTime": remote["update_time"]}
                else:
                    collisions.append(item)
    if collisions:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for item in collisions:
                renumber_row(conn, store, item.table, json.loads(item.pk_str)[0], report)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return retry_or_give_up("Conflits d'identifiants non résolus")

    def record_pushed_write(item: PendingWrite, result: Dict[str, Any]) -> None:
        if item.row is None:
            conn.execute("DELETE FROM _fs_base WHERE tbl = ? AND pk = ?", (item.table, item.pk_str))
            report["deleted"] = report.get("deleted", 0) + 1
        else:
            base, _ = _get_base(conn, item.table, item.pk_str)
            new_base = dict(base or {})
            new_base.update(item.row if item.write.get("mask") is None else item.write["fields"])
            _set_base(conn, item.table, item.pk_str, new_base, result.get("update_time"))
            report["pushed"] = report.get("pushed", 0) + 1
        conn.execute("DELETE FROM _fs_changes WHERE tbl = ? AND pk = ? AND seq <= ?", (item.table, item.pk_str, item.seq))
        touched = report.setdefault("tables", [])
        if item.table not in touched:
            touched.append(item.table)

    conflicts: List[PendingWrite] = []
    for start in range(0, len(pending), COMMIT_CHUNK):
        chunk = pending[start:start + COMMIT_CHUNK]
        try:
            results = store.commit([item.write for item in chunk])
            for item, result in zip(chunk, results, strict=False):
                record_pushed_write(item, result)
        except FirestoreConflictError:
            for item in chunk:
                try:
                    record_pushed_write(item, store.commit([item.write])[0])
                except FirestoreConflictError:
                    conflicts.append(item)
    if conflicts:
        report["conflicts"] = report.get("conflicts", 0) + len(conflicts)
        # Relire les documents en conflit, fusionner, puis renvoyer.
        for table in {item.table for item in conflicts}:
            ids = [item.write["doc_id"] for item in conflicts if item.table == table]
            found = store.get_many(collection_for(table), ids)
            apply_remote_docs(conn, store, table, [d for d in found.values() if d], report)
        return retry_or_give_up(f"{len(conflicts)} écriture(s) en conflit non résolue(s)")
    return report
