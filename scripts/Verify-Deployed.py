"""Read back installed source hashes, flags and compiled keyboard settings."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('panel', Path(__file__).with_name('Settings-Panel.py'))
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    directory = Path(os.environ['APPDATA']) / 'Rime'
    service = panel.Settings(directory)
    state = service.state()
    config = service.compiled()
    assert state['version'] == '0.5.1' and state['phrase_enabled']
    assert panel.get(config, 'schema/name') == '笔画输入法'
    expected = {'fuzzy': False, 'association': True, 'prediction_pages': 5,
                'page_minus': True, 'page_brackets': True,
                'page_comma': False, 'page_tab': True, 'page_keypad': True}
    for key, value in expected.items():
        assert state['settings'][key] == value, key
    assert panel.get(config, 'menu/page_size') == 9
    assert panel.get(config, 'speller/alphabet') == 'hspnz'
    assert panel.get(config, 'engine/processors')[0] == 'lua_processor@*bihua_query_keys'
    assert panel.get(config, 'bihua_matcher/mobile_phrases') is True
    assert panel.get(config, 'bihua_matcher/static_association') is True
    assert panel.get(config, 'key_binder/import_preset') is None
    bindings = panel.get(config, 'key_binder/bindings')
    for key in ['Return', 'KP_Enter', 'KP_0']:
        assert {'when': 'has_menu', 'accept': key, 'send': 'space'} in bindings
    assert not any(row.get('accept') in ['KP_6', 'KP_7'] for row in bindings)
    manifest = json.loads((directory / 'bihua_local.manifest.json').read_text(encoding='utf-8'))
    profile = ROOT / '.verification/generated-association-profile'
    for name, expected_hash in manifest['generated_files'].items():
        deployed = directory / ('lua/' + name if name.endswith('.lua') else name)
        assert digest(deployed) == expected_hash == digest(profile / name), name
    sources = {}
    for path in (ROOT / 'rime/lua').glob('*.lua'):
        deployed = directory / 'lua' / path.name
        if deployed.exists():
            assert digest(path) == digest(deployed), path.name
            sources[path.name] = digest(path)
    report = {'result': 'PASS', 'version': state['version'], 'schema_id': 'bihua_mvp',
              'compiled_schema_sha256': digest(directory / 'build/bihua_mvp.schema.yaml'),
              'settings': state['settings'], 'generated_profile_hashes': manifest['generated_files'],
              'runtime_source_hashes': sources, 'source_and_compiled_configuration_verified': True,
              'latest_windows_application_trial': 'pending user experience check after sleep',
              'previous_user_feedback': 'basic stroke input and chained predictions confirmed'}
    (ROOT / '.verification/deployed-local.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'result': 'PASS', 'version': state['version'], 'runtime_modules': len(sources), 'settings': state['settings']}))

if __name__ == '__main__':
    main()
