from fastapi.testclient import TestClient
from app.main import app
from app.core import classify

client = TestClient(app)

def test_classification():
    for q in ['Is our process compliant?', 'We did X, is that OK?', 'Explain enforcement actions']:
        assert classify(q) == 'escalate'
    assert classify('What does EMIR require?') == 'out_of_scope'
    assert classify('What changed in Part 45 in 2020?') == 'historical'
    assert classify('account number 123456789') == 'sensitive_data'
    assert classify('What does 45.3 require?') == 'explain'

def test_requires_acknowledgement():
    assert client.post('/api/chat', json={'question':'What does 45.3 require?'}).status_code == 400

def test_escalation_does_not_retrieve():
    r = client.post('/api/chat', json={'question':'Is our process compliant?', 'acknowledged':True}).json()
    assert r['classification'] == 'escalate'
    assert r['citations'] == []
    handoff = client.post('/api/escalations', json={'answer_id':r['id']}).json()
    assert handoff['status'] == 'Prepared locally; not sent'

def test_source_is_verbatim_and_versioned():
    r = client.post('/api/chat', json={'question':'What does 45.3 require?', 'acknowledged':True}).json()
    assert r['citations'], 'Ingest the supplied corpus before running integration tests'
    for c in r['citations']:
        s = client.get(c['url']).json()
        assert c['quote'] == s['text']
        assert c['snapshot'] == s['snapshot']
        assert c['citation'] == '17 CFR 45.3'
    assert client.post('/api/feedback',json={'answer_id':r['id'],'rating':1}).status_code == 200

def test_sensitive_question_not_stored():
    from app.core import connect
    q='account number 123456789'
    r=client.post('/api/chat',json={'question':q,'acknowledged':True}).json()
    with connect() as db:
        payload=db.execute('SELECT payload FROM audit WHERE id=?',(r['id'],)).fetchone()[0]
    assert q not in payload
    assert client.post('/api/escalations',json={'answer_id':r['id']}).status_code == 400

def test_invalid_part_and_source():
    assert client.post('/api/chat',json={'question':'What does the rule say?', 'part':99, 'acknowledged':True}).status_code == 400
    assert client.get('/api/sources/nonexistent').status_code == 404
