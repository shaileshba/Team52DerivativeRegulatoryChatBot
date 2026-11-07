import json
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import ROOT, PARTS, answer, connect, now

app = FastAPI(title='CFTC Regulatory Assistant', version='0.1.0')

class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    part: int | None = None
    acknowledged: bool = False

class Feedback(BaseModel):
    answer_id: str
    rating: int = Field(ge=1, le=5)

class Escalation(BaseModel):
    answer_id: str

@app.get('/api/status')
def status():
    with connect() as db:
        live = db.execute('SELECT s.* FROM live l JOIN snapshots s ON s.id=l.snapshot').fetchone()
        return {'mode':'Local extractive pilot', 'production_ready':False, 'parts':PARTS,
                'snapshot':dict(live) if live else None,
                'sections':db.execute('SELECT count(*) FROM chunks WHERE snapshot=(SELECT snapshot FROM live)').fetchone()[0]}

@app.post('/api/chat')
def chat(q: Question):
    if not q.acknowledged:
        raise HTTPException(400, 'Acknowledge the first-use disclosure')
    if q.part is not None and q.part not in PARTS:
        raise HTTPException(400, 'Part is outside the approved scope')
    return answer(q.question.strip(), q.part)

@app.get('/api/sources/{ident}')
def source(ident: str):
    with connect() as db:
        row = db.execute('SELECT * FROM chunks WHERE id=?', (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Source not found')
        return dict(row)

@app.get('/api/pdf/{ident}')
def pdf(ident: str):
    row = source(ident)
    return FileResponse(ROOT / 'RAGData' / row['file'], media_type='application/pdf')

@app.post('/api/feedback')
def feedback(f: Feedback):
    with connect() as db:
        if not db.execute('SELECT 1 FROM audit WHERE id=?', (f.answer_id,)).fetchone():
            raise HTTPException(404, 'Answer not found')
        db.execute('INSERT INTO feedback VALUES(?,?,?,?)', (str(uuid.uuid4()), f.answer_id, f.rating, now()))
    return {'saved':True}

@app.post('/api/escalations')
def escalate(e: Escalation):
    with connect() as db:
        row = db.execute('SELECT payload FROM audit WHERE id=?', (e.answer_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Answer not found')
        payload = json.loads(row[0])
        if payload['classification'] == 'sensitive_data':
            raise HTTPException(400, 'Remove sensitive data and resubmit')
        ident = str(uuid.uuid4())
        db.execute('INSERT INTO escalations VALUES(?,?,?)', (ident, e.answer_id, now()))
    return {'id':ident, 'status':'Prepared locally; not sent', 'question':payload['question'], 'answer_id':e.answer_id, 'snapshot': [c['snapshot'] for c in payload['citations']]}

app.mount('/', StaticFiles(directory=ROOT / 'web', html=True), name='web')
