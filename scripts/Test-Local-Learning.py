"""Two independent real-Rime processes verify original-code alias persistence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', required=True)
    parser.add_argument('--shared', required=True)
    parser.add_argument('--profile', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    user = root / '.verification' / ('learning-processes-' + uuid.uuid4().hex)
    common = [sys.executable, str(Path(__file__).with_name('Test-Local-Rime.py')),
              '--dll', args.dll, '--shared', args.shared, '--profile', args.profile,
              '--user-dir', str(user), '--fuzzy', '--learning']
    outputs = []
    for extra in (['--rank-learning'], ['--reuse', '--expected-commits', '1', '--expect-rank-learning']):
        process = subprocess.run(common + extra, cwd=root, capture_output=True, text=True, encoding='utf-8')
        if process.returncode:
            raise RuntimeError(process.stdout + '\n' + process.stderr)
        outputs.append(json.loads(process.stdout))
    report = {'processes': outputs, 'original_code_count_before_restart': outputs[0]['learning_aliases'],
              'original_code_count_loaded_after_restart': outputs[1]['learning_initial_aliases'],
              'exactly_once_after_second_selection': outputs[1]['learning_aliases'],
              'rank_learning_persists_after_restart': outputs[1]['rank_learning_after_process_restart'],
              'result': 'PASS', 'scope': 'Two independent OS processes using private Rime directory; no Windows UI input'}
    (user / 'two-process-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
