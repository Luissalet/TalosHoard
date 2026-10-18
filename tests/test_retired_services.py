import json

from cassandra_hoard.config import Config
from cassandra_hoard.registry import Registry


def test_retired_services_cannot_be_restored_by_saved_restart_overrides(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    config = Config(data_dir=data, roots=[], externals=False, hub_registry=False)
    config.retired_ids = ('argus', 'echo', 'funes', 'cassandra', 'diskhoard', 'tantalus', 'phileas')
    saved = {'services': [
        {'id': 'argus', 'url': 'http://127.0.0.1:5183', 'restart': {'enabled': True, 'cmd': 'old-server'}},
        {'id': 'custom-service', 'url': 'http://127.0.0.1:59998'},
    ], 'policies': {'argus': {'enabled': True}}}
    config.services_path.write_text(json.dumps(saved), encoding='utf-8')
    original = config.services_path.read_bytes()
    registry = Registry(config)
    assert registry.get('argus') is None
    assert registry.get('custom-service') is not None
    assert config.services_path.read_bytes() == original
