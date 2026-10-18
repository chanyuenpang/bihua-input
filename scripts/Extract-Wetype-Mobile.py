"""Static research export for the pinned WeChat Android 4.0.0 APK.

Does not execute, install, or load any code from the APK. Requires cityhash
0.4.10 (MIT; Google CityHash is BSD licensed). Extracted Tencent data remains
local research material; this script does not deploy it to the Rime MVP.
"""
import argparse
import csv
import hashlib
import json
import math
import struct
import sys
import zipfile
from pathlib import Path

APK_SHA256 = '940586c40ca1ddb7d7190a727c9a3e2846c5a30b290de427da8c24df814b9603'


class BinaryMap:
    def __init__(self, data):
        self.data = data
        flags, self.count = struct.unpack_from('<II', data)
        if flags != 0x80000001 or not 0 < self.count < 100000:
            raise ValueError('Unsupported hash map header')
        offsets = struct.unpack_from(f'<{self.count}I', data, 8)
        self.buckets = []
        for offset in offsets:
            n = struct.unpack_from('<I', data, offset)[0]
            if n > 100:
                raise ValueError('Unexpected bucket size')
            keys = struct.unpack_from(f'<{n}I', data, offset + 4)
            ends = struct.unpack_from(f'<{n}H', data, offset + 4 + 4 * n)
            base, prev, bucket = offset + 4 + 6 * n, 0, {}
            for key, end in zip(keys, ends):
                if end < prev or base + end > len(data) or key in bucket:
                    raise ValueError('Invalid bucket bounds or duplicate key')
                bucket[key] = data[base + prev:base + end]
                prev = end
            self.buckets.append(bucket)
        self.entries = sum(map(len, self.buckets))

    def lookup(self, key, cityhash):
        raw = key.encode('utf-8')
        bucket = cityhash.CityHash32(raw) % self.count
        fingerprint = cityhash.CityHash64WithSeed(raw, 0x1DBBA5) & 0xFFFFFFFF
        return (bucket, fingerprint), self.buckets[bucket].get(fingerprint)


def stroke_digits(raw):
    pos, digits = 0, []
    while pos < len(raw):
        header = raw[pos]
        pos += 1
        for group in range(4):
            width = ((header >> (2 * group)) & 3) + 1
            if pos + width > len(raw):
                raise ValueError('Truncated packed stroke block')
            word = int.from_bytes(raw[pos:pos + width], 'little')
            pos += width
            count = 0
            while word:
                digit = word & 15
                if digit:
                    if digit > 5:
                        raise ValueError('Invalid stroke digit')
                    digits.append(str(digit))
                    count += 1
                word >>= 4
            if count < 8:
                return ''.join(digits)
    return ''.join(digits)


def group_varints(raw):
    pos, values = 0, []
    while pos < len(raw):
        header = raw[pos]
        pos += 1
        for group in range(4):
            if pos == len(raw):
                break
            width = ((header >> (2 * group)) & 3) + 1
            if pos + width > len(raw):
                raise ValueError('Truncated candidate value')
            values.append(int.from_bytes(raw[pos:pos + width], 'little'))
            pos += width
    return values


def stroke_trie(data):
    """Read serialized arrays; skip rank/select indexes without evaluating them."""
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('Array exceeds file')
        result = data[pos:pos + n]
        pos += n
        return result

    def vector():
        nonlocal pos
        n = struct.unpack('<Q', take(8))[0]
        result = take(n)
        take((-n) % 8)
        return result

    children = vector()
    child_ends = struct.unpack(f'<{len(children)}I', vector())
    vector()  # unused payload ends
    vector()  # terminal bit vector
    take(8)   # bit count and population
    vector()  # rank index
    vector()  # select-one index
    vector()  # select-zero index
    stems, lengths = vector(), vector()
    stem_ends = struct.unpack(f'<{len(children)}I', vector())
    flags = struct.unpack('<I', take(4))[0]
    if flags != 0 or len(lengths) != len(children):
        raise ValueError('Unsupported stroke trie format')
    prefixes = [''] * len(children)
    for node, count in enumerate(children):
        start = 1 + (child_ends[node - 1] if node else 0)
        if start + count > len(children):
            raise ValueError('Invalid child range')
        for child in range(start, start + count):
            a = stem_ends[child - 1] if child else 0
            b = stem_ends[child]
            stem = stems[a:b].decode('ascii')
            if len(stem) != lengths[child] or not stem or set(stem) - set('12345'):
                raise ValueError('Invalid stroke trie stem')
            prefixes[child] = prefixes[node] + stem
    if not all(prefixes[1:]):
        raise ValueError('Unreachable trie node')
    return prefixes[1:], BinaryMap(data[pos:])


