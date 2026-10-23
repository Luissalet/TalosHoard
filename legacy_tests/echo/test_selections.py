from echo.agent_tools import call_tool
from echo.db import Database
from echo.store import ClipStore


def test_saved_selection_survives_restart_without_copying_or_editing_clips(client):
    first = client.services.clips.capture_text('Fixture A', source_app='fixture', source_title='A', now=client.clock())['id']
    second = client.services.clips.capture_text('Fixture B', source_app='fixture', source_title='B', now=client.clock())['id']
    before = client.get('/api/clips').json()
    args = {'name': '  Reunión  ', 'ids': [second, first], 'separator': ', ', 'include_origins': False}
    saved = client.post('/api/clips/selections', json=args)
    assert saved.status_code == 200, saved.text
    row = saved.json()['selection']
    assert row['name'] == 'Reunión' and row['ids'] == [second, first]
    with Database(client.services.config.db_path) as db:
        reopened = ClipStore(db, client.services.config.images_dir).selections()
        assert reopened == [row]
        assert set(dict(db.conn.execute('SELECT * FROM clip_selections').fetchone())) == {'id', 'name', 'ids', 'separator', 'include_origins', 'created_at', 'updated_at'}
    assert call_tool(client.services, 'clip_selections', {}) == client.get('/api/clips/selections').json()
    renamed = call_tool(client.services, 'clip_selection_save', {**args, 'id': row['id'], 'name': 'Renombrada', 'ids': [first, second]})['selection']
    assert renamed['id'] == row['id'] and renamed['created_at'] == row['created_at']
    assert renamed['name'] == 'Renombrada' and renamed['ids'] == [first, second]
    assert client.delete(f"/api/clips/selections/{row['id']}").json()['deleted']
    assert client.get('/api/clips/selections').json()['selections'] == []
    assert client.get('/api/clips').json() == before
    assert client.backend.read() is None


def test_missing_reference_is_retained_and_bundle_still_reports_it(client):
    row = call_tool(client.services, 'clip_selection_save', {'name': 'Referencia antigua', 'ids': [987654]})['selection']
    assert client.get('/api/clips/selections').json()['selections'][0]['ids'] == [987654]
    assert client.post('/api/clips/bundle', json={'ids': row['ids']}).status_code == 404
    assert client.post('/api/clips/selections', json={**row, 'name': ' '}).status_code == 400
    assert client.post('/api/clips/selections', json={'name': 'Duplicada', 'ids': [1, 1]}).status_code == 400
    assert client.post('/api/clips/selections', json={'name': 'Grande', 'ids': list(range(21))}).status_code == 400
    assert client.post('/api/clips/selections', json={**row, 'id': 999999}).status_code == 404
