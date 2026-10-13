"""SQLite is the source of truth. One transaction per user change."""
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from .schema import Invalid, validate, validate_assertion


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
          INSERT OR IGNORE INTO meta VALUES(1,0);
          CREATE TABLE IF NOT EXISTS assertions (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, source TEXT NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','retracted')),
            retracted_at TEXT, supersedes TEXT REFERENCES assertions(id), event_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, operation TEXT NOT NULL, source TEXT NOT NULL,
            proposal TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')

        from .semantic import install
        install(self.db)

    def note(self, source, explanation):
        from .semantic import now
        ident = "n_" + uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO source_notes VALUES(?,?,?,?)", (ident, source, explanation, now()))
        return ident

    def close(self):
        self.db.close()

    def snapshot(self, active_only=True):
        with self.db:
            self.db.execute("BEGIN")
            revision = self.db.execute("SELECT revision FROM meta WHERE id=1").fetchone()[0]
            sql = "SELECT * FROM assertions" + (" WHERE status='active'" if active_only else "") + " ORDER BY rowid"
            rows = [dict(row) for row in self.db.execute(sql)]
        for row in rows:
            row["assertion"] = json.loads(row.pop("payload"))
            validate_assertion(row["assertion"])
        return revision, rows

    def candidates(self, text, explicit_id=None, limit=12):
        revision, rows = self.snapshot()
        tokens = set(re.findall(r"[a-z0-9_-]+", text.lower()))
        ranked = []
        for row in rows:
            if explicit_id:
                score = 100 if row["id"] == explicit_id else 0
            else:
                atoms = [row["assertion"]["head"]] + row["assertion"]["body"]
                names = {t["const"].split(":", 1)[1] for a in atoms for t in a["args"] if "const" in t}
                normalized = " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "
                score = sum(name in tokens or " " + name.replace("_", " ").replace("-", " ") + " " in normalized for name in names)
                if row["id"] in tokens:
                    score += 100
            if score:
                ranked.append((score, row))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        if explicit_id and not ranked:
            raise Invalid("Explicit target is missing or retracted")
        return revision, [row for _, row in ranked[:limit]], len(ranked) > limit

    def apply(self, operation, source, proposal, revision, allowed_targets):
        validate(proposal, operation, allowed_targets)
        if proposal["status"] != "ok" or operation == "ask":
            raise Invalid("No mutation to apply")
        now = datetime.now(timezone.utc).isoformat()
        event = "e_" + uuid.uuid4().hex
        created = []
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current = self.db.execute("SELECT revision FROM meta WHERE id=1").fetchone()[0]
            if current != revision:
                raise Invalid("Knowledge changed during translation. Retry against fresh candidates.")
            for target in proposal["targets"]:
                count = self.db.execute("UPDATE assertions SET status='retracted', retracted_at=? WHERE id=? AND status='active'", (now, target)).rowcount
                if count != 1:
                    raise Invalid("Target is no longer active")
            active = self.db.execute("SELECT count(*) FROM assertions WHERE status='active'").fetchone()[0]
            if active + len(proposal["assertions"]) > 1000:
                raise Invalid("Prototype active assertion limit (1000) exceeded")
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (event, operation, source, json.dumps(proposal), now))
            for item in proposal["assertions"]:
                ident = "a_" + uuid.uuid4().hex
                self.db.execute("INSERT INTO assertions VALUES(?,?,?,?,?,?,?,?)", (ident, json.dumps(item), source, now, "active", None, next(iter(proposal["targets"]), None), event))
                created.append(ident)
            self.db.execute("UPDATE meta SET revision=revision+1 WHERE id=1")
        return {"created": created, "retracted": proposal["targets"], "revision": revision + 1}

    def import_records(self, records, source):
        """Atomic reviewed domain fixture import, retaining each original source."""
        if not isinstance(records,list) or not 1 <= len(records) <= 1000:
            raise Invalid('Import requires 1–1000 source/assertion records')
        for record in records:
            if set(record) != {'source','assertion'} or not isinstance(record['source'],str) or not record['source'].strip():
                raise Invalid('Import entries need original source and assertion')
            validate_assertion(record['assertion'])
        event='e_'+uuid.uuid4().hex
        timestamp=datetime.now(timezone.utc).isoformat()
        ids=[]
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            count=self.db.execute("SELECT count(*) FROM assertions WHERE status='active'").fetchone()[0]
            if count+len(records)>1000: raise Invalid('Active assertion limit exceeded')
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',(event,'import',source,json.dumps(records),timestamp))
            for record in records:
                ident='a_'+uuid.uuid4().hex;ids.append(ident)
                self.db.execute('INSERT INTO assertions VALUES(?,?,?,?,?,?,?,?)',
                    (ident,json.dumps(record['assertion']),record['source'],timestamp,'active',None,None,event))
            self.db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
        return {'created':ids,'event':event}

    def events(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM events ORDER BY rowid")]
