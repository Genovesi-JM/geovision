"""Export the current route contracts without starting servers or connecting to databases."""
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.update(ENV='test', DATABASE_URL='sqlite:///:memory:', ACCOUNTS_DATABASE_URL='sqlite:///:memory:', STARTUP_COMPATIBILITY_BOOTSTRAP='false')
from fastapi import FastAPI
from app.bootstrap import register_application_routes

app = FastAPI(title='GeoVision API', version='2026-09-23')
register_application_routes(app)
spec = app.openapi()
spec['servers'] = [{'url': 'https://api.geovisionops.com'}]
SELECTED = {
    '/auth/register': ['post'], '/auth/login': ['post'], '/auth/me': ['get'],
    '/auth/refresh': ['post'], '/auth/logout': ['post'],
    '/portal/experience': ['get'], '/portal/map-layers': ['get'],
    '/assets': ['get', 'post'], '/assets/{asset_id}': ['get'],
    '/datasets/': ['get', 'post'], '/datasets/{dataset_id}': ['get'],
    '/datasets/{dataset_id}/upload': ['post'],
    '/datasets/{dataset_id}/files/{file_id}/download': ['get'],
    '/ai/chat': ['post'],
}
# Keep the exact backend schema. FlutterFlow supports OpenAPI file imports;
# mapping variables/actions and testing in the actual project remain required.
starter = copy.deepcopy(spec)
starter['info']['title'] = 'GeoVision FlutterFlow customer journey'
starter['paths'] = {p: {m: copy.deepcopy(spec['paths'][p][m]) for m in methods} for p, methods in SELECTED.items()}
for path, operations in starter['paths'].items():
    for operation in operations.values():
        parameters = operation.setdefault('parameters', [])
        if operation.get('security') and not path.startswith('/auth/'):
            parameters.append({
                'name': 'X-Workspace-ID', 'in': 'header', 'required': False,
                'description': 'Bind active_workspace_id from /portal/experience; never use a fixed customer ID.',
                'schema': {'type': 'string'},
            })
        if path in {'/auth/login', '/auth/register'}:
            parameters.append({
                'name': 'X-GeoVision-Client', 'in': 'header', 'required': False,
                'description': 'Use web for the browser prototype (no refresh token). Native clients need secure token storage.',
                'schema': {'type': 'string', 'default': 'web'},
            })
refs = set()
def collect(node):
    if isinstance(node, dict):
        if '$ref' in node:
            refs.add(node['$ref'].split('/')[-1])
        for value in node.values(): collect(value)
    elif isinstance(node, list):
        for value in node: collect(value)
collect(starter['paths'])
while True:
    before = set(refs)
    for key in before: collect(spec['components']['schemas'][key])
    if before == refs: break
starter['components']['schemas'] = {key: value for key, value in spec['components']['schemas'].items() if key in refs}
for name, data in [('geovision-full.openapi.json', spec), ('geovision-customer-journey.openapi.json', starter)]:
    (Path(__file__).parent / name).write_text(json.dumps(data, indent=2) + '\n')
print(json.dumps({'full_operations': sum(len([m for m in ops if m in {'get','post','put','delete','patch'}]) for ops in spec['paths'].values()), 'starter_operations': sum(map(len, SELECTED.values())), 'starter_schemas': len(refs)}))
