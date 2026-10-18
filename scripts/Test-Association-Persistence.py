"""Independent Rime processes verify personal prediction disk state and decay metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid


def read_snapshot(path):
    envelope = json.loads(path.read_text(encoding='utf-8'))
    checksum = 2166136261
    for byte in envelope['payload'].encode('utf-8'):
        checksum = ((checksum ^ byte) * 16777619) & 0xffffffff
    assert envelope['checksum'] == f'{checksum:08x}', 'Snapshot checksum mismatch'
    return json.loads(envelope['payload'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', required=True)
    parser.add_argument('--shared', required=True)
    parser.add_argument('--profile', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    user = root / '.verification' / ('association-processes-' + uuid.uuid4().hex)
    common = [sys.executable, str(Path(__file__).with_name('Test-Local-Rime.py')),
              '--dll', args.dll, '--shared', args.shared, '--profile', args.profile,
              '--user-dir', str(user), '--association-runtime']

    def run(extra):
        process = subprocess.run(common + extra, cwd=root, capture_output=True, text=True, encoding='utf-8')
        if process.returncode:
            raise RuntimeError(process.stdout + '\n' + process.stderr)
        return json.loads(process.stdout)

    first = run([])
    path = user / 'bihua_personal_association_v1.jsonl'
    before = read_snapshot(path)
    assert len(before['window']) <= 1000
    assert before['confirmed']['星河']['positive_count'] == 1
    assert before['confirmed']['星河计']['positive_count'] == 1
    assert before['confirmed']['星河计划']['positive_count'] == 1
    for record in before['confirmed'].values():
        assert 0 <= record['score'] <= 20 and record['last_feedback_at'] > 0
    protected = [user / 'bihua_local.schema.yaml', user / 'bihua_local.dict.yaml', *sorted((user / 'lua').glob('*.lua'))]
    hashes = {str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in protected}
    second = run(['--reuse', '--expected-associations', str(sum(record['positive_count'] > 0 for record in before['confirmed'].values()))])
    assert hashes == {str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in protected}
    after = read_snapshot(path)
    for phrase in ('星河', '星河计', '星河计划'):
        assert after['confirmed'][phrase]['positive_count'] == 2, phrase
        assert after['confirmed'][phrase]['last_feedback_at'] >= before['confirmed'][phrase]['last_feedback_at']
    report = {'result': 'PASS', 'first_process': first, 'second_process': second,
              'relations_loaded_before_new_typing': second['association_loaded_relations'],
              'per_step_confirmation_counts_after_restart': {phrase: after['confirmed'][phrase]['positive_count'] for phrase in ('星河', '星河计', '星河计划')},
              'timestamps_and_strength_saved': True, 'static_files_unchanged': True,
              'private_user_directory': str(user)}
    (user / 'association-two-process-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
