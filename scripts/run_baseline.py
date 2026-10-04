"""Evaluate a configured analyst using only the frozen training retrieval pool."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from src.db import Store, digest
from src.classification import diagnose
from src.evaluation import evaluate_predictions
from src.evaluation.benchmark import leakage_groups

load_dotenv()
p=argparse.ArgumentParser();p.add_argument('manifest_id');p.add_argument('--output',default='data/benchmark/baseline-predictions.json');args=p.parse_args()
store=Store();manifest=next(x['payload'] for x in store.list_documents('dataset_manifests') if x['id']==args.manifest_id)
training=set(manifest['training_ids'])
exclude={r['id'] for r in store.records('objection') if r['id'] not in training}
for group in leakage_groups(store):
    if exclude.intersection(group):exclude.update(group)
predictions={}
for item in manifest['records']:
    if item['id'] not in manifest['test_ids']:continue
    if digest(store.get(item['id']))!=item['hash']:raise ValueError('Frozen benchmark changed')
    predictions[item['id']]=diagnose(store,item['snapshot']['objection_text_ar'],exclude_ids=exclude,persist=False)
path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(predictions,ensure_ascii=False,indent=2),encoding='utf-8')
result=evaluate_predictions(store,args.manifest_id,predictions)
print(json.dumps(result['metrics'],ensure_ascii=False,indent=2))
