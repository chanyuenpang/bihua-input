"""Manage local personal phrases and learned associations; never overwrites base dictionaries."""
import argparse
import json
import math
import os
from pathlib import Path

from personal_data import association_lock, atomic_write, checksum, han, read_snapshot, validate_snapshot


def normalized_codes(packed):
    return packed.lower().replace('d', 'n').translate(str.maketrans('12345', 'hspnz')).split('|')


def phrase_rows(path):
    rows = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line or line.startswith('#'):
                continue
            text, codes, weight = line.split('\t')
            codes = normalized_codes(codes)
            weight = float(weight)
            if not han(text) or not 2 <= len(text) <= 4 or len(codes) != len(text) or text in rows:
                raise ValueError('Invalid or duplicate phrase: ' + text)
            if not math.isfinite(weight) or not 0 <= weight <= 1000000000 or any(not code or len(code) > 52 or set(code) - set('hspnz') for code in codes):
                raise ValueError('Invalid phrase code or weight: ' + text)
            rows[text] = (codes, weight)
    if len(rows) > 20000:
        raise ValueError('Personal vocabulary exceeds 20000 entries')
    return rows


def manage_phrases(args, parser, directory):
    path = directory / 'bihua_personal_phrases.tsv'
    rows = phrase_rows(path)
    if args.action == 'add':
        if not args.word or not args.codes:
            parser.error('add requires --word and --codes')
        codes = normalized_codes(args.codes)
        if not han(args.word) or not 2 <= len(args.word) <= 4 or len(codes) != len(args.word) or any(not code or len(code) > 52 or set(code) - set('hspnz') for code in codes):
            parser.error('A phrase requires 2..4 Han characters and one canonical code per character')
        rows[args.word] = (codes, 1)
    elif args.action == 'delete':
        if not args.word:
            parser.error('delete requires --word')
        rows.pop(args.word, None)
    elif args.action == 'import':
        if not args.input:
            parser.error('import requires --input TSV')
        if not args.input.is_file():
            parser.error('Import file does not exist')
        incoming = phrase_rows(args.input)
        rows = incoming if args.replace else rows | incoming
    elif args.action not in ('list', 'export'):
        parser.error('This action applies to associations only')
    if len(rows) > 20000:
        raise ValueError('Personal vocabulary exceeds 20000 entries')
    content = '# phrase\tcanonical_codes\tweight\n' + ''.join(text + '\t' + '|'.join(codes) + '\t' + format(weight, 'g') + '\n' for text, (codes, weight) in sorted(rows.items()))
    if args.action == 'list':
        print(content, end='')
    elif args.action == 'export':
        if not args.output:
            parser.error('export requires --output')
        atomic_write(args.output, content)
    else:
        if path.exists():
            atomic_write(path.with_suffix('.tsv.previous'), path.read_text(encoding='utf-8'))
        atomic_write(path, content)
        print('个人词条已保存。重新部署小狼毫后生效；使用次数仍由 Rime 用户词库保存。')
    return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['phrases', 'associations', 'strokes'])
    parser.add_argument('action', choices=['list', 'export', 'import', 'add', 'upsert', 'delete', 'clear-window', 'restore-previous'])
    parser.add_argument('--rime-dir', type=Path, default=Path(os.environ.get('APPDATA', '.')) / 'Rime')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--word')
    parser.add_argument('--char')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--result-file', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--codes', help='Per-character codes joined by |; accepts digits 1..5 or h/s/p/d/n/z')
    parser.add_argument('--replace', action='store_true', help='Replace instead of merge on import')
    args = parser.parse_args()
    directory = args.rime_dir.resolve()
    if args.output and args.output.resolve().is_relative_to(directory):
        parser.error('Export outside the live Rime directory to protect active dictionaries')
    if args.kind == 'strokes':
        import personal_strokes as strokes
        operation = 'list' if args.action == 'export' else args.action
        try:
            result = strokes.action(directory, operation, char=args.char or args.word, code=args.codes,
                                    content=args.input.read_text(encoding='utf-8-sig') if args.input else None,
                                    replace=args.replace)
        except Exception as error:
            if args.result_file:
                atomic_write(args.result_file, json.dumps({'status':'error','message':str(error)},ensure_ascii=False))
            raise
        if args.result_file:
            atomic_write(args.result_file, json.dumps({key:value for key,value in result.items() if key!='rows'},ensure_ascii=False))
        if args.action == 'export':
            if not args.output: parser.error('export requires --output')
            atomic_write(args.output, strokes.render(max(1, result['revision']), {row['text']: row['code'] for row in result['rows']}))
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        elif args.action == 'list':
            print(strokes.render(max(1, result['revision']), {row['text']: row['code'] for row in result['rows']}), end='')
        elif not result.get('skipped_system'):
            print('个人笔顺已保存，下一次查询立即生效。')
        return
    if args.kind == 'phrases':
        with association_lock(directory / 'bihua_personal_phrases.tsv'):
            return manage_phrases(args, parser, directory)

    path = directory / 'bihua_personal_association_v1.jsonl'
    if args.action in ('add',):
        parser.error('Associations are confirmed through explicit candidate selection')
    with association_lock(path):
        if args.action == 'restore-previous':
            previous_envelope, state = read_snapshot(path.with_name(path.name + '.previous'))
            try:
                envelope, _ = read_snapshot(path)
                envelope['revision'] = max(envelope['revision'], previous_envelope['revision'])
            except (ValueError, FileNotFoundError, KeyError, TypeError):
                envelope = previous_envelope
            if path.exists():
                atomic_write(path.with_name(path.name + '.before-restore'), path.read_text(encoding='utf-8', errors='replace'))
        else:
            envelope, state = read_snapshot(path)
        if args.action in ('list', 'export'):
            content = json.dumps(state, ensure_ascii=False, indent=2) + '\n'
            if args.action == 'list':
                print(content, end='')
            else:
                if not args.output:
                    parser.error('export requires --output')
                atomic_write(args.output, content)
            return
        if args.action == 'delete':
            if not args.word:
                parser.error('delete requires --word context+next character')
            state['confirmed'].pop(args.word, None)
        elif args.action == 'clear-window':
            state['window'] = []
            state['segment'] += 1
        elif args.action == 'restore-previous':
            pass  # Backup was validated before touching a damaged active file.
        elif args.action == 'import':
            if not args.input:
                parser.error('import requires --input exported JSON')
            incoming = json.loads(args.input.read_text(encoding='utf-8'))
            validate_snapshot(incoming)
            if not args.replace and incoming['version'] != state['version']:
                raise ValueError('联想快照版本不同，请使用当前版本的导出文件')
            if args.replace:
                state = incoming
            else:
                # Merge confirmed facts only; never concatenate training windows.
                for phrase, record in incoming['confirmed'].items():
                    existing = state['confirmed'].get(phrase)
                    if not existing or record.get('last_feedback_at', record.get('last_used_at', 0)) > existing.get('last_feedback_at', existing.get('last_used_at', 0)):
                        state['confirmed'][phrase] = record
        validate_snapshot(state)
        payload = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
        updated = {'format': 1, 'revision': envelope['revision'] + 1, 'payload': payload, 'checksum': checksum(payload)}
        if args.action != 'restore-previous' and path.exists():
            atomic_write(path.with_name(path.name + '.previous'), path.read_text(encoding='utf-8'))
        atomic_write(path, json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n')
        print('个人联想已保存；权重时间保留，重新启用输入法后继续使用。')


if __name__ == '__main__':
    main()
