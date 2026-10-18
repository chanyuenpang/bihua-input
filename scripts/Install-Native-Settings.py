"""Install a reversible, current-user Weasel menu extension; stock installation stays intact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import winreg
import importlib.util
spec=importlib.util.spec_from_file_location('bihua_panel',Path(__file__).with_name('Settings-Panel.py'))
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)

ROOT=Path(__file__).resolve().parent.parent
CLSID='{A3F4CDED-B1E9-41EE-9CA6-7B4D0DE6CB0A}'
STOCK=Path('C:/Program Files/Rime/weasel-0.17.4')
HOME=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel'
def value(path,name,view):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|view) as k:
            data,kind=winreg.QueryValueEx(k,name)
            return {'data':data,'type':kind}
    except FileNotFoundError:return None
def write(path,name,view,data):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_WRITE|view) as k:
        if data is None:
            try:winreg.DeleteValue(k,name)
            except FileNotFoundError:pass
        else:winreg.SetValueEx(k,name,0,data['type'],data['data'])

def restore_registry(entries):
    # Preflight the entire restore before changing any value.
    for entry in entries:
        if value(entry['path'],entry['name'],entry['view']) not in (entry['installed'],entry['before']):
            raise RuntimeError('Registry changed externally; restore stopped')
    for entry in reversed(entries):
        write(entry['path'],entry['name'],entry['view'],entry['before'])
    for path,view in {(entry['path'],entry['view']) for entry in entries if entry.get('created_key')}:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|view) as key:
                children,values,_=winreg.QueryInfoKey(key)
            if children==0 and values==0:winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,path,view)
        except FileNotFoundError:pass
def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--restore',action='store_true');a=p.parse_args()
    HOME.mkdir(parents=True,exist_ok=True);receipt=HOME/'installation.json'
    if a.restore:
        state=json.loads(receipt.read_text(encoding='utf-8'))
        restore_registry(state['registry'])
        style=state.get('tray_style')
        if style:
            path=Path(style['path']);text=panel.read(path)
            current=panel.decode(text).get('patch',{}).get('style/display_tray_icon')
            if current is True:
                replacement=style['before'] if style['existed'] else panel.REMOVE
                panel.atomic_write(path,panel.patch_text(text,{'style/display_tray_icon':replacement}))
        subprocess.run([str(Path(state['directory'])/'WeaselServer.exe'),'/q'],timeout=10,check=True)
        subprocess.Popen([str(STOCK/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        state['status']='restored';receipt.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Original registration and server restored; package retained for recovery.');return
    stage_spec=importlib.util.spec_from_file_location('native_upgrade',Path(__file__).with_name('Upgrade-Native-Menu.py'))
    stage_module=importlib.util.module_from_spec(stage_spec);stage_spec.loader.exec_module(stage_module)
    directory=HOME/'0.5.1';package=stage_module.stage()
    if receipt.exists():
        previous=json.loads(receipt.read_text(encoding='utf-8'))
        if previous['status'] not in ('restored','rolled_back'):
            raise RuntimeError('Native installation already recorded; inspect or restore before replacing')
        receipt.rename(HOME/('installation-'+str(time.time_ns())+'.json'))
    for name in ('WeaselServer.exe','BihuaSettingsLauncher.exe','weasel.dll','weaselx64.dll'):
        if not (package/name).is_file():raise FileNotFoundError(package/name)
    plan=[]
    for view,name in ((winreg.KEY_WOW64_64KEY,'weaselx64.dll'),(winreg.KEY_WOW64_32KEY,'weasel.dll')):
        path='Software\\Classes\\CLSID\\'+CLSID+'\\InprocServer32'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|view):pass
            created=False
        except FileNotFoundError:created=True
        for key,data in (('',str(directory/name)),('ThreadingModel','Apartment')):
            plan.append({'path':path,'name':key,'view':view,'created_key':created,'before':value(path,key,view),'installed':{'data':data,'type':winreg.REG_SZ}})
    plan.append({'path':'Software\\Rime\\Weasel','name':'BihuaOriginalInstallDir','view':0,'before':value('Software\\Rime\\Weasel','BihuaOriginalInstallDir',0),'installed':{'data':str(STOCK),'type':winreg.REG_SZ}})
    system=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    startup=f'"{system}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{directory / "Start-Bihua.ps1"}"'
    plan.append({'path':'Software\\Microsoft\\Windows\\CurrentVersion\\Run','name':'BihuaWeasel','view':0,'before':value('Software\\Microsoft\\Windows\\CurrentVersion\\Run','BihuaWeasel',0),'installed':{'data':startup,'type':winreg.REG_SZ}})
    if not a.apply:
        print(json.dumps({'directory':str(directory),'registry':plan},ensure_ascii=True,indent=2));return
    if directory.exists():directory=HOME/('0.5.1-'+str(time.time_ns()))
    # The destination is now final: regenerate every installed path accordingly.
    for entry in plan:
        entry['installed']['data']=entry['installed']['data'].replace(str(HOME/'0.5.1'),str(directory))
    shutil.copytree(package,directory)
    state={'directory':str(directory),'stock_directory':str(STOCK),'registry':plan,'status':'prepared',
           'version':'0.5.1','menu_actions':2,'only_schema':'bihua_mvp',
           'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in directory.iterdir() if f.is_file()}}
    receipt.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    applied=[]
    rime_dir=value('Software\\Rime\\Weasel','RimeUserDir',0)
    style_path=Path(rime_dir['data'] if rime_dir else str(Path(os.environ['APPDATA'])/'Rime'))/'weasel.custom.yaml'
    style_text=panel.read(style_path);style_patch=panel.decode(style_text).get('patch',{})
    changed_style=panel.patch_text(style_text,{'style/display_tray_icon':True})
    state['tray_style']={'path':str(style_path),'existed':'style/display_tray_icon' in style_patch,'before':style_patch.get('style/display_tray_icon')}
    receipt.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        panel.atomic_write(style_path,changed_style)
        for entry in plan:
            if value(entry['path'],entry['name'],entry['view'])!=entry['before']:raise RuntimeError('Registry changed during installation')
            write(entry['path'],entry['name'],entry['view'],entry['installed']);applied.append(entry)
        subprocess.Popen([str(directory/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(2)
        result=subprocess.run(['powershell','-NoProfile','-Command',"Get-Process WeaselServer | Select-Object -ExpandProperty Path"],capture_output=True,text=True,timeout=10)
        if str(directory/'WeaselServer.exe').lower() not in result.stdout.lower():raise RuntimeError('Custom server did not start')
        state['status']='installed';receipt.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    except BaseException:
        restore_registry(applied)
        panel.atomic_write(style_path,style_text)
        subprocess.Popen([str(STOCK/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        state['status']='rolled_back';receipt.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');raise
    print(json.dumps({'status':'installed','directory':str(directory),'receipt':str(receipt)}))
if __name__=='__main__':main()
