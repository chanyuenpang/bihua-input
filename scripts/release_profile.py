"""One pinned product-data source; never substitute another profile."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
DEFAULT_SOURCE=ROOT/'data/provided-wetype'
LOCK_PATH=ROOT/'packaging/provided-data.lock.json'
TABLES=('bihua_local.dict.yaml','bihua_local_data.lua','bihua_local_associations.lua','bihua_local_phrase_data.lua')

def verified_source(source=DEFAULT_SOURCE):
    source=Path(source)
    lock=json.loads(LOCK_PATH.read_text(encoding='utf-8'))
    if lock['source_role']!='user_provided' or set(lock['generated_files'])!=set(TABLES):
        raise ValueError('发布数据锁定信息不完整')
    for name,digest in lock['source_exports'].items():
        path=source/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('提供的微信数据缺失或校验失败，停止构建：'+name)
    return lock

def build(output,source=DEFAULT_SOURCE):
    output=Path(output);lock=verified_source(source)
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/Build-Local-Profile.py'),
                    '--source',str(source),'--output',str(output),'--with-associations'],
                   check=True,capture_output=True)
    manifest=json.loads((output/'bihua_local.manifest.json').read_text(encoding='utf-8'))
    for name,digest in lock['generated_files'].items():
        if hashlib.sha256((output/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('微信数据生成结果与已验证参考表不同：'+name)
    from personal_strokes import canonical_codes
    codes=canonical_codes(rime_directory=output)
    contents=('character\tstroke_digits\n'+''.join(char+'\t'+code+'\n' for char,code in sorted(codes.items()))).encode('utf-8')
    (output/'canonical_strokes.tsv').write_bytes(contents)
    (output/'canonical_strokes.sha256').write_text(hashlib.sha256(contents).hexdigest(),encoding='ascii')
    manifest.update(profile_id=lock['profile_id'],source_role=lock['source_role'],
                    reference_profile_id=lock['reference_profile_id'],
                    purpose='Product installation data selected by the project owner; preserves the supplied static snapshot and does not claim the complete mobile runtime algorithm.')
    (output/'bihua_local.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest
