"""The sole writer for personal stroke aliases; system codes are never changed."""
from pathlib import Path
import csv
import hashlib
import json
import re

from personal_data import association_lock, atomic_write, han

NAME = 'bihua_personal_strokes.tsv'
HEADER = '# bihua-personal-strokes-v1'
MAX_REVISION = 9007199254740991


def canonical_codes(data_directory=None, *, rime_directory=None):
    if rime_directory is not None:
        folder = Path(rime_directory)
        dictionary = folder / 'bihua_local.dict.yaml'
        if dictionary.exists():
            manifest = folder / 'bihua_local.manifest.json'
            if not dictionary.is_file() or dictionary.stat().st_size > 32 * 1024 * 1024 or not manifest.is_file():
                raise ValueError('系统码表不可用，未保存个人笔顺')
            expected = json.loads(manifest.read_text(encoding='utf-8-sig')).get('generated_files', {}).get(dictionary.name)
            contents = dictionary.read_bytes()
            if not expected or hashlib.sha256(contents).hexdigest() != expected:
                raise ValueError('系统码表校验失败，未保存个人笔顺')
            result, entries = {}, False
            for line in contents.decode('utf-8-sig').splitlines():
                if not entries:
                    entries = line.strip() == '...'
                    continue
                if not line or line.startswith('#'):
                    continue
                fields = line.split('\t')
                if len(fields) < 2 or len(fields[0]) != 1 or not re.fullmatch('[hspnz]{1,64}', fields[1]):
                    raise ValueError('系统码表格式错误，未保存个人笔顺')
                # Both supported profile builders put the default spelling first.
                result.setdefault(fields[0], fields[1].translate(str.maketrans('hspnz', '12345')))
            if not entries or not result:
                raise ValueError('系统码表为空，未保存个人笔顺')
            return result
    root = Path(__file__).resolve().parent.parent
    folder = Path(data_directory) if data_directory is not None else root / 'data'
    current = folder / 'current-canonical_strokes.tsv'
    source = current if current.exists() else folder / 'canonical_strokes.tsv'
    research = False
    if data_directory is None and not source.exists():
        source = root / '.verification/wetype-mobile/reproducible-export/wechat-mobile-strokes.tsv'
        research = True
    if not source.is_file() or source.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('标准笔顺表不可用，未保存个人笔顺')
    checksum = source.with_suffix('.sha256')
    if checksum.exists():
        expected = checksum.read_text(encoding='ascii').strip()
    elif research:
        expected = '5840b0fb6fadd0ca002e6eeb3aea507b157ddc7ecd0bcb0a558c5fd94398b23b'
    else:
        raise ValueError('标准笔顺表校验信息缺失，未保存个人笔顺')
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError('标准笔顺表校验失败，未保存个人笔顺')
    result = {}
    with source.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file, delimiter='\t')
        if not {'character', 'stroke_digits'} <= set(reader.fieldnames or []):
            raise ValueError('标准笔顺表格式错误，未保存个人笔顺')
        for row in reader:
            char, code = row['character'], row['stroke_digits']
            if not isinstance(char, str) or len(char) != 1 or char in result or not re.fullmatch('[1-5]{1,64}', code or ''):
                raise ValueError('标准笔顺表内容错误，未保存个人笔顺')
            result[char] = code
    if not result:
        raise ValueError('标准笔顺表为空，未保存个人笔顺')
    return result


def normalize(code):
    code = str(code).lower().replace('d', 'n').translate(str.maketrans('12345', 'hspnz'))
    if not re.fullmatch('[hspnz]{1,52}', code):
        raise ValueError('笔顺需要 1–52 个笔画（12345 或 hspnz）')
    return code


