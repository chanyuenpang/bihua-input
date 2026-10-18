"""Local repair installer. Must run outside packaged development apps.

This payload contains private reference data and is not a distributable release.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import winreg

def physical(path):
    k=c.WinDLL('kernel32',use_last_error=True)
    k.CreateFileW.argtypes=[c.c_wchar_p,c.c_ulong,c.c_ulong,c.c_void_p,c.c_ulong,c.c_ulong,c.c_void_p];k.CreateFileW.restype=c.c_void_p
    k.GetFinalPathNameByHandleW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_ulong,c.c_ulong];k.CloseHandle.argtypes=[c.c_void_p]
    handle=k.CreateFileW(str(path),0,7,None,3,0x02000000,None)
    if handle==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
    buffer=c.create_unicode_buffer(32768)
    try:
        if not k.GetFinalPathNameByHandleW(handle,buffer,len(buffer),0):raise c.WinError(c.get_last_error())
        return buffer.value.removeprefix('\\\\?\\')
    finally:k.CloseHandle(handle)

def value(path,name,view):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|view) as key:
            data,kind=winreg.QueryValueEx(key,name);return {'data':data,'type':kind}
    except FileNotFoundError:return None

def write(entry,data):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,entry['path'],0,winreg.KEY_WRITE|entry['view']) as key:
        if data is None:
            try:winreg.DeleteValue(key,entry['name'])
            except FileNotFoundError:pass
        else:winreg.SetValueEx(key,entry['name'],0,data['type'],data['data'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    a.report.parent.mkdir(parents=True,exist_ok=True)
    local=Path(os.environ['LOCALAPPDATA']);roaming=Path(os.environ['APPDATA'])
    if Path(physical(local))!=local or Path(physical(roaming))!=roaming:
        raise RuntimeError('AppData is virtualized; run this installer outside Codex')
    home=local/'BihuaWeasel';home.mkdir(exist_ok=True);destination=home/'0.5.2'
    probe=home/('installation-view-probe-'+str(time.time_ns()))
    try:
        probe.write_text('view probe',encoding='utf-8')
        if Path(physical(probe))!=probe:
            raise RuntimeError('AppData writes are redirected; run the installer outside Codex')
    finally:probe.unlink(missing_ok=True)
    if destination.exists():raise RuntimeError('Install destination already exists; inspect previous receipt')
    package=a.payload.resolve();assert (package/'PRIVATE-LOCAL-REPAIR.json').exists()
    shutil.copytree(package,destination,ignore=shutil.ignore_patterns('user-data'))
    (destination/'settings-script.txt').write_text(str(destination/'scripts/Open-Settings.ps1')+'\n',encoding='utf-8')
    user=roaming/'Rime';user.mkdir(exist_ok=True)
    backup=home/('pre-independent-'+str(time.time_ns()));backup.mkdir()
    entries=[];clsid='{A3F4CDED-B1E9-41EE-9CA6-7B4D0DE6CB0A}'
    for view,name in ((winreg.KEY_WOW64_64KEY,'weaselx64.dll'),(winreg.KEY_WOW64_32KEY,'weasel.dll')):
        for key,data in (('',str(destination/name)),('ThreadingModel','Apartment')):
            path='Software\\Classes\\CLSID\\'+clsid+'\\InprocServer32'
            entries.append({'path':path,'name':key,'view':view,'before':value(path,key,view),'installed':{'data':data,'type':winreg.REG_SZ}})
    path='Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    entries.append({'path':path,'name':'BihuaWeasel','view':0,'before':value(path,'BihuaWeasel',0),'installed':{'data':'"'+str(destination/'WeaselServer.exe')+'"','type':winreg.REG_SZ}})
    path='Software\\Rime\\Weasel'
    entries.append({'path':path,'name':'RimeUserDir','view':0,'before':value(path,'RimeUserDir',0),'installed':{'data':str(user),'type':winreg.REG_SZ}})
    copied=[];changed=[];personal={}
    try:
        for source in (package/'user-data').iterdir():
            target=user/source.name
            if source.name.startswith('bihua_personal'):
                if target.exists():
                    personal[source.name]='existing physical data preserved; cached copy retained in private migration source';continue
                personal[source.name]='migrated without overwriting physical data'
            if target.exists():
                if target.is_dir():shutil.copytree(target,backup/source.name)
                else:shutil.copy2(target,backup/source.name)
            copied.append(source.name)
            if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True)
            else:shutil.copy2(source,target)
        for entry in entries:write(entry,entry['installed']);changed.append(entry)
        receipt={'status':'prepared','version':'0.5.2','directory':str(destination),'stock_directory':'C:\\Program Files\\Rime\\weasel-0.17.4',
                 'registry':entries,'only_schema':'bihua_mvp','menu_actions':2,'backup':str(backup),'personal':personal,'outside_packaged_app':True}
        (home/'installation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        deploy=subprocess.run([str(destination/'WeaselDeployer.exe'),'/deploy'],timeout=60)
        assert deploy.returncode==0,'Actual user-directory deployment failed'
        subprocess.Popen([str(destination/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(.7)
        assert subprocess.run([str(destination/'WeaselServer.exe'),'/bihua-engine-probe'],timeout=10).returncode==0
        assert 'status.schema_id=bihua_mvp' in (destination/'bihua-engine-session.txt').read_text()
        receipt['status']='installed';(home/'installation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'result':'PASS','directory':str(destination),'physical_directory':physical(destination),'user_data':physical(user),
                'registry':entries,'personal':personal,'settings_script':str(destination/'scripts/Open-Settings.ps1'),
                'python':str(destination/'python/pythonw.exe'),'backup':str(backup),'release_ready':False}
        a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    except BaseException:
        for entry in reversed(changed):write(entry,entry['before'])
        for name in copied:
            previous=backup/name;target=user/name
            if previous.exists():
                if previous.is_dir():shutil.copytree(previous,target,dirs_exist_ok=True)
                else:shutil.copy2(previous,target)
            elif target.is_file():target.unlink()
        raise

if __name__=='__main__':
    try:main()
    except BaseException as error:
        p=argparse.ArgumentParser();p.add_argument('--payload');p.add_argument('--report');a,_=p.parse_known_args()
        if a.report:Path(a.report).write_text(json.dumps({'result':'FAIL','error':str(error)}),encoding='utf-8')
        raise
