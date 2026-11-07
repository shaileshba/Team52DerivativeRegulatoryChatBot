"""Build a candidate index transactionally; activate only complete, nonempty parts."""
import hashlib
import json
import re
from pypdf import PdfReader
from .core import ROOT, PARTS, connect, now

def ingest():
    files = sorted((ROOT / 'RAGData').glob('CFTC_17CFR_Part*_2025.pdf'))
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest['parser_version'] = 'reading-order-v2'
    snapshot = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    with connect() as db:
        if db.execute('SELECT 1 FROM snapshots WHERE id=?', (snapshot,)).fetchone():
            print('Snapshot already indexed:', snapshot)
            return snapshot
        counts = {}
        for path in files:
            part = int(re.search(r'Part(\d+)', path.name)[1])
            if part not in PARTS:
                continue
            current = None
            def flush():
                if not current or len(current['text'].strip()) < 30:
                    return
                text = current['text'].strip()
                ident = hashlib.sha256((snapshot+path.name+str(current['page'])+current['citation']+text).encode()).hexdigest()[:24]
                db.execute('INSERT OR IGNORE INTO chunks VALUES(?,?,?,?,?,?,?,?,?)', (ident, snapshot, part, current['citation'], current['heading'], text, path.name, current['page'], '2025 supplied PDF; effective date unverified'))
                db.execute('INSERT INTO search(id,text,citation,heading) VALUES(?,?,?,?)', (ident, text, current['citation'], current['heading']))
                counts[part] = counts.get(part, 0)+1
            for page_num, page in enumerate(PdfReader(path).pages, 1):
                text = page.extract_text() or ''
                for line in text.splitlines():
                    line = line.strip()
                    match = re.match(r'^§\s*('+str(part)+r'\.\d+[a-z]?)\s+(.*)', line)
                    if match:
                        flush()
                        current = dict(citation=match[1], heading=match[2], text=line+'\n', page=page_num)
                    elif current:
                        current['text'] += line+'\n'
            flush()
            print(path.name, counts.get(part, 0), 'sections', flush=True)
        if set(counts) != set(PARTS) or any(n < 1 for n in counts.values()):
            raise RuntimeError('Candidate rejected: missing or empty parts; previous index remains live')
        manifest['section_counts'] = counts
        manifest['validation'] = 'Structural check only; SME held-out evaluation and TOC reconciliation pending'
        db.execute('INSERT INTO snapshots VALUES(?,?,?)', (snapshot, now(), json.dumps(manifest)))
        db.execute('INSERT OR REPLACE INTO live VALUES(1,?)', (snapshot,))
    print('Activated local snapshot:', snapshot)
    return snapshot

if __name__ == '__main__':
    ingest()