def parse(content, *, imported=False):
    if len(content.encode('utf-8')) > 4 * 1024 * 1024:
        raise ValueError('个人笔顺文件过大')
    lines = content.lstrip('\ufeff').splitlines()
    revision, rows = 0, {}
    if lines and lines[0].startswith(HEADER):
        fields = lines.pop(0).split('\t')
        if len(fields) != 2 or not fields[1].isdigit() or not 1 <= int(fields[1]) <= MAX_REVISION:
            raise ValueError('个人笔顺版本头损坏')
        revision = int(fields[1])
    elif not imported:
        raise ValueError('个人笔顺版本头缺失')
    for line in lines:
        if not line or (imported and line.startswith('#')):
            continue
        fields = line.split('\t')
        if len(fields) != 2:
            raise ValueError('每行需要：单字、Tab、笔顺')
        char, code = fields
        if len(char) != 1 or not han(char) or char in rows:
            raise ValueError('不是单个汉字或重复收录：' + char)
        if not imported and not re.fullmatch('[hspnz]{1,52}', code):
            raise ValueError('个人笔顺文件编码损坏')
        rows[char] = normalize(code)
    if len(rows) > 20000:
        raise ValueError('个人笔顺最多 20000 条')
    return revision, rows


def read(path):
    return parse(path.read_text(encoding='utf-8')) if path.exists() else (0, {})


def render(revision, rows):
    return HEADER + '\t' + str(revision) + '\n' + ''.join(char + '\t' + code + '\n' for char, code in sorted(rows.items()))


def action(directory, operation, *, char=None, code=None, content=None, replace=False):
    path = Path(directory) / NAME
    with association_lock(path):
        try:
            revision, before = read(path)
        except ValueError:
            if operation != 'restore-previous': raise
            previous_revision, _ = parse(path.with_name(path.name + '.previous').read_text(encoding='utf-8'))
            header=(path.read_text(encoding='utf-8',errors='replace').splitlines()+[''])[0]
            match=re.fullmatch(re.escape(HEADER)+r'\t([0-9]+)',header)
            revision=max(previous_revision,int(match[1]) if match and int(match[1])<MAX_REVISION else 0)
            before={}
        rows = before.copy()
        replaced = char in rows
        skipped_system = False
        if operation == 'upsert':
            if not isinstance(char, str) or len(char) != 1 or not han(char):
                raise ValueError('请选择单个汉字')
            normalized = normalize(code)
            standard = canonical_codes(rime_directory=directory).get(char, '')
            skipped_system = normalized == standard.translate(str.maketrans('12345', 'hspnz'))
            if not skipped_system:
                rows[char] = normalized
        elif operation == 'delete':
            if not isinstance(char, str) or len(char) != 1 or not han(char):
                raise ValueError('请选择单个汉字')
            rows.pop(char, None)
        elif operation == 'import':
            _, incoming = parse(content, imported=True)
            rows = incoming if replace else rows | incoming
        elif operation == 'restore-previous':
            _, rows = parse(path.with_name(path.name + '.previous').read_text(encoding='utf-8'))
        elif operation != 'list':
            raise ValueError('未知个人笔顺操作')
        if len(rows) > 20000:
            raise ValueError('个人笔顺最多 20000 条')
        changed = rows != before or operation == 'restore-previous'
        if changed:
            if revision >= MAX_REVISION:
                raise ValueError('个人笔顺版本已达上限')
            old = path.read_text(encoding='utf-8') if path.exists() else render(1, {})
            updated = render(revision + 1, rows)
            parse(updated)
            atomic_write(path.with_name(path.name + ('.before-restore' if operation=='restore-previous' else '.previous')), old)
            atomic_write(path, updated)
            try:
                if path.read_text(encoding='utf-8') != updated:
                    raise OSError('笔顺读回不一致')
            except Exception as error:
                try:
                    atomic_write(path, old)
                except Exception as recovery:
                    raise RuntimeError('recovery_required：保存未确认，请从 .previous 恢复。' + str(recovery)) from error
                raise RuntimeError('readback_failed_rolled_back：原记录已恢复，请重试。') from error
            revision += 1
        return {'status': 'applied', 'revision': revision, 'changed': changed,
                'skipped_system': skipped_system,
                'char': char, 'code': rows.get(char), 'replaced': replaced,
                'rows': [{'text': c, 'code': v, 'digits': v.translate(str.maketrans('hspnz', '12345'))} for c, v in sorted(rows.items())]}
