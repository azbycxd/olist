"""Authenticated preference listing/deletion; no user ID supplied in request data."""
import os
from datetime import datetime,timedelta,timezone
from uuid import UUID

import jwt
from fastapi import FastAPI,Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials

from scripts.preferences import list_active,delete

app=FastAPI()
bearer=HTTPBearer(auto_error=False)


def secret():
    key=os.getenv('MEMORY_API_SECRET','')
    if len(key)<32: raise RuntimeError('MEMORY_API_SECRET must contain at least 32 characters')
    return key


def issue(user_id):
    now=datetime.now(timezone.utc)
    return jwt.encode({'sub':str(UUID(str(user_id))),'iat':now,'exp':now+timedelta(hours=1),'aud':'olist-memory'},secret(),algorithm='HS256')


def user(credentials: HTTPAuthorizationCredentials=Depends(bearer)):
    if not credentials: raise HTTPException(401,'Bearer token required')
    try:
        claims=jwt.decode(credentials.credentials,secret(),algorithms=['HS256'],audience='olist-memory',options={'require':['exp','sub','iat','aud']})
        return UUID(claims['sub'])
    except (jwt.PyJWTError,ValueError): raise HTTPException(401,'Invalid token')


@app.get('/memories')
def get_memories(owner: UUID=Depends(user)):
    return {'memories':list_active(owner)}


@app.delete('/memories/{memory_id}',status_code=204)
def delete_memory(memory_id:UUID,owner:UUID=Depends(user)):
    if not delete(owner,memory_id): raise HTTPException(404,'Memory not found')
