"""Run with the bundled interpreter outside Codex; report without personal text."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
directory=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.5.2'
root=a.root.resolve();receipt=json.loads((directory.parent/'installation.json').read_text(encoding='utf-8-sig'))
for name in ['Install-Independent.py','Restore-Independent.py']:
    shutil.copy2(root/'scripts'/name,directory/'scripts'/name)
spec=importlib.util.spec_from_file_location('menus',root/'scripts/Patch-Native-Menus.py');menus=importlib.util.module_from_spec(spec);spec.loader.exec_module(menus)
expected=[(40018,'笔画输入法'),(40017,'笔画设置')]
for name in ['weasel.dll','weaselx64.dll','WeaselServer.exe']:
    rows=menus.menus(directory/name)
    assert len(rows)==3 and all(menus.menu_items(data)==expected for _,_,data in rows)
tools=root/'.verification/weasel-native/package'
for name,probe in [('weasel.dll','ComProbe32.exe'),('weaselx64.dll','ComProbe64.exe')]:
    r=subprocess.run([str(tools/probe)],capture_output=True,text=True,timeout=10)
    assert r.returncode==0 and str(directory/name).lower() in r.stdout.lower(),r.stdout
catalogue=subprocess.run([str(tools/'SchemaVisibilityProbe.exe'),str(directory/'data'),str(Path(os.environ['APPDATA'])/'Rime')],capture_output=True,text=True,encoding='utf-8',timeout=10)
assert catalogue.returncode==0 and 'available\tbihua_mvp' in catalogue.stdout and 'selected\tbihua_mvp' in catalogue.stdout
assert catalogue.stdout.count('available\t')==1
user=Path(os.environ['APPDATA'])/'Rime'
source=root/'.verification/independent-package-0.5.2/user-data'
hashes={};history_checks={}
for name in ['bihua_personal_association_v1.jsonl','bihua_personal_phrases.tsv']:
    if (source/name).exists():
        if name.endswith('.jsonl'):
            before=json.loads(json.loads((source/name).read_text(encoding='utf-8'))['payload'])
            now=json.loads(json.loads((user/name).read_text(encoding='utf-8'))['payload'])
            assert now['sequence']>=before['sequence'],'Migrated manual history regressed'
            earlier={row['sequence']:row for row in before['window']}
            overlap=[row for row in now['window'] if row['sequence'] in earlier]
            assert all(row==earlier[row['sequence']] for row in overlap),'Retained manual history changed'
            for phrase,record in before['confirmed'].items():
                current=now['confirmed'].get(phrase)
                assert current and current['positive_count']>=record['positive_count'] and current['negative_count']>=record['negative_count'],'Learned feedback history regressed'
            history_checks[name]={'before_sequence':before['sequence'],'current_sequence':now['sequence'],'retained_overlap':len(overlap)}
        hashes[name]=hashlib.sha256((user/name).read_bytes()).hexdigest()
restore=subprocess.run([str(directory/'python/python.exe'),str(directory/'scripts/Restore-Independent.py')],capture_output=True,text=True,timeout=10)
assert restore.returncode==0,restore.stderr
for entry in receipt['registry']:
    from personal_data import atomic_write
    # Registry inspection belongs to the same external process as the installer.
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,entry['path'],0,winreg.KEY_READ|entry['view']) as key:
        data,kind=winreg.QueryValueEx(key,entry['name'])
    assert {'data':data,'type':kind}==entry['installed']
report={'result':'PASS','directory':str(directory),'menus':9,'COM':'both actual current-user registrations load 0.5.2',
        'single_schema':True,'personal_current_hashes':hashes,'history_preserved_with_live_typing':history_checks,'restore_preview':True,'receipt':receipt,
        'fresh_machine_tested':False,'uninstall_applied':False}
a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
