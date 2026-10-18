"""Verify panel persistence, rollback, local API isolation and personal words."""
import http.client
import importlib.util
import json
from pathlib import Path
import threading
import uuid
import yaml

spec = importlib.util.spec_from_file_location('panel', Path(__file__).with_name('Settings-Panel.py'))
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


def main():
    directory = panel.ROOT / '.verification' / ('settings-panel-' + uuid.uuid4().hex)
    (directory / 'build').mkdir(parents=True)
    compiled = {'schema': {'version': 'test'}, 'bihua_matcher': {'fuzzy_enabled': False, 'personal_association': True},
                'key_binder': {'bindings': [{'when': 'always', 'accept': 'd', 'send': 'n'}]}}
    (directory / 'build/bihua_mvp.schema.yaml').write_text(yaml.safe_dump(compiled), encoding='utf-8')
    (directory / 'bihua_mvp.custom.yaml').write_bytes(b'# keep this comment\r\npatch:\r\n  unknown/setting: 42 # preserve\r\n')
    (directory / 'weasel.custom.yaml').write_text('# style note\npatch:\n  "style/color_scheme": ink\n', encoding='utf-8')

    def deploy():
        patch = panel.decode(panel.read(directory / 'bihua_mvp.custom.yaml')).get('patch', {})
        active = dict(compiled)
        for key, value in patch.items():
            target = active
            parts = key.split('/')
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        # Rime emits an all-digit style identifier as a plain YAML scalar.
        if active.get('bihua_keys',{}).get('keypad_style')=='789456':
            active['bihua_keys']['keypad_style']=789456
        (directory / 'build/bihua_mvp.schema.yaml').write_text(yaml.safe_dump(active), encoding='utf-8')
        appearance = {'style': {}}
        for key, value in panel.decode(panel.read(directory / 'weasel.custom.yaml')).get('patch', {}).items():
            if key.startswith(('style/','bihua_mouse/')):
                target=appearance
                parts=key.split('/')
                for part in parts[:-1]:target=target.setdefault(part,{})
                target[parts[-1]]=value
        (directory / 'build/weasel.yaml').write_text(yaml.safe_dump(appearance), encoding='utf-8')

    service = panel.Settings(directory, deploy)
    assert panel.decode(panel.patch_text('patch:\n  "style/color_scheme": ink', {'style/font_point': 14}))['patch']['style/font_point'] == 14
    settings = service.state()['settings']
    settings.update(page_minus=True, page_brackets=True, page_comma=False, page_tab=True, page_keypad=True,
                    association=True, prediction_pages=5, horizontal=False, font_size=18, mouse_input=True)
    service.paths[0].write_bytes(service.paths[0].read_bytes() + b'  bihua_association/half_life_days: 7\r\n')
    before = [path.read_bytes() for path in service.paths]
    prepared = service.preview(settings)
    assert before == [path.read_bytes() for path in service.paths], 'Preview wrote configuration'
    service.apply(prepared['preview_id'])
    assert '# keep this comment\r\n' in panel.read(service.paths[0])
    assert '  unknown/setting: 42 # preserve\r\n' in panel.read(service.paths[0])
    assert service.paths[1].read_bytes().startswith(before[1]), 'Unknown appearance bytes changed'
    assert service.state()['settings'] == settings
    for device,presets in [('letter',panel.LETTER),('keypad',panel.KEYPAD)]:
        for style,keys in presets.items():
            changed=dict(settings)
            changed[device+'_style']=style
            changed[device+'_keys']=keys.copy()
            service.apply(service.preview(changed)['preview_id'])
            assert service.state()['settings']==changed
    service.apply(service.preview(settings)['preview_id'])
    disabled=dict(settings,stroke_info=False,arrow_navigation=False)
    service.apply(service.preview(disabled)['preview_id'])
    assert service.state()['settings']==disabled
    service.apply(service.preview(settings)['preview_id'])
    invalid=dict(settings)
    invalid['letter_style']='custom'
    invalid['letter_keys']=dict(settings['letter_keys'],h='s')
    try:
        service.preview(invalid)
        raise AssertionError('Duplicate physical key accepted')
    except ValueError:
        pass
    invalid['letter_keys']=dict(settings['letter_keys'],h='Return')
    try:
        service.preview(invalid)
        raise AssertionError('Reserved key accepted')
    except ValueError:
        pass
    assert 'bihua_association/half_life_days' not in panel.decode(panel.read(service.paths[0]))['patch']
    active = [path.read_bytes() for path in service.paths]
    failure = service.preview(settings)
    counter = 0

    def fail_once():
        nonlocal counter
        counter += 1
        if counter == 1:
            raise RuntimeError('simulated deploy failure')
        deploy()

    service.deploy = fail_once
    try:
        service.apply(failure['preview_id'])
        raise AssertionError('Failed deploy reported success')
    except RuntimeError as error:
        assert '已恢复原配置' in str(error)
    assert active == [path.read_bytes() for path in service.paths] and not service.recovery_required
    service.deploy = deploy
    stale = service.preview(settings)
    service.paths[0].write_bytes(service.paths[0].read_bytes() + b'# external edit\n')
    try:
        service.apply(stale['preview_id'])
        raise AssertionError('Stale preview overwrote another writer')
    except RuntimeError as error:
        assert '其他程序' in str(error)
    try:
        panel.patch_text('patch:\n  foo: 1\n  foo: 2\n', {'bar': 1})
        raise AssertionError('Duplicate keys silently accepted')
    except ValueError:
        pass
    service.word_action('add', {'text': '中国', 'codes': '251|25112141'})
    assert service.state()['words'] == [{'text': '中国', 'digits': '251|25112141'}]
    word_file = directory / 'bihua_personal_phrases.tsv'
    word_bytes = word_file.read_bytes()
    try:
        service.word_action('import', {'content': '坏词\t66|77\t1\n'})
        raise AssertionError('Bad import accepted')
    except ValueError:
        pass
    assert word_file.read_bytes() == word_bytes
    service.word_action('delete', {'text': '中国'})
    assert not service.state()['words']
    service.word_action('add', {'text': '中国', 'codes': ''})
    assert service.state()['words'][0]['digits'] == '2512|25112141'
    service.word_action('delete', {'text': '中国'})
    server = panel.make_server(service, 'test-token')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def request(path, token='test-token', origin=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'X-Bihua-Token': token}
            if origin:
                headers['Origin'] = origin
            connection.request('GET', path, headers=headers)
            response = connection.getresponse()
            status, data = response.status, response.read()
            connection.close()
            return status, data
        assert request('/')[0] == 200
        assert request('/api/state')[0] == 200
        assert request('/api/state', 'wrong')[0] == 403
        assert request('/api/state', origin='https://example.com')[0] == 403
        assert request('/../README.md')[0] == 404
    finally:
        server.shutdown()
        server.server_close()
    report = {'result': 'PASS', 'preview_does_not_write': True, 'unknown_patch_and_comments_preserved': True,
              'apply_and_readback': True, 'failed_deploy_rolls_back': True, 'stale_preview_rejected': True,
              'duplicate_yaml_rejected': True, 'numeric_word_add_export_delete': True,
              'invalid_import_preserves_entire_dictionary': True, 'token_origin_paths_isolated': True,
              'sandbox': str(directory)}
    (directory / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
