import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models import Record, Citation, ReviewRequest

folder = Path('schemas'); folder.mkdir(exist_ok=True)
for filename, cls, kind in [('objection', Record, 'objection'), ('methodology-rule', Record, 'rule'), ('objection-family', Record, 'family'), ('source', Citation, None), ('review', ReviewRequest, None)]:
    schema = cls.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = f'https://manhaj.local/schemas/{filename}.schema.json'
    if kind: schema['properties']['kind'] = {'const': kind, 'type': 'string'}
    (folder / f'{filename}.schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')