def write_tsv(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, delimiter='\t')
        writer.writerow(columns)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dependency-dir', type=Path)
    args = parser.parse_args()
    if args.dependency_dir:
        sys.path.insert(0, str(args.dependency_dir.resolve()))
    import cityhash

    with args.apk.open('rb') as apk_file:
        digest = hashlib.file_digest(apk_file, 'sha256').hexdigest()
    if digest != APK_SHA256:
        raise ValueError('APK differs from the verified Android 4.0.0 build')
    with zipfile.ZipFile(args.apk) as apk:
        index = json.loads(apk.read('assets/config/beta/index.json'))
        metadata = {}
        resources = {}
        for name in ('rsd.bin', 'sd.bin', 'sw.bin'):
            matches = [item for item in index if item['name'] == name]
            if len(matches) != 1:
                raise ValueError('Missing or duplicate resource metadata')
            resources[name] = apk.read('assets/config/beta/' + name)
            item = matches[0]
            if hashlib.md5(resources[name]).hexdigest() != item['md5']:
                raise ValueError('Resource does not match APK index')
            metadata[name] = {key: item[key] for key in ('type', 'version', 'md5')}
            metadata[name]['sha256'] = hashlib.sha256(resources[name]).hexdigest()
        reverse = BinaryMap(resources['rsd.bin'])
        prefixes, candidates = stroke_trie(resources['sd.bin'])
        continuation_map = BinaryMap(resources['sw.bin'])
    codes, reverse_seen = {}, set()
    for codepoint in range(1, 0x110000):
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        char = chr(codepoint)
        key, raw = reverse.lookup(char, cityhash)
        if raw is not None:
            if key in reverse_seen:
                raise ValueError('Unicode hash collision')
            codes[char] = stroke_digits(raw)
            reverse_seen.add(key)
    if len(reverse_seen) != reverse.entries:
        raise ValueError('Not all reverse stroke keys resolved')
    rows, candidate_seen, full_scores = [], set(), {}
    for prefix in prefixes:
        key, raw = candidates.lookup(prefix, cityhash)
        if raw is None or key in candidate_seen:
            raise ValueError('Unresolved or colliding stroke prefix')
        candidate_seen.add(key)
        values, pos, last_score = group_varints(raw), 1, math.inf
        for rank in range(1, values[0] + 1):
            length = values[pos]
            pos += 1
            char = ''.join(chr(x) for x in values[pos:pos + length])
            pos += length
            score = struct.unpack('<f', struct.pack('<I', values[pos]))[0]
            exact = values[pos + 1]
            pos += 2
            if length != 1 or char not in codes or not codes[char].startswith(prefix):
                raise ValueError('Candidate and reverse code disagree')
            if exact not in (0, 1) or bool(exact) != (codes[char] == prefix):
                raise ValueError('Exact-match flag disagrees with reverse code')
            if not math.isfinite(score) or score > last_score:
                raise ValueError('Invalid score or unsorted candidates')
            last_score = score
            rows.append((prefix, rank, char, score, exact))
            if exact:
                if char in full_scores:
                    raise ValueError('Duplicate full-code score')
                full_scores[char] = score
        if pos != len(values):
            raise ValueError('Unexpected candidate payload tail')
    if len(candidate_seen) != candidates.entries:
        raise ValueError('Not all candidate keys resolved')
    continuations, continuation_seen = [], set()
    for codepoint in range(1, 0x110000):
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        previous = chr(codepoint)
        key, raw = continuation_map.lookup(previous, cityhash)
        if raw is None:
            continue
        if key in continuation_seen:
            raise ValueError('Continuation key collision')
        continuation_seen.add(key)
        values = group_varints(raw)
        if not 1 <= values[0] <= 3:
            raise ValueError(f'Unexpected continuation group count: U+{codepoint:04X} {values[:10]}')
        pos = 1
        for expected_length in range(1, values[0] + 1):
            size = values[pos]
            pos += 1
            end, rank, previous_weight = pos + size, 0, math.inf
            while pos < end:
                length = values[pos]
                pos += 1
                if length != expected_length or pos + length + 1 > end:
                    raise ValueError('Continuation suffix length or bounds disagree')
                suffix = ''.join(chr(x) for x in values[pos:pos + length])
                pos += length
                weight = values[pos]
                pos += 1
                if weight > previous_weight:
                    raise ValueError('Unsorted continuation weights')
                previous_weight = weight
                rank += 1
                continuations.append((previous, suffix, length, rank, weight))
            if pos != end:
                raise ValueError('Continuation group payload tail')
        if pos != len(values):
            raise ValueError('Unexpected continuation payload tail')
    if len(continuation_seen) != continuation_map.entries:
        raise ValueError('Unresolved continuation keys')
    args.output.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output / 'wechat-mobile-strokes.tsv',
              ['codepoint', 'character', 'stroke_digits'],
              ((f'U+{ord(c):04X}', c, s) for c, s in codes.items()))
    write_tsv(args.output / 'wechat-mobile-stroke-candidates.tsv',
              ['stroke_prefix', 'stored_rank', 'candidate', 'stored_score', 'exact_match'], rows)
    write_tsv(args.output / 'wechat-mobile-full-code-scores.tsv',
              ['character', 'stroke_digits', 'full_code_stored_score'],
              ((c, codes[c], s) for c, s in sorted(full_scores.items(), key=lambda x: -x[1])))
    write_tsv(args.output / 'wechat-mobile-continuations.tsv',
              ['previous_character', 'suffix', 'suffix_length', 'group_rank', 'stored_integer_weight'], continuations)
    report = dict(apk_sha256=digest, application='WeChat mobile Android 4.0.0',
                  resource_metadata=metadata,
                  continuation_keys=len(continuation_seen), continuation_rows=len(continuations),
                  unresolved_continuation_keys=continuation_map.entries - len(continuation_seen),
                  reverse_records=len(codes), stroke_prefixes=len(prefixes),
                  candidate_rows=len(rows), full_code_scored_characters=len(full_scores),
                  unresolved_reverse_keys=reverse.entries - len(reverse_seen),
                  unresolved_candidate_keys=candidates.entries - len(candidate_seen),
                  candidate_code_or_flag_disagreements=0, score_order_inversions=0,
                  max_strokes=max(map(len, codes.values())),
                  samples={c: codes[c] for c in '疒国玉的我一天木'},
                  limits='Static stored scores, not corpus counts or verified live UI ranking. No Rime deployment.')
    (args.output / 'export-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
