from echo.agent_tools import BundleArgs, run_bundle


def test_ui_bundle_preserves_native_order_text_and_history(client):
    first = client.post('/api/clips', json={'text':'Nota ficticia del lunes'}).json()['id']
    second = client.post('/api/clips', json={'text':'Otra nota ficticia\ncon segunda línea'}).json()['id']
    before = client.get('/api/clips').json()
    args = BundleArgs(ids=[second, first], max_chars_per_clip=20000)
    response = client.post('/api/clips/bundle', json=args.model_dump())
    assert response.status_code == 200
    assert response.json() == run_bundle(client.services, args)
    assert [clip['id'] for clip in response.json()['clips']] == [second, first]
    assert client.get('/api/clips').json() == before
