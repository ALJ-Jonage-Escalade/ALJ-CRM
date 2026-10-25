"""Réception (`pull`) et envoi (`flush`) des modifications entre le cache et Firestore."""
import datetime
import json
import sqlite3
from typing import Any, Dict, List, Optional

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
    CloudConflictError,
    _same,
    collection_for,
    doc_id_for,
    ts_key,
    ts_minus,
)

def renumber_row(conn, store, table: str, old_id: int, report: Dict[str, Any]) -> int:
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


def apply_remote_docs(conn, store, table: str, docs: List[Dict[str, Any]], report: Dict[str, Any]):
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
                remote = {c: d["fields"][c] for c in cols if c in d["fields"]}
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



def pull(conn, store, report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Récupère les documents modifiés depuis la dernière synchronisation."""
    report = report if report is not None else {}
    for t in tracked_tables(conn):
        coll = collection_for(t)
        wm = get_state(conn, f"wm:{t}") or "1970-01-01T00:00:00Z"
        docs = store.list_modified_since(coll, ts_minus(wm, PULL_MARGIN_SECONDS))
        apply_remote_docs(conn, store, t, docs, report)
        if docs:
            newest = max((d["modified_at"] for d in docs if d.get("modified_at")), key=ts_key, default=wm)
            if ts_key(newest) > ts_key(wm):
                set_state(conn, f"wm:{t}", newest)
    set_state(conn, "last_pull", datetime.datetime.now().isoformat(timespec="seconds"))
    return report


def _build_write(conn, table: str, cols: List[str], pk: List[str], pk_str: str, by: str):
    """Prépare l'écriture d'une ligne modifiée. Retourne (write, row, base) ou None."""
    vals = json.loads(pk_str)
    row = _read_row(conn, table, pk, vals)
    base, base_ut = _get_base(conn, table, pk_str)
    w = {"collection": collection_for(table), "doc_id": doc_id_for(vals), "by": by}
    if row is None:
        if base is None:
            return None
        w.update(fields={c: v for c, v in zip(pk, vals, strict=False)}, mask=None, deleted=True,
                 precondition={"updateTime": base_ut} if base_ut else None)
        return w, None
    if base is None:
        w.update(fields=row, mask=None, deleted=False, precondition=None, create=True)
        return w, row
    diff = {c: v for c, v in row.items() if c not in base or not _same(v, base.get(c))}
    if not diff:
        return {"noop": True}, row
    w.update(fields=diff, mask=list(diff.keys()), deleted=False,
             precondition={"updateTime": base_ut} if base_ut else {"exists": True})
    return w, row


def flush(conn, store, by: str = "", report: Optional[Dict[str, Any]] = None,
          _depth: int = 0) -> Dict[str, Any]:
    """Envoie les lignes modifiées localement vers Firestore."""
    report = report if report is not None else {}
    changes = conn.execute("SELECT tbl, pk, seq FROM _fs_changes ORDER BY seq").fetchall()
    if not changes:
        return report
    meta = {}
    items = []  # (table, pk_str, seq, write, row)
    for ch in changes:
        t, pk_str, seq = ch["tbl"], ch["pk"], ch["seq"]
        if t not in meta:
            if not table_exists(conn, t):
                conn.execute("DELETE FROM _fs_changes WHERE tbl = ?", (t,))
                continue
            meta[t] = (table_columns(conn, t), table_pk(conn, t))
        cols, pk = meta[t]
        built = _build_write(conn, t, cols, pk, pk_str, by)
        if built is None or built[0].get("noop"):
            row = None if built is None else built[1]
            conn.execute("DELETE FROM _fs_changes WHERE tbl = ? AND pk = ? AND seq <= ?", (t, pk_str, seq))
            continue
        items.append((t, pk_str, seq, built[0], built[1]))

    # Créations : vérifier que l'ID n'est pas déjà pris (tombe => on écrase la tombe)
    collisions = []
    by_table: Dict[str, List[int]] = {}
    for i, it in enumerate(items):
        if it[3].get("create"):
            by_table.setdefault(it[0], []).append(i)
    for t, idxs in by_table.items():
        found = store.get_many(collection_for(t), [items[i][3]["doc_id"] for i in idxs])
        for i in idxs:
            w = items[i][3]
            remote = found.get(w["doc_id"])
            if remote is None:
                w["precondition"] = {"exists": False}
            elif remote["deleted"]:
                w["precondition"] = {"updateTime": remote["update_time"]}
            else:
                same = all(_same(remote["fields"].get(c), v) for c, v in items[i][4].items())
                if same or len(meta[t][1]) != 1 or not isinstance(json.loads(items[i][1])[0], int):
                    # Contenu identique, ou clé « métier » (texte) : on adopte / écrase.
                    w["precondition"] = {"updateTime": remote["update_time"]}
                else:
                    collisions.append(i)
    if collisions:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for i in collisions:
                renumber_row(conn, store, items[i][0], json.loads(items[i][1])[0], report)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        if _depth < 3:
            return flush(conn, store, by, report, _depth + 1)
        report.setdefault("errors", []).append("Conflits d'identifiants non résolus")
        return report

    def done(it, res):
        t, pk_str, seq, w, row = it
        if row is None:
            conn.execute("DELETE FROM _fs_base WHERE tbl = ? AND pk = ?", (t, pk_str))
            report["deleted"] = report.get("deleted", 0) + 1
        else:
            base, _ = _get_base(conn, t, pk_str)
            new_base = dict(base or {})
            new_base.update(row if w.get("mask") is None else w["fields"])
            _set_base(conn, t, pk_str, new_base, res.get("update_time"))
            report["pushed"] = report.get("pushed", 0) + 1
        conn.execute("DELETE FROM _fs_changes WHERE tbl = ? AND pk = ? AND seq <= ?", (t, pk_str, seq))
        touched = report.setdefault("tables", [])
        if t not in touched:
            touched.append(t)

    conflicts = []
    for start in range(0, len(items), COMMIT_CHUNK):
        chunk = items[start:start + COMMIT_CHUNK]
        try:
            results = store.commit([it[3] for it in chunk])
            for it, res in zip(chunk, results, strict=False):
                done(it, res)
        except CloudConflictError:
            for it in chunk:
                try:
                    res = store.commit([it[3]])[0]
                    done(it, res)
                except CloudConflictError:
                    conflicts.append(it)
    if conflicts:
        report["conflicts"] = report.get("conflicts", 0) + len(conflicts)
        # Relire les documents en conflit, fusionner, puis renvoyer.
        for t in {it[0] for it in conflicts}:
            ids = [it[3]["doc_id"] for it in conflicts if it[0] == t]
            found = store.get_many(collection_for(t), ids)
            apply_remote_docs(conn, store, t, [d for d in found.values() if d], report)
        if _depth < 3:
            return flush(conn, store, by, report, _depth + 1)
        report.setdefault("errors", []).append(f"{len(conflicts)} écriture(s) en conflit non résolue(s)")
    return report
