"""Two real Rime processes verify canonical phrase usage without operator aliases."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dll', 'shared', 'profile'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    user = root / '.verification' / ('phrase-processes-' + uuid.uuid4().hex)
    common = [sys.executable, str(Path(__file__).with_name('Test-Local-Rime.py')),
              '--dll', args.dll, '--shared', args.shared, '--profile', args.profile,
              '--user-dir', str(user), '--phrase-query', '--phone-phrases', '--association-runtime', '--static-association']
    reports = []
    for step in range(2):
        extra = []
        if step:
            envelope = json.loads((user / 'bihua_personal_association_v1.jsonl').read_text(encoding='utf-8'))
            records = json.loads(envelope['payload'])['confirmed']
            positive = sum(record['positive_count'] > 0 for record in records.values())
            extra = ['--reuse', '--expected-phrase-usage', '2', '--expected-associations', str(positive)]
        result = subprocess.run(common + extra, cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        reports.append(json.loads(result.stdout))
    assert reports[0]['phrase_query']['native_user_dictionary_count'] == 2
    assert reports[1]['phrase_query']['native_user_dictionary_count'] == 4
    report = {'result': 'PASS', 'native_phrase_counts': [2, 4], 'canonical_codes_only': True,
              'sandbox': str(user), 'processes': reports}
    (user / 'phrase-two-process-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'result': 'PASS', 'native_phrase_counts': [2, 4], 'sandbox': str(user)}))

if __name__ == '__main__':
    main()
