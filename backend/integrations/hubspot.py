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

CLIENT_ID = os.getenv('HUBSPOT_CLIENT_ID')
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


async def authorize_hubspot(user_id, org_id):
    # TODO
    pass

async def oauth2callback_hubspot(request: Request):
    # TODO
    pass

async def get_hubspot_credentials(user_id, org_id):
    # TODO
    pass

async def create_integration_item_metadata_object(response_json):
    # TODO
    pass

async def get_items_hubspot(credentials):
    # TODO
    pass