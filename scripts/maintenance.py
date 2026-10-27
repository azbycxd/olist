"""Explicit audited retention and user erasure; no automatic destructive startup work."""
import argparse
import json
from uuid import UUID
import psycopg
from config import db_kwargs,RETENTION_DAYS


def retain(conn,days=RETENTION_DAYS):
    return conn.execute('SELECT retain_task_details(%s)',(days,)).fetchone()[0]


def delete_user(conn,owner):
    from scripts.rate_limits import abandon_task
    owner=UUID(str(owner))
    conn.execute('SELECT pg_advisory_xact_lock(730021)')
    conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(owner,))
    tasks=conn.execute('SELECT task_id FROM tasks WHERE user_id=%s ORDER BY task_id FOR UPDATE',(owner,)).fetchall()
    for task in tasks:abandon_task(conn,task[0])
    return conn.execute('SELECT delete_user_data(%s)',(owner,)).fetchone()[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    commands.add_parser('retain')
    erase=commands.add_parser('delete-user');erase.add_argument('user_id',type=UUID)
    args=parser.parse_args()
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        result=retain(conn) if args.operation=='retain' else delete_user(conn,args.user_id)
    print(json.dumps(result))


if __name__=='__main__':main()
