"""Private end-to-end CLI word and association maintenance checks."""
import json
from pathlib import Path
import subprocess
import sys
import uuid
from personal_data import read_snapshot, checksum

def main():
    root = Path(__file__).resolve().parent.parent
    sandbox = root / '.verification' / ('personal-manager-' + uuid.uuid4().hex)
    directory = sandbox / 'rime'
    directory.mkdir(parents=True)
    def run(kind, action, *extra, success=True):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('Manage-Personal.py')),
                                 kind, action, '--rime-dir', str(directory), *map(str, extra)],
                                capture_output=True, text=True, encoding='utf-8')
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result
    run('phrases', 'add', '--word', '中国', '--codes', '2512|25112141')
    path = directory / 'bihua_personal_phrases.tsv'
    run('phrases', 'add', '--word', '中国', '--codes', '2512|25112141')
    incoming = sandbox / 'input.tsv'
    incoming.write_text('上海\t211|4413155414\t1e+09\n', encoding='utf-8')
    run('phrases', 'import', '--input', incoming)
    assert '1e+09' in path.read_text(encoding='utf-8')
    exported = sandbox / 'words.tsv'
    run('phrases', 'export', '--output', exported)
    assert exported.read_bytes() == path.read_bytes()
    protected = path.read_bytes()
    incoming.write_text('上海\t66|77\t1\n', encoding='utf-8')
    run('phrases', 'import', '--input', incoming, success=False)
    run('phrases', 'import', '--input', sandbox / 'missing', '--replace', success=False)
    run('phrases', 'export', '--output', path, success=False)
    assert protected == path.read_bytes()
    run('phrases', 'delete', '--word', '上海')
    snapshot = directory / 'bihua_personal_association_v1.jsonl'
    state = {'version': 1, 'capacity': 1000, 'sequence': 2, 'segment': 1,
             'half_life': 604800, 'minimum_weight': 0.2, 'maximum_strength': 8,
             'window': [{'text': '星', 'sequence': 1, 'segment': 1, 'observed_at': 1000}],
             'confirmed': {'星河': {'count': 1, 'recent': 2, 'strength': 1, 'last_used_at': 1000}}}
    payload = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    snapshot.write_text(json.dumps({'format': 1, 'revision': 1, 'payload': payload, 'checksum': checksum(payload)}), encoding='utf-8')
    run('associations', 'export', '--output', sandbox / 'associations.json')
    run('associations', 'delete', '--word', '星河')
    assert '星河' not in read_snapshot(snapshot)[1]['confirmed']
    run('associations', 'import', '--input', sandbox / 'associations.json')
    assert '星河' in read_snapshot(snapshot)[1]['confirmed']
    run('associations', 'clear-window')
    assert not read_snapshot(snapshot)[1]['window']
    previous = snapshot.with_name(snapshot.name + '.previous').read_bytes()
    snapshot.write_text('{broken', encoding='utf-8')
    run('associations', 'restore-previous')
    assert read_snapshot(snapshot)[1] == json.loads(json.loads(previous)['payload'])
    assert snapshot.with_name(snapshot.name + '.before-restore').read_text(encoding='utf-8') == '{broken'
    snapshot.unlink()
    run('associations', 'restore-previous')
    read_snapshot(snapshot)
    run('associations', 'export', '--output', snapshot, success=False)
    v2 = {'version': 2, 'policy': 'shown_choice_v1', 'capacity': 1000, 'sequence': 2, 'segment': 1,
          'window': [], 'confirmed': {'星河': {'score': 0, 'positive_count': 1, 'negative_count': 11,
          'recent': 2, 'last_feedback_at': 1000, 'hidden_sequence': 2, 'origin': 'personal'}}}
    incoming2 = sandbox / 'feedback-v2.json'
    incoming2.write_text(json.dumps(v2, ensure_ascii=False), encoding='utf-8')
    protected = snapshot.read_bytes()
    run('associations', 'import', '--input', incoming2, success=False)
    assert snapshot.read_bytes() == protected, 'Mixed-version merge modified current state'
    run('associations', 'import', '--input', incoming2, '--replace')
    assert read_snapshot(snapshot)[1]['confirmed']['星河']['score'] == 0
    run('associations', 'export', '--output', sandbox / 'feedback-export.json')
    invalid = json.loads(json.dumps(v2)); invalid['confirmed']['星河']['score'] = True
    incoming2.write_text(json.dumps(invalid, ensure_ascii=False), encoding='utf-8')
    protected = snapshot.read_bytes()
    run('associations', 'import', '--input', incoming2, success=False)
    assert snapshot.read_bytes() == protected
    run('associations', 'clear-window')
    assert read_snapshot(snapshot)[1]['confirmed']['星河']['score'] == 0, 'History clearing resurrected hidden edge'
    report = {'result': 'PASS', 'word_crud_import_export': True, 'failed_import_no_partial_write': True,
              'exports_protect_active_files': True, 'association_merge_delete_clear': True,
              'restore_damaged_and_missing_active': True, 'sandbox': str(sandbox)}
    (sandbox / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
