import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from src.db import Store

load_dotenv();store=Store();counts={};total=0
with store.engine.connect() as c:
    for r in store.records():
        schema_name={'objection':'objection','rule':'methodology-rule','family':'objection-family'}[r['kind']]
        schema=json.loads(Path(f'schemas/{schema_name}.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(r)
        if r['kind']!='family':store.verify_source(r,c)
        counts[r['review_status']]=counts.get(r['review_status'],0)+1;total+=1
print(json.dumps({'validated_records':total,'status_counts':counts,'source_spans':'all_verified_against_extracted_text','visual_verification':'human_review_required'},ensure_ascii=False))
