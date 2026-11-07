"""Offline retrieval comparison with frozen inputs and deterministic replay.

TF-IDF here is a lexical vector baseline, not a neural embedding substitute.
No classifier, answer generation, or compliance accuracy is evaluated.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sqlite3

from .core import ROOT, connect, now

VERSION = 'retrieval-eval-v1'
METHODS = ['bm25', 'citation_bm25', 'tfidf', 'hybrid_rrf']
CONFIG = {'top_k': 5, 'rrf_k': 60, 'candidate_depth': 50,
          'bm25_weights': [0, 1, 1, 1], 'tokenizer': 'unicode61',
          'tfidf': 'log TF * smoothed IDF; cosine; title and citation once',
          'part_filter': False, 'seed': 52}
STOP = set('what does the a an is are of to in for and explain cftc rule say require requirements part how which under about text describe'.split())

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def tokens(text):
    return [t for t in re.findall(r'[a-z0-9]+', text.lower()) if t not in STOP]

def metrics(expected, retrieved, k=5):
    expected = set(expected)
    if not expected:
        raise ValueError('Retrieval labels must not be empty')
    ranked = list(dict.fromkeys(retrieved))[:k]
    ranks = [i+1 for i, citation in enumerate(ranked) if citation in expected]
    return {'recall_at_5':len(expected.intersection(ranked))/len(expected),
            'mrr_at_5':1/min(ranks) if ranks else 0.0,
            'hit_at_5':float(bool(ranks))}

class Retriever:
    def __init__(self, corpus):
        self.rows = sorted(corpus, key=lambda r:r['id'])
        self.by_id = {r['id']:r for r in self.rows}
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE VIRTUAL TABLE docs USING fts5(id UNINDEXED,text,citation,heading, tokenize="unicode61")')
        self.db.executemany('INSERT INTO docs VALUES(?,?,?,?)', [(r['id'],r['text'],r['citation'],r['heading']) for r in self.rows])
        counts = [Counter(tokens(r['heading']+' '+r['citation']+' '+r['text'])) for r in self.rows]
        df = Counter(t for count in counts for t in count)
        self.idf = {t:math.log((1+len(counts))/(1+n))+1 for t,n in df.items()}
        self.vectors = [self.vector(c) for c in counts]

    def vector(self, counts):
        v = {t:(1+math.log(n))*self.idf[t] for t,n in counts.items() if t in self.idf}
        norm = math.sqrt(sum(x*x for x in v.values()))
        return {t:w/norm for t,w in v.items()} if norm else {}

    def rank(self, question, method):
        ts = sorted(set(tokens(question)))
        query = ' OR '.join('"'+t+'"' for t in ts)
        bm = self.db.execute('SELECT id,-bm25(docs) AS score FROM docs WHERE docs MATCH ? ORDER BY bm25(docs), id', (query,)).fetchall() if query else []
        qvec = self.vector(Counter(tokens(question)))
        vec = [(r['id'],sum(w*v.get(t,0) for t,w in qvec.items())) for r,v in zip(self.rows,self.vectors)]
        vec = sorted((r for r in vec if r[1]>0),key=lambda r:(-r[1],r[0]))
        if method == 'bm25':
            ranked = bm
        elif method == 'citation_bm25':
            exact = set(re.findall(r'\b\d{1,3}\.\d+[a-z]?\b',question))
            ranked = [(r['id'],100.0) for r in self.rows if r['citation'] in exact]
            ranked += [r for r in bm if self.by_id[r[0]]['citation'] not in exact]
        elif method == 'tfidf':
            ranked = vec
        elif method == 'hybrid_rrf':
            scores = Counter()
            for listing in [bm,vec]:
                # Fuse section ranks, so duplicate PDF chunks cannot inflate a section.
                seen = set()
                rank = 0
                for ident,_ in listing:
                    citation = self.by_id[ident]['citation']
                    if citation in seen:
                        continue
                    seen.add(citation)
                    rank += 1
                    if rank > CONFIG['candidate_depth']:
                        break
                    scores[citation] += 1/(CONFIG['rrf_k']+rank)
            representatives = {}
            for ident,_ in bm+vec:
                representatives.setdefault(self.by_id[ident]['citation'],ident)
            ranked = [(representatives[c],s) for c,s in sorted(scores.items(),key=lambda x:(-x[1],x[0]))]
        else:
            raise ValueError('Unknown retrieval method')
        results, seen = [],set()
        for ident,score in ranked:
            r = self.by_id[ident]
            if r['citation'] in seen:
                continue
            seen.add(r['citation'])
            results.append({'chunk_id':ident,'citation':r['citation'],'score':score,'page':r['page'],'file':r['file']})
            if len(results)==CONFIG['top_k']:
                break
        return results

def validate(questions, corpus):
    if len({q['id'] for q in questions}) != len(questions):
        raise ValueError('Duplicate question IDs')
    citations = {r['citation'] for r in corpus}
    for q in questions:
        if q['split'] not in {'tuning','held_out'} or not q['expected_citations'] or not set(q['expected_citations']) <= citations:
            raise ValueError('Invalid split or missing corpus label: '+q['id'])
        if any(int(c.split('.')[0]) != q['part'] for c in q['expected_citations']):
            raise ValueError('Part does not match label: '+q['id'])

def evaluate(corpus, questions, split):
    validate(questions, corpus)
    retriever = Retriever(corpus)
    selected = [q for q in questions if q['split']==split]
    if not selected:
        raise ValueError('No questions in selected split')
    outcomes=[]
    for q in selected:
        for method in METHODS:
            hits = retriever.rank(q['question'],method)
            scores = metrics(q['expected_citations'],[h['citation'] for h in hits])
            outcomes.append({**q,'method':method,'retrieved':hits,'metrics':scores,
                             'pass':scores['recall_at_5']==1})
    summary={}
    for method in METHODS:
        rows = [r for r in outcomes if r['method']==method]
        summary[method]={'questions':len(rows),**{m:sum(r['metrics'][m] for r in rows)/len(rows) for m in rows[0]['metrics']},
                         'by_part':{str(p):{m:sum(r['metrics'][m] for r in rows if r['part']==p)/sum(r['part']==p for r in rows) for m in rows[0]['metrics']} for p in sorted({r['part'] for r in rows})}}
    return {'summary':summary,'per_question':outcomes}

def run(dataset, output, split):
    questions=json.loads(dataset.read_text(encoding='utf-8'))
    with connect() as db:
        snap=db.execute('SELECT s.* FROM snapshots s JOIN live l ON l.snapshot=s.id').fetchone()
        if not snap:
            raise ValueError('Run python -m app.ingest first')
        corpus=[dict(r) for r in db.execute('SELECT * FROM chunks WHERE snapshot=? ORDER BY id',(snap['id'],))]
    result=evaluate(corpus,questions['questions'],split)
    stamp=now()
    run_id=stamp.replace(':','').replace('.','').replace('+','_')+'_'+digest([corpus,questions,split])[:10]
    folder=output/run_id
    folder.mkdir(parents=True,exist_ok=False)
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['manifest']={'run_id':run_id,'created_at':stamp,'evaluation_version':VERSION,
       'evaluator_sha256':source_hash,'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
       'corpus_snapshot':snap['id'],'corpus_manifest':json.loads(snap['manifest']),
       'corpus_sha256':digest(corpus),'dataset_sha256':digest(questions),
       'dataset_metadata':{k:v for k,v in questions.items() if k!='questions'},
       'split':split,'config':CONFIG,'methods':METHODS,'embedding_model':'none; lexical TF-IDF only',
       'prompt_version':'none','llm':'none','release_gate':'not evaluated; provisional labels require SME approval',
       'split_counts':dict(Counter(q['split'] for q in questions['questions']))}
    for name,value in [('corpus.json',corpus),('questions.json',questions),('results.json',result)]:
        (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return folder/'results.json',result

def replay(path):
    saved=json.loads(path.read_text(encoding='utf-8'))
    corpus=json.loads((path.parent/'corpus.json').read_text(encoding='utf-8'))
    dataset=json.loads((path.parent/'questions.json').read_text(encoding='utf-8'))
    m=saved['manifest']
    for actual,expected,label in [(digest(corpus),m['corpus_sha256'],'corpus'),(digest(dataset),m['dataset_sha256'],'dataset'),(hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),m['evaluator_sha256'],'evaluator')]:
        if actual != expected:
            raise ValueError(label+' hash mismatch; replay refused')
    if m['config'] != CONFIG or m['methods'] != METHODS or m['sqlite'] != sqlite3.sqlite_version or m['python'] != platform.python_version():
        raise ValueError('Replay configuration/runtime differs from manifest')
    repeated=evaluate(corpus,dataset['questions'],m['split'])
    if canonical(repeated) != canonical({k:saved[k] for k in ['summary','per_question']}):
        raise ValueError('Replay results differ')
    return repeated

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'evaluation/questions.json')
    parser.add_argument('--output',type=Path,default=ROOT/'eval_runs')
    parser.add_argument('--split',choices=['tuning','held_out'],default='held_out')
    parser.add_argument('--replay',type=Path)
    args=parser.parse_args()
    if args.replay:
        replay(args.replay)
        print('Replay matched all rankings, scores, and metrics:',args.replay)
    else:
        path,result=run(args.dataset,args.output,args.split)
        print(path)
        print(json.dumps(result['summary'],indent=2))

if __name__=='__main__':
    main()
