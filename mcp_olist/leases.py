"""Fence writes from a superseded background worker; CLI tasks have no lease."""
from uuid import UUID


def validate(conn,task_id,token=None,states=('running',),lock=False):
    row=conn.execute('SELECT status,background,lease_token,lease_expires_at>now() FROM tasks WHERE task_id=%s'+(' FOR UPDATE' if lock else ''),(UUID(str(task_id)),)).fetchone()
    if not row or row[0] not in states:raise ValueError('Task is not active')
    if row[1] and (not token or str(row[2])!=str(token) or not row[3]):raise ValueError('Worker lease is missing or expired')
