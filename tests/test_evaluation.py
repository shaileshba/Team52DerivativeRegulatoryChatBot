import json
import pytest
from app.evaluate import Retriever, metrics, replay, run

def corpus():
    return [dict(id='a',text='alpha collateral segregation',heading='Collateral',citation='22.2',page=1,file='a.pdf'),
            dict(id='b',text='beta trade reporting',heading='Reporting',citation='45.3',page=2,file='b.pdf'),
            dict(id='c',text='alpha collateral',heading='Collateral continued',citation='22.2',page=3,file='a.pdf')]

def test_metrics_use_unique_section_ranks():
    result=metrics(['22.2','45.3'],['99.1','22.2','22.2','45.3'])
    assert result == {'recall_at_5':1,'mrr_at_5':0.5,'hit_at_5':1}
    assert metrics(['22.2'],['99.1'])['mrr_at_5']==0

def test_exact_lookup_and_deduplication():
    retriever=Retriever(corpus())
    for method in ['bm25','citation_bm25','tfidf','hybrid_rrf']:
        rows=retriever.rank('alpha collateral',method)
        assert len({r['citation'] for r in rows})==len(rows)
    assert retriever.rank('Where is 45.3?', 'citation_bm25')[0]['citation']=='45.3'
    assert retriever.rank('unfindable', 'bm25')==[]

def test_frozen_split_coverage():
    from app.core import ROOT, PARTS
    questions=json.loads((ROOT/'evaluation/questions.json').read_text())['questions']
    assert len(questions)==65
    assert sum(q['split']=='held_out' for q in questions)==19
    for split in ['tuning','held_out']:
        assert {q['part'] for q in questions if q['split']==split}==set(PARTS)
    assert len({q['question'] for q in questions})==len(questions)

def test_saved_run_replays_and_detects_tampering(tmp_path):
    from app.core import ROOT
    path,result=run(ROOT/'evaluation/questions.json',tmp_path,'held_out')
    assert len(result['per_question'])==19*4
    assert replay(path)['summary']==result['summary']
    frozen=json.loads((path.parent/'questions.json').read_text())
    frozen['questions'][0]['question']='tampered'
    (path.parent/'questions.json').write_text(json.dumps(frozen))
    with pytest.raises(ValueError,match='dataset hash mismatch'):
        replay(path)
