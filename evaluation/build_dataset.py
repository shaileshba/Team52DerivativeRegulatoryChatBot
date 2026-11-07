"""One-time dataset authoring helper. The runner reads frozen questions.json only.

Do not regenerate a held-out set to improve scores. Replace it only after a
documented independent review; keep prior run bundles for comparison.
"""
import json
from pathlib import Path

# Provisional retrieval labels from section headings in the supplied PDFs.
CASES = {
1: [
('1.2','Where is liability of a principal for the act of an agent addressed?'),
('1.3','Where are general commodity regulation definitions collected?'),
('1.4','What section addresses electronic signatures and acknowledgments?'),
('1.6','Find the general anti-evasion provision.'),
('1.7','Where are books and records requirements addressed?')],
3: [
('3.1','Find the definitions used in the registration rules.'),
('3.2','Where is registration processing addressed?'),
('3.3','What section addresses the chief compliance officer?'),
('3.4','Does the rule text discuss registration in one capacity and another capacity?'),
('3.10','Find registration provisions for futures commission merchants.')],
22: [
('22.1','Where are cleared swaps collateral definitions located?'),
('22.2','Find the cleared swaps collateral provisions for futures commission merchants.'),
('22.3','Which cleared swaps collateral section addresses derivatives clearing organizations?'),
('22.7','Where is treatment by permitted depositories addressed for cleared swaps collateral?'),
('22.8','Find the situs provision for cleared swaps customer collateral.')],
23: [
('23.21','Where is registration of swap dealers addressed?'),
('23.22','Find the prohibition against statutory disqualification for swap dealers.'),
('23.23','Which section addresses cross-border application for swap dealers?'),
('23.502','What does 23.502 require?'),
('23.101','Where are minimum financial requirements for swap dealers addressed?')],
37: [
('37.1','Find the scope of the swap execution facility rules.'),
('37.3','Where are requirements and procedures for swap execution facility registration?'),
('37.4','Which swap execution facility section covers procedures for listing products?'),
('37.6','Where is enforceability addressed for swap execution facilities?'),
('37.7','Find prohibited use of data collected for regulatory purposes by swap execution facilities.')],
39: [
('39.1','Where is the scope of derivatives clearing organization rules?'),
('39.2','Find definitions for derivatives clearing organizations.'),
('39.3','Where are derivatives clearing organization registration procedures?'),
('39.5','Find the review of swaps for a Commission clearing requirement determination.'),
('39.6','What section discusses exemption from derivatives clearing organization registration?')],
43: [
('43.1','Find the purpose and scope of real-time public reporting.'),
('43.2','Where are real-time swap reporting definitions?'),
('43.3','Which section covers method and timing for real-time public reporting?'),
('43.4','Find swap transaction and pricing data provisions.'),
('43.5','Where are time delays for public dissemination addressed?')],
45: [
('45.1','Where are swap data reporting definitions?'),
('45.2','Find the swap recordkeeping section.'),
('45.3','What does 45.3 require?'),
('45.4','Find continuation data reporting requirements.'),
('45.5','Which section addresses unique transaction identifiers for swap reporting?')],
46: [
('46.1','Find definitions for pre-enactment and transition swaps.'),
('46.2','Where is recordkeeping for pre-enactment swaps addressed?'),
('46.3','Find data reporting for pre-enactment and transition swaps.'),
('46.4','Which section concerns unique identifiers for historical swaps?'),
('46.6','Where is third-party facilitation of data reporting for pre-enactment swaps addressed?')],
49: [
('49.1','Find the scope of swap data repository regulations.'),
('49.2','Where are definitions for swap data repositories?'),
('49.3','Find procedures for swap data repository registration.'),
('49.4','Where is withdrawal from swap data repository registration addressed?'),
('49.5','Which section addresses equity interest transfers for swap data repositories?')],
50: [
('50.1','Find clearing requirement definitions.'),
('50.2','Where is treatment of swaps subject to a clearing requirement addressed?'),
('50.3','Which clearing requirement section addresses notice to the public?'),
('50.4','Find classes of swaps required to be cleared.'),
('50.5','Where are swaps exempt from a clearing requirement addressed?')],
150: [
('150.1','Find definitions for speculative position limits.'),
('150.2','Where are federal speculative position limits addressed?'),
('150.3','Find exemptions from position limits.'),
('150.4','Which section concerns aggregation of positions?'),
('150.5','Where are exchange-set speculative position limits addressed?')],
180: [
('180.1','Find the prohibition on manipulative or deceptive devices.'),
('180.1','Where does the rule discuss a scheme or artifice to defraud?'),
('180.1','What does 180.1 say?'),
('180.1','Find the provision concerning material misstatements and omissions in connection with swaps.'),
('180.2','Where is the prohibition on price manipulation addressed?')]
}

def main():
    questions=[]
    for index,(part,rows) in enumerate(CASES.items()):
        boundary=3 if index<6 else 4
        for i,(citation,question) in enumerate(rows):
            questions.append({'id':f'p{part:03d}-{i+1:02d}','part':part,
                'question':question,'expected_citations':[citation],
                'split':'tuning' if i<boundary else 'held_out',
                'query_type':'section_lookup' if citation in question else 'plain_language'})
    data={'version':'provisional-cftc-v1','label_status':'SME review required',
          'purpose':'Retrieval-only development benchmark; not a regulatory accuracy or release approval set',
          'split_policy':'Frozen query-level stratification by part: 46 tuning / 19 held-out. Every part appears in both. Source corpus is shared; queries are not used for training.',
          'limitations':['Author-created from source section headings; independent SME labels pending.',
                        'Small held-out sample; near-paraphrases and overlapping source sections may overestimate generalization.',
                        'No answer faithfulness, citation support, escalation or readability metrics are claimed.',
                        'Other relevant sections may be omitted from the provisional expected-citation labels.'],
          'questions':questions}
    Path(__file__).with_name('questions.json').write_text(json.dumps(data,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
