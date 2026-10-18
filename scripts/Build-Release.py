"""Assemble an allowlisted release; never copy the live Rime user directory."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import sys
import yaml
from key_bindings import LETTER, KEYPAD
import release_profile

ROOT=Path(__file__).resolve().parent.parent
VERSION='0.6.28'
OUT=ROOT/'.verification/release'/VERSION
APP=OUT/'payload'
DIST=ROOT/'dist'

def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    else:shutil.copy2(source,target)

def build():
    if (DIST/'releases'/VERSION).exists():
        raise FileExistsError('已发布版本不可覆盖，请先递增版本号：'+VERSION)
    APP.mkdir(parents=True,exist_ok=True);DIST.mkdir(exist_ok=True)
    private=ROOT/'.verification/independent-package-0.5.2'
    native=ROOT/'.verification/weasel-native'
    for name in ['rime.dll','WinSparkle.dll','WeaselDeployer.exe','BihuaSettingsLauncher.exe']:
        copy(private/name,APP/name)
    copy(native/'weasel-0.17.4/output/WeaselServer.exe',APP/'WeaselServer.exe')
    for name in ['bihua32.dll','bihua64.dll','BihuaProfileSetup.exe','LICENSE.txt']:
        copy(native/'package'/name,APP/name)
    copy(OUT/'Uninstall.exe',APP/'Uninstall.exe')
    copy(private/'python',APP/'python')
    for path in Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT').glob('*.dll'):
        copy(path,APP/path.name)
    for name in ['Open-Settings.ps1','Native-Settings.py','Settings-Panel.py','appearance.py','key_bindings.py','Manage-Personal.py','personal_data.py','personal_strokes.py','stroke_icons.py']:
        copy(ROOT/'scripts'/name,APP/'scripts'/name)
    for path in (ROOT/'packaging').glob('*.py'):copy(path,APP/'scripts'/path.name)
    for name in ['default.yaml','key_bindings.yaml','punctuation.yaml','symbols.yaml','weasel.yaml']:
        copy(private/'data'/name,APP/'data'/name)
    copy(private/'data/opencc',APP/'data/opencc')
    copy(ROOT/'settings',APP/'settings')
    copy(ROOT/'packaging/安装说明.txt',APP/'安装说明.txt')
    copy(ROOT/'packaging/安装说明.txt',DIST/'安装说明.txt')
    product_profile=OUT/'provided-profile'
    release_profile.build(product_profile)
    for name in ['canonical_strokes.tsv','canonical_strokes.sha256']:
        copy(product_profile/name,APP/'data'/name)
    profile=APP/'profile';(profile/'lua').mkdir(parents=True,exist_ok=True)
    for path in (ROOT/'rime/lua').glob('*.lua'):copy(path,profile/'lua'/path.name)
    for path in product_profile.glob('*.lua'):copy(path,profile/'lua'/path.name)
    for name in ['bihua_local.dict.yaml','bihua_local.manifest.json']:copy(product_profile/name,profile/name)
    schema=yaml.safe_load((ROOT/'rime/bihua_local.schema.yaml').read_text(encoding='utf-8'))
    schema['schema'].update(schema_id='bihua_mvp',name='笔画输入法',version=VERSION)
    schema['bihua_matcher'].update(personal_association=True,static_association=True,phrase_enabled=True,mobile_phrases=True)
    schema['engine']['processors'].insert(0,'lua_processor@*bihua_query_keys')
    schema['engine']['segmentors'].insert(0,'lua_segmentor@*bihua_query_segmentor')
    schema['bihua_phrase']={'dictionary':'bihua_local','user_dict':'bihua_mvp_phrase_v1'}
    schema['bihua_keys']={'letter_style':'standard','keypad_style':'standard',
                          'letter':LETTER['standard'],'keypad':KEYPAD['standard']}
    (profile/'bihua_mvp.schema.yaml').write_text(yaml.safe_dump(schema,allow_unicode=True,sort_keys=False),encoding='utf-8')
    (profile/'default.custom.yaml').write_text('patch:\n  schema_list:\n    - schema: bihua_mvp\n',encoding='utf-8')
    (profile/'weasel.custom.yaml').write_text('patch:\n  style/font_point: 18\n  style/horizontal: true\n',encoding='utf-8')
    notice='''笔画输入法 0.6.28 测试版

Windows 前端基于 Weasel 0.17.4，GNU GPL v3。修改后前端与后台源代码随安装包提供。
Rime 1.13.1: BSD-3-Clause, https://github.com/rime/librime
Product data: the project owner's supplied WeType Android 4.0.0 static snapshot.
The pinned source and generated hashes are recorded in packaging/provided-data.lock.json.
Includes character strokes, prefix candidate ranks, phrase tails and single-character continuations.
Original data rights remain with their respective owners; project code licensing does not relicense third-party data.
Python 3.13.12: PSF license, see python/LICENSE.txt.
PyYAML 6.0.3: MIT, see licenses/PyYAML-LICENSE.
Boost 1.84.0: Boost Software License 1.0, see licenses/BOOST-LICENSE_1_0.txt.
rxi/json.lua: MIT, see licenses/rxi-json-LICENSE.
OpenCC: Apache-2.0, https://github.com/BYVoid/OpenCC
WinSparkle 0.8.1: MIT, see licenses/WinSparkle-COPYING.
Microsoft Visual C++ runtime files are redistributable components of Visual Studio 2022.

The installer contains no personal dictionary, personal stroke aliases or learned user history.
'''
    (APP/'THIRD-PARTY.txt').write_text(notice,encoding='utf-8')
    copy(native/'package/LICENSE.txt',APP/'licenses/GPL-3.0.txt')
    copy(native/'boost_1_84_0/LICENSE_1_0.txt',APP/'licenses/BOOST-LICENSE_1_0.txt')
    copy(ROOT/'vendor/rxi-json/LICENSE',APP/'licenses/rxi-json-LICENSE')
    copy(Path('C:/Python314/Lib/site-packages/pyyaml-6.0.3.dist-info/licenses/LICENSE'),APP/'licenses/PyYAML-LICENSE')
    copy(ROOT/'.verification/release-tools/licenses',APP/'licenses')
    source_archive=DIST/f'BihuaInput-{VERSION}-source.zip'
    cached=None
    if '--reuse-source' in sys.argv and source_archive.exists():
        cached=source_archive.with_suffix('.cached.zip');shutil.copy2(source_archive,cached)
    with zipfile.ZipFile(source_archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for folder in ['native','rime','settings','packaging','assets']:
            for path in (ROOT/folder).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts: z.write(path,'project/'+path.relative_to(ROOT).as_posix())
        for name in ['Build-Release.py','Build-Open-Profile.py','Build-Local-Profile.py','Build-Provided-Profile.py','release_profile.py','Test-Provided-Data.py','Test-Provided-Rime.py','Settings-Panel.py','Native-Settings.py','appearance.py','Open-Settings.ps1','Manage-Personal.py','personal_data.py','personal_strokes.py','Test-Personal-Strokes.py','Test-Personal-Stroke-Save.py','key_bindings.py','stroke_icons.py','Test-Release-Transactions.py','Test-Installer-Scheduler.py','Test-Appearance.py','Test-Settings-Panel.py','Patch-Single-Menu.py','Patch-Native-Source.py','Patch-Native-Menus.py','Patch-Independent-Profile.py','Patch-Mouse-Input.py']:
            z.write(ROOT/'scripts'/name,'project/scripts/'+name)
        lock=release_profile.verified_source()
        for name in lock['source_exports']:
            z.write(release_profile.DEFAULT_SOURCE/name,'data/provided-wetype/'+name)
        if cached:
            with zipfile.ZipFile(cached) as old:
                for item in old.infolist():
                    if not item.filename.startswith(('project/','data/provided-wetype/','data/conway/')):z.writestr(item,old.read(item))
        else:
            dependency_source(z,native)
    if cached:cached.unlink()
    copy(source_archive,APP/'source.zip')
    finalize()

def dependency_source(z,native):
        weasel=native/'weasel-0.17.4'
        for path in weasel.rglob('*'):
            rel=path.relative_to(weasel)
            if any(part in ['output','msbuild','lib','lib64','.git'] for part in rel.parts):continue
            if path.is_file() and path.suffix.lower() not in ['.obj','.pdb','.dll','.exe','.lib','.bin','.ipch']:
                z.write(path,'weasel-0.17.4/'+rel.as_posix())
        boost=native/'boost_1_84_0'
        archive=native/'boost_1_84_0.7z'
        assert hashlib.sha256(archive.read_bytes()).hexdigest()=='81a4d10075731966477276c47324ecd9cac02da49899d36c48eba66e40014f25'
        z.write(archive,'dependencies/boost_1_84_0.7z',compress_type=zipfile.ZIP_STORED)
        z.write(boost/'LICENSE_1_0.txt','boost-1.84.0/LICENSE_1_0.txt')
def finalize():
    manifest={'version':VERSION,'product':'BihuaInput','profile':json.loads(release_profile.LOCK_PATH.read_text(encoding='utf-8'))['profile_id'],'files':{}}
    for path in sorted(APP.rglob('*')):
        if path.is_file() and path.name!='release-manifest.json':
            rel=path.relative_to(APP).as_posix()
            assert not any(x in rel for x in ['.userdb','migration-preserved','wetype-mobile','__pycache__'])
            assert 'bihua_personal' not in rel or rel=='profile/lua/bihua_personal_stroke_runtime.lua'
            manifest['files'][rel]=hashlib.sha256(path.read_bytes()).hexdigest()
    (APP/'release-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    zip_path=OUT/'payload.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in APP.rglob('*'):
            if path.is_file():z.write(path,path.relative_to(APP).as_posix())
    print(json.dumps({'payload':str(APP),'zip':str(zip_path),'source':str(DIST/f'BihuaInput-{VERSION}-source.zip'),'files':len(manifest['files'])}))

if __name__=='__main__':build()
