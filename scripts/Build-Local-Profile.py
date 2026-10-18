"""Build a local research profile from the verified mobile static export.

The output is private build staging; release_profile.py owns explicit product-data selection.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

SOURCE_HASHES = {
    'wechat-mobile-strokes.tsv': '5840b0fb6fadd0ca002e6eeb3aea507b157ddc7ecd0bcb0a558c5fd94398b23b',
    'wechat-mobile-stroke-candidates.tsv': 'df14c40f0495d4bea17dd062104a68448fbc8c66a60e7426e06f2622f5600c9f',
    'wechat-mobile-full-code-scores.tsv': 'a7a4e6717278ff403a6854638ed5118e367dee2dd2f865f6bfed14c655a1aae3',
}
APK_HASH = '940586c40ca1ddb7d7190a727c9a3e2846c5a30b290de427da8c24df814b9603'
CONTINUATIONS_HASH = 'aee195309421b19bdd65198940923341905dac38019b957d1d0ee304e78fad25'
TRANSLATION = str.maketrans('12345', 'hspnz')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_tsv(path):
    with path.open(encoding='utf-8', newline='') as file:
        return list(csv.DictReader(file, delimiter='\t'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--with-associations', action='store_true')
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    if not output.is_relative_to((project / '.verification').resolve()):
        raise ValueError('Local research profile must remain under project .verification')
    for name, expected in SOURCE_HASHES.items():
        if digest(args.source / name) != expected:
            raise ValueError('Export differs from the verified snapshot: ' + name)
    report = json.loads((args.source / 'export-report.json').read_text(encoding='utf-8'))
    if report['apk_sha256'] != APK_HASH:
        raise ValueError('Unexpected source APK')
    code_rows = read_tsv(args.source / 'wechat-mobile-strokes.tsv')
    codes = {row['character']: row['stroke_digits'] for row in code_rows}
    rows = read_tsv(args.source / 'wechat-mobile-stroke-candidates.tsv')
    full = read_tsv(args.source / 'wechat-mobile-full-code-scores.tsv')
    full_by_char = {row['character']: row for row in full}
    if len(codes) != 29517 or len(code_rows) != len(codes) or len(rows) != 79172 or len(full_by_char) != 10579:
        raise ValueError('Export record counts disagree')
    prefixes, exact = {}, {}
    for row in rows:
        char, prefix = row['candidate'], row['stroke_prefix']
        rank, flag, score = int(row['stored_rank']), int(row['exact_match']), float(row['stored_score'])
        group = prefixes.setdefault(prefix, [])
        if rank != len(group) + 1 or not math.isfinite(score):
            raise ValueError('Candidate rank or score invalid')
        if group and score > float(group[-1]['stored_score']):
            raise ValueError('Unsorted candidate list')
        if flag not in (0, 1) or not codes[char].startswith(prefix) or bool(flag) != (codes[char] == prefix):
            raise ValueError('Candidate and canonical code disagree')
        group.append(row)
        if flag:
            if char in exact or full_by_char[char]['stroke_digits'] != prefix:
                raise ValueError('Duplicate or contradictory exact entry')
            if float(full_by_char[char]['full_code_stored_score']) != score:
                raise ValueError('Full-code score disagrees')
            exact[char] = score
    if len(prefixes) != 34595 or set(exact) != set(full_by_char):
        raise ValueError('Prefix or exact character set disagrees')
    # The compiled dictionary gives Memory a canonical spelling and language;
    # ranking comes from the prefix index, never these placeholder dictionary weights.
    dictionary = ['---', 'name: bihua_local', 'version: "local-4.0.0-1"',
                  'sort: original', 'use_preset_vocabulary: false', '...', '']
    dictionary += [f'{char}\t{codes[char].translate(TRANSLATION)}\t1' for char in sorted(exact)]
    # A generated Lua module avoids a second filesystem/parser path in the matcher.
    # Codepoint escapes make all generated module bytes ASCII, including rare characters.
    def literal(char):
        return '"\\u{' + format(ord(char), 'x') + '}"'
    def packed_literal(text):
        return '"' + ''.join('\\t' if char == '\t' else '\\n' if char == '\n' else
                              char if ord(char) < 128 else '\\u{' + format(ord(char), 'x') + '}' for char in text) + '"'
    data = ['-- local_research: Tencent-derived static data; do not redistribute.',
            'local packed = require("bihua_packed_data")', 'return {', 'codes = {']
    data += [f'[{literal(char)}]="{codes[char].translate(TRANSLATION)}",' for char in sorted(exact)]
    data += ['},', 'prefixes = packed.prefixes({']
    for prefix in sorted(prefixes):
        packed = ''.join(row['candidate'] + '\t' + row['stored_score'] + '\t' + row['exact_match'] + '\n' for row in prefixes[prefix])
        data.append('["' + prefix.translate(TRANSLATION) + '"]=' + packed_literal(packed) + ',')
    data += ['})', '}', '']
    files = {
        'bihua_local.dict.yaml': '\n'.join(dictionary) + '\n',
        'bihua_local_data.lua': '\n'.join(data),
    }
    exports = dict(SOURCE_HASHES)
    association_keys = association_rows = phrase_rows = phrase_keys = missing_codes = 0
    if args.with_associations:
        name = 'wechat-mobile-continuations.tsv'
        if digest(args.source / name) != CONTINUATIONS_HASH:
            raise ValueError('Continuation export differs from the verified snapshot')
        continuations = read_tsv(args.source / name)
        if len(continuations) != 176329 or report['unresolved_continuation_keys'] != 0:
            raise ValueError('Incomplete continuation export')
        groups = {}
        for row in continuations:
            if int(row['suffix_length']) != 1:
                continue  # Product contract: recommend exactly one next character.
            key, suffix = row['previous_character'], row['suffix']
            group = groups.setdefault(key, [])
            if len(key) != 1 or len(suffix) != 1 or int(row['group_rank']) != len(group) + 1:
                raise ValueError('Invalid single-character continuation group')
            group.append(row)
        if len({row['previous_character'] for row in continuations}) != 4323 or len(groups) != 4234 or sum(map(len, groups.values())) != 98657:
            raise ValueError('Single-character continuation counts disagree')
        module = ['-- local_research: Tencent-derived continuation data; do not redistribute.', 'return require("bihua_packed_data").associations({']
        for key, group in sorted(groups.items()):
            packed = ''.join(row['suffix'] + '\t' + row['stored_integer_weight'] + '\n' for row in group)
            module.append('[' + literal(key) + ']=' + packed_literal(packed) + ',')
        module += ['})', '']
        files['bihua_local_associations.lua'] = '\n'.join(module)
        tails, missing_codes = {}, 0
        for row in continuations:
            first, suffix = row['previous_character'], row['suffix']
            if first not in codes or any(char not in codes for char in suffix):
                missing_codes += 1
                continue
            length = int(row['suffix_length'])
            if length != len(suffix) or length not in (1, 2, 3):
                raise ValueError('Invalid phrase suffix length')
            tails.setdefault(first, {}).setdefault(length, []).append(row)
        phrase_module = ['-- local_research: Tencent-derived phrase tails; do not redistribute.', 'return {codes={']
        for first in sorted(tails):
            phrase_module.append('[' + literal(first) + ']="' + codes[first].translate(TRANSLATION) + '",')
        phrase_module += ['},tails=require("bihua_packed_data").tails({']
        for first, tail_groups in sorted(tails.items()):
            phrase_module.append('[' + literal(first) + ']={')
            for length, group in sorted(tail_groups.items()):
                packed = ''.join(row['suffix'] + '\t' + row['stored_integer_weight'] + '\t' + '|'.join(codes[char].translate(TRANSLATION) for char in row['suffix']) + '\n' for row in group)
                phrase_module.append('[' + str(length) + ']=' + packed_literal(packed) + ',')
            phrase_module.append('},')
        phrase_module += ['})}', '']
        files['bihua_local_phrase_data.lua'] = '\n'.join(phrase_module)
        phrase_rows, phrase_keys = len(continuations) - missing_codes, len(tails)
        exports[name] = CONTINUATIONS_HASH
        association_keys, association_rows = len(groups), sum(map(len, groups.values()))
    manifest = dict(profile_id='wetype_android_4_0_0_static_local_v1',
                    source_role='local_research', source_apk_sha256=APK_HASH,
                    source_exports=exports, prefix_count=len(prefixes),
                    association_keys=association_keys, association_rows=association_rows,
                    phrase_rows=phrase_rows, phrase_keys=phrase_keys, phrase_missing_codes=missing_codes,
                    candidate_rows=len(rows), direct_characters=len(exact),
                    resource_metadata=report['resource_metadata'],
                    generated_files={name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()},
                    purpose='Local evaluation only; not mobile UI equivalence or a redistribution license')
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output / name).write_bytes(content.encode('utf-8'))
    (output / 'bihua_local.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
