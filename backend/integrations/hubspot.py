import json
import secrets
import os
from urllib.parse import quote_plus
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = os.getenv('HUBSPOT_CLIENT_ID')   # loading into env
CLIENT_SECRET = os.getenv('HUBSPOT_CLIENT_SECRET')
REDIRECT_URI = os.getenv('HUBSPOT_REDIRECT_URI', 'http://localhost:8000/integrations/hubspot/oauth2callback')
# Minimal scope for reading contacts only
SCOPE = 'crm.objects.contacts.read'

AUTH_BASE = 'https://app.hubspot.com/oauth/authorize'
TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'
CONTACTS_URL = 'https://api.hubapi.com/crm/v3/objects/contacts'

authorization_url = (
    f'{AUTH_BASE}?client_id={CLIENT_ID}'
    f'&response_type=code'
    f'&redirect_uri={quote_plus(REDIRECT_URI)}'
)

# Only add scope if it's not empty
if SCOPE:
    authorization_url += f'&scope={quote_plus(SCOPE)}'

async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id,
    }
    encoded_state = json.dumps(state_data)
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', encoded_state, expire=600)
    
    # Build the complete authorization URL with proper encoding
    auth_url = f'{authorization_url}&state={quote_plus(encoded_state)}'
    
    # Debug logging
    print(f"DEBUG - CLIENT_ID: {CLIENT_ID}")
    print(f"DEBUG - REDIRECT_URI: {REDIRECT_URI}")
    print(f"DEBUG - SCOPE: '{SCOPE}'")
    print(f"DEBUG - Full Authorization URL: {auth_url}")
    
    return auth_url

async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error'))

    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    
    # Debug logging
    print(f"DEBUG - Received code: {code}")
    print(f"DEBUG - Received encoded_state: {encoded_state}")
    
    try:
        # URL decode the state first, then parse as JSON
        from urllib.parse import unquote_plus
        decoded_state = unquote_plus(encoded_state)
        print(f"DEBUG - Decoded state: {decoded_state}")
        state_data = json.loads(decoded_state)
    except Exception as e:
        print(f"DEBUG - State parsing error: {e}")
        raise HTTPException(status_code=400, detail=f'Invalid state payload: {e}')

    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')
    original_state = state_data.get('state')

    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')
    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,  # NOT encoded for token exchange
        'code': code,
    }

    # Debug logging for token exchange
    print(f"DEBUG - Token exchange data: {data}")
    
    async with httpx.AsyncClient() as client:
        token_resp, _ = await asyncio.gather(
            client.post(TOKEN_URL, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}')
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=token_resp.status_code, detail=f'Failed to get token: {token_resp.text}')

    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(token_resp.json()), expire=600)

    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)

async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')
    return json.loads(credentials)

async def create_integration_item_metadata_object(response_json):
    items = []
    for item in response_json.get('results', []):
        props = item.get('properties', {})
        name = props.get('firstname', '')
        lname = props.get('lastname', '')
        full_name = (name + ' ' + lname).strip() or props.get('email', 'Contact')
        items.append(IntegrationItem(
            id=item.get('id'),
            type='contact',
            name=full_name,
            creation_time=props.get('createdate'),
            last_modified_time=props.get('lastmodifieddate'),
            parent_id=None,
            parent_path_or_name=None,
        ))
    return items

async def get_items_hubspot(credentials):
    if isinstance(credentials, str):
        try:
            credentials = json.loads(credentials)
        except Exception:
            pass
    access_token = credentials.get('access_token') if isinstance(credentials, dict) else None
    if not access_token:
        raise HTTPException(status_code=400, detail='Invalid credentials')

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    params = {
        'limit': 50,
        'properties': 'firstname,lastname,email,createdate,lastmodifieddate',
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(CONTACTS_URL, headers=headers, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f'Error fetching HubSpot items: {resp.text}')

    return await create_integration_item_metadata_object(resp.json())