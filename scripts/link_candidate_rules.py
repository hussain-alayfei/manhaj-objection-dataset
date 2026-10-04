"""Suggest book-backed rule references. This never approves rules or objections."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from src.db import Store
from src.export import export_snapshots

load_dotenv();store=Store();rules=store.records('rule');count=0
for objection in store.records('objection',phase=1):
    candidates=[r for r in rules if r['source']['source_id']==objection['source']['source_id']]
    if not candidates:continue
    # First-page statement is a methodological source proposal, not an approved rule.
    rule=next((r for r in candidates if r['source']['page_number']==1 and 'أن الشريعة لا تفرق' in r['source']['source_excerpt']),candidates[0])
    changes={'methodology_rule_ids':[rule['id']],'methodology_rule_ar':rule['methodology_rule_ar']}
    count+=store.add_machine_proposal(objection['id'],changes,'source_rule_link_v1')
export_snapshots(store)
print({'linked_candidates':count,'approved_records':len(store.eligible())})
