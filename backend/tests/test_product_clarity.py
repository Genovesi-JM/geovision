from datetime import timedelta
import pytest
import uuid
from app.models import User
from app.utils import hash_password
from app.core.time import utc_now
from app.models import IotDevice, TelemetryReading
from app.routers.iot import _device_payload
from test_iot_platform import _auth, _tenant, _provision, _ingest


def setup_device(client, db_session):
    email = f'clarity-{uuid.uuid4().hex}@example.com'
    db_session.add(User(email=email, password_hash=hash_password('test-password-long'), role='cliente', is_active=True))
    db_session.commit()
    _, site = _tenant(db_session, email)
    headers = _auth(client, email, 'test-password-long')
    device, secret = _provision(client, headers, site.id)
    return headers, device, secret


def test_missing_telemetry_does_not_become_zero(client, db_session):
    _, device, _ = setup_device(client, db_session)
    row = db_session.get(IotDevice, device['id'])
    payload = _device_payload(db_session, row)
    assert payload['battery_percent'] is None
    assert payload['signal_percent'] is None
    assert payload['last_reading_at'] is None


@pytest.mark.parametrize('age', [61, -30])
def test_stale_or_future_interlock_cannot_authorize_output(client, db_session, age):
    headers, device, secret = setup_device(client, db_session)
    response = _ingest(client, device['device_uid'], secret, f'interlock-{age}', 20)
    assert response.status_code == 200, response.text
    sample = db_session.query(TelemetryReading).filter_by(device_id=device['id'], channel='safety_ok').one()
    sample.recorded_at = utc_now() - timedelta(seconds=age)
    db_session.commit()
    response = client.post(f"/iot/devices/{device['id']}/commands", headers=headers,
        json={'name':'relay_on','confirmed':True,'reason':'Supervised test'})
    assert response.status_code == 409, response.text
    assert 'fresh' in response.json()['detail']


def test_reason_and_confirmation_are_required(client, db_session):
    headers, device, secret = setup_device(client, db_session)
    assert _ingest(client, device['device_uid'], secret, 'fresh-test', 20).status_code == 200
    url = f"/iot/devices/{device['id']}/commands"
    assert client.post(url, headers=headers, json={'name':'relay_on','confirmed':True}).status_code == 422
    assert client.post(url, headers=headers, json={'name':'relay_on','confirmed':False,'reason':'Supervised test'}).status_code == 409
    response = client.post(url, headers=headers, json={'name':'relay_on','confirmed':True,'reason':'Supervised test'})
    assert response.status_code == 202, response.text
    assert response.json()['outcome'] == 'pending'
    assert response.json()['data']['command_id']


def test_command_and_control_history_stay_in_selected_workspace(client, db_session):
    from app.models import Account, AccountMember, Asset
    headers, device, secret = setup_device(client, db_session)
    row = db_session.get(IotDevice, device['id'])
    one = Account(organization_id=row.company_id, name='Operations A', sector_focus='mining', entity_type='company')
    two = Account(organization_id=row.company_id, name='Operations B', sector_focus='mining', entity_type='company')
    db_session.add_all([one, two]); db_session.flush()
    db_session.add_all([AccountMember(account_id=w.id, user_id=row.created_by, role='owner', status='active') for w in (one, two)])
    db_session.get(Asset, row.core_asset_id).workspace_id = one.id
    db_session.commit()
    assert _ingest(client, device['device_uid'], secret, 'scope-reading', 20).status_code == 200
    wrong = {**headers, 'X-Workspace-ID': two.id}
    base = f"/iot/devices/{device['id']}"
    assert client.get(base, headers={**headers, 'X-Workspace-ID': one.id}).status_code == 200
    assert client.get(base, headers=wrong).status_code == 404
    assert client.get(base + '/commands', headers=wrong).status_code == 404
    response = client.post(base + '/commands', headers=wrong, json={'name':'relay_on','confirmed':True,'reason':'Wrong workspace test'})
    assert response.status_code == 403, response.text


def test_viewer_can_read_control_history_but_cannot_operate(client, db_session):
    from app.models import Account, AccountMember, Asset, CompanyUser
    headers, device, secret = setup_device(client, db_session)
    row = db_session.get(IotDevice, device['id'])
    account = Account(organization_id=row.company_id, name='View only', sector_focus='mining', entity_type='company')
    viewer = User(email=f'viewer-{uuid.uuid4().hex}@example.com', password_hash=hash_password('test-password-long'), role='cliente', is_active=True)
    db_session.add_all([account, viewer]); db_session.flush()
    db_session.add(CompanyUser(company_id=row.company_id, user_id=viewer.id, email=viewer.email, name='Viewer', role='viewer', is_active=True))
    db_session.add(AccountMember(account_id=account.id, user_id=viewer.id, role='viewer', status='active'))
    db_session.get(Asset, row.core_asset_id).workspace_id = account.id
    db_session.commit()
    access = {**_auth(client, viewer.email, 'test-password-long'), 'X-Workspace-ID': account.id}
    base = f"/iot/devices/{device['id']}"
    assert client.get(base + '/commands', headers=access).status_code == 200
    response = client.post(base + '/commands', headers=access, json={'name':'relay_on','confirmed':True,'reason':'Viewer must not operate'})
    assert response.status_code == 403, response.text
