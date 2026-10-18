"""Stage/update a current-user two-item, single-schema package; keep old package and user data."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import winreg

root=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('native_install',Path(__file__).with_name('Install-Native-Settings.py'))
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
home=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel'
def stage():
    stock=install.STOCK;package=root/'.verification/weasel-native/package-0.5.1'
    for name in ('WeaselServer.exe','BihuaSettingsLauncher.exe','weasel.dll','weaselx64.dll'):
        if not (package/name).is_file():raise FileNotFoundError(package/name)
    for name in ('rime.dll','WinSparkle.dll','WeaselDeployer.exe','LICENSE.txt','7z.exe','7z.dll','rime-install.bat','curl.exe','curl-ca-bundle.crt'):
        shutil.copy2(stock/name,package/name)
    if not (package/'data').exists():
        shutil.copytree(stock/'data',package/'data',ignore=shutil.ignore_patterns('*.schema.yaml'))
    user=Path(os.environ['APPDATA'])/'Rime'
    shutil.copy2(user/'bihua_mvp.schema.yaml',package/'data/bihua_mvp.schema.yaml')
    (package/'settings-script.txt').write_text(str(root/'scripts/Open-Settings.ps1')+'\n',encoding='utf-8')
    (package/'Start-Bihua.ps1').write_text("Start-Process -FilePath (Join-Path $PSScriptRoot 'WeaselServer.exe') -WindowStyle Hidden\n",encoding='utf-8-sig')
    schemas=list((package/'data').rglob('*.schema.yaml'))
    assert len(schemas)==1 and schemas[0].name=='bihua_mvp.schema.yaml'
    return package
def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
    package=stage()
    if not args.apply:print('Staged two-action package with exactly one schema.');return
    path=home/'installation.json';previous=json.loads(path.read_text(encoding='utf-8'))
    if previous['status']!='installed':raise RuntimeError('Expected installed current-user version')
    old=Path(previous['directory']);destination=home/'0.5.1'
    if destination.exists():raise RuntimeError('Destination exists; refusing an unrecorded overwrite')
    if not old.resolve().is_relative_to(home.resolve()):raise ValueError('Invalid old package directory')
    for entry in previous['registry']:
        if install.value(entry['path'],entry['name'],entry['view'])!=entry['installed']:
            raise RuntimeError('Current registration differs from installation receipt')
    personal=Path(os.environ['APPDATA'])/'Rime'
    watched=[personal/'bihua_personal_association_v1.jsonl',personal/'bihua_personal_phrases.tsv']
    before={str(file):hashlib.sha256(file.read_bytes()).hexdigest() for file in watched if file.exists()}
    shutil.copytree(package,destination)
    next_receipt=json.loads(json.dumps(previous));next_receipt['directory']=str(destination)
    next_receipt['version']='0.5.1';next_receipt['menu_actions']=2;next_receipt['only_schema']='bihua_mvp'
    next_receipt['previous_directory']=str(old)
    next_receipt['files']={file.name:hashlib.sha256(file.read_bytes()).hexdigest() for file in destination.iterdir() if file.is_file()}
    for entry in next_receipt['registry']:
        entry['installed']['data']=entry['installed']['data'].replace(str(old),str(destination))
    changed=[]
    try:
        # Stop via the currently installed executable, which the guard accepts.
        subprocess.run([str(old/'WeaselServer.exe'),'/q'],check=True,timeout=10)
        time.sleep(.3)
        for entry in next_receipt['registry']:
            install.write(entry['path'],entry['name'],entry['view'],entry['installed']);changed.append(entry)
        subprocess.Popen([str(destination/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(1)
        proof=subprocess.run([str(destination/'WeaselServer.exe'),'/bihua-engine-probe'],timeout=10)
        if proof.returncode:raise RuntimeError('New server failed real schema status check')
        # Stock late startup and cached old restart actions must not take over.
        late=subprocess.Popen([str(install.STOCK/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        late.wait(timeout=10)
        running=subprocess.run(['powershell','-NoProfile','-Command','Get-Process WeaselServer | Select-Object -ExpandProperty Path'],capture_output=True,text=True,timeout=10)
        if str(destination/'WeaselServer.exe').lower() not in running.stdout.lower():raise RuntimeError('Stock took over the custom server')
        assert before=={str(file):hashlib.sha256(file.read_bytes()).hexdigest() for file in watched if file.exists()},'Empty diagnostic sessions changed personal records'
        shutil.copy2(path,home/('installation-before-0.5.1-'+str(time.time_ns())+'.json'))
        install.panel.atomic_write(path,json.dumps(next_receipt,ensure_ascii=False,indent=2))
    except BaseException:
        for entry in reversed(changed):
            prior=next(x for x in previous['registry'] if (x['path'],x['name'],x['view'])==(entry['path'],entry['name'],entry['view']))
            install.write(entry['path'],entry['name'],entry['view'],prior['installed'])
        subprocess.run([str(destination/'WeaselServer.exe'),'/q'],timeout=10)
        subprocess.Popen([str(old/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        raise
    (root/'.verification/menu-upgrade-results.json').write_text(json.dumps({'result':'PASS','directory':str(destination),
        'single_schema':True,'stock_late_start_did_not_take_over':True,'personal_hashes_unchanged':before},indent=2),encoding='utf-8')
    print(json.dumps({'result':'PASS','directory':str(destination),'single_schema':True,'stock_takeover_blocked':True,'personal_data_unchanged':True}))
if __name__=='__main__':main()
