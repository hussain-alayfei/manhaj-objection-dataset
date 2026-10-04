"""Create an operator-controlled identity. Only the token's SHA-256 is stored; the token is shown once.

Use --token-out to write the token to a private file instead of printing it, e.g. when creating
production reviewers whose hashes go into REVIEWER_TOKEN_HASHES on the hosting platform.
"""
import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

p = argparse.ArgumentParser()
p.add_argument('reviewer_id')
p.add_argument('--env-file', default='.env')
p.add_argument('--token-out', help='write the token to this file (created with owner-only permissions) and print nothing secret')
args = p.parse_args()
path = Path(args.env_file)
path.touch(exist_ok=True)
current = json.loads(dotenv_values(path).get('REVIEWER_TOKEN_HASHES') or '{}')
if args.reviewer_id in current: raise SystemExit('Reviewer exists. Remove its hash deliberately to rotate the token.')
token = secrets.token_urlsafe(36)
current[args.reviewer_id] = hashlib.sha256(token.encode()).hexdigest()
set_key(path, 'REVIEWER_TOKEN_HASHES', json.dumps(current, separators=(',', ':')), quote_mode='never')
print('Reviewer:', args.reviewer_id, '| hashes in', path)
if args.token_out:
    out = Path(args.token_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f: f.write(token + '\n')
    print('Token written to', out, '- hand it to the reviewer privately, then delete the file.')
else:
    print('Save this secret in your password manager; it is shown only once:')
    print(token)
