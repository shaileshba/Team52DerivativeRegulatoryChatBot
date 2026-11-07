"""Explicit, extractive retrieval pipeline. Never generates regulatory claims."""
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
PARTS = [1, 3, 22, 23, 37, 39, 43, 45, 46, 49, 50, 150, 180]
FOOTER = 'This explains the rule text. It is not a compliance determination. Contact Compliance for decisions.'

def connect():
    DATA.mkdir(exist_ok=True)
    db = sqlite3.connect(DATA / 'corpus.sqlite', timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, created TEXT, manifest TEXT);
      CREATE TABLE IF NOT EXISTS live(singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot TEXT);
      CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, snapshot TEXT, part INTEGER,
        citation TEXT, heading TEXT, text TEXT, file TEXT, page INTEGER, version TEXT);
      CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, text, citation, heading);
      CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, created TEXT, payload TEXT);
      CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, answer_id TEXT, rating INTEGER, created TEXT);
      CREATE TABLE IF NOT EXISTS escalations(id TEXT PRIMARY KEY, answer_id TEXT, created TEXT);
    ''')
    return db

def now():
    return datetime.now(timezone.utc).isoformat()

def classify(question):
    q = question.lower()
    if re.search(r'\b[A-Z0-9]{18}[0-9]{2}\b|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}|\b\d{8,}\b|\b(account|client|customer|trade)\s*(number|id|name|#)\s*[:=]?\s*\S+', question, re.I):
        return 'sensitive_data'
    if re.search(r'\b(emir|mifid|sec|fca|basel|bitcoin|weather|recipe)\b', q):
        return 'out_of_scope'
    if re.search(r'\b(our|my|we|client|customer|compliant|compliance determination|breach|enforcement|regulator correspondence|can i|can we|should i|should we|is it ok|is this allowed)\b', q):
        return 'escalate'
    if re.search(r'\b(changed?|compare|previous|historical|2020|2024)\b', q):
        return 'historical'
    return 'explain'

def retrieve(db, question, part=None):
    live = db.execute('SELECT snapshot FROM live WHERE singleton=1').fetchone()
    if not live:
        return []
    snap = live[0]
    exact = re.findall(r'\b\d{1,3}\.\d+[a-z]?\b', question)
    rows = []
    if exact:
        marks = ','.join('?' for _ in exact)
        rows = db.execute(f'SELECT *, 100.0 AS score FROM chunks WHERE snapshot=? AND citation IN ({marks})' + (' AND part=?' if part else '') + ' LIMIT 5', [snap, *exact, *([part] if part else [])]).fetchall()
    if not rows:
        stop = {'what','does','the','a','an','is','are','of','to','in','for','and','explain','cftc','rule','say','require','requirements','part','how','which','under'}
        terms = [t for t in re.findall(r'[a-zA-Z]{3,}', question.lower()) if t not in stop][:16]
        if not terms:
            return []
        query = ' OR '.join('"' + t + '"' for t in terms)
        rows = db.execute('SELECT c.*, -bm25(search) AS score FROM search JOIN chunks c ON c.id=search.id WHERE search MATCH ? AND c.snapshot=?' + (' AND c.part=?' if part else '') + ' ORDER BY bm25(search) LIMIT 5', [query, snap, *([part] if part else [])]).fetchall()
    return [dict(r) for r in rows]

def answer(question, part=None):
    category = classify(question)
    result = dict(id=str(uuid.uuid4()), classification=category, citations=[], footer=FOOTER,
                  limitations='The supplied corpus is a 2025 snapshot. It does not establish the current rule, applicability to a specific case, or subsequent amendments.',
                  pipeline_version='extractive-v1', model='none', question=question)
    messages = {
      'sensitive_data': 'Please remove personal, client, account and trade identifiers before submitting a general rule question. This question was not retained.',
      'out_of_scope': 'This assistant covers only the 13 selected CFTC parts. It cannot answer this question from its approved corpus.',
      'escalate': 'This question needs a Compliance judgment. No regulatory determination has been made. You can prepare a Compliance hand-off below.',
      'historical': 'A version comparison needs multiple approved snapshots. Only the supplied 2025 PDFs are available; please refer this question to Compliance.'
    }
    with connect() as db:
        if category in messages:
            result['answer'] = messages[category]
        else:
            hits = retrieve(db, question, part)
            if not hits:
                result.update(classification='low_confidence', answer='No sufficiently identifiable source was found in the local corpus. Please refine the section number or refer the question to Compliance.')
            else:
                # Exact stored excerpts are the only substantive output in local mode.
                result['answer'] = 'The following passages were retrieved from the supplied rule text. Read the full section and its conditions before drawing conclusions. A plain-language synthesis requires an approved model and validation; this local mode returns source excerpts only.'
                for h in hits[:3]:
                    result['citations'].append(dict(id=h['id'], citation='17 CFR '+h['citation'], heading=h['heading'], quote=h['text'], version=h['version'], page=h['page'], file=h['file'], snapshot=h['snapshot'], url='/api/sources/'+h['id'], score=h['score']))
                result['classification'] = 'source_excerpts'
        stored = {**result, 'question': '[BLOCKED]' if category == 'sensitive_data' else question}
        db.execute('INSERT INTO audit VALUES(?,?,?)', (result['id'], now(), json.dumps(stored)))
    return result
