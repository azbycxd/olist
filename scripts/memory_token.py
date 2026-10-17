"""Local administrator token issuance until interactive login in Step 8."""
import argparse
import psycopg
from config import db_kwargs
from api.memories import issue

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username',required=True)
    args=parser.parse_args()
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        row=conn.execute('SELECT user_id FROM users WHERE username=%s',(args.username,)).fetchone()
    if not row: raise SystemExit('Unknown user')
    print(issue(row[0]))
