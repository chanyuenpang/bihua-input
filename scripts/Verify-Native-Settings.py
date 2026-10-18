"""Read-only native menu, COM, executable-code and launcher verification."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import winreg

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('native_menus',Path(__file__).with_name('Patch-Native-Menus.py'))
menus=importlib.util.module_from_spec(spec);spec.loader.exec_module(menus)
def code_sections(path):
    data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    count=struct.unpack_from('<H',data,pe+6)[0];optional=struct.unpack_from('<H',data,pe+20)[0]
    start=pe+24+optional;out={}
    for index in range(count):
        offset=start+40*index;name=data[offset:offset+8].rstrip(b'\0').decode()
        length,address=struct.unpack_from('<II',data,offset+16)
        flags=struct.unpack_from('<I',data,offset+36)[0]
        if flags&0x20000000:out[name]=hashlib.sha256(data[address:address+length]).hexdigest()
    return out
def main():
    home=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel'
    receipt=json.loads((home/'installation.json').read_text(encoding='utf-8'));directory=Path(receipt['directory']);stock=Path(receipt['stock_directory'])
    results={'result':'PASS','directory':str(directory),'COM':{},'menus':{},'stock_code_preserved':{}}
    for name,probe in (('weaselx64.dll','ComProbe64.exe'),('weasel.dll','ComProbe32.exe')):
        result=subprocess.run([str(ROOT/'.verification/weasel-native/package'/probe)],capture_output=True,text=True,timeout=10)
        assert result.returncode==0 and str(directory/name).lower() in result.stdout.lower(),(probe,result.stdout,result.returncode)
        results['COM'][name]='loaded current-user DLL'
        assert code_sections(stock/name)==code_sections(directory/name),name
        results['stock_code_preserved'][name]=code_sections(directory/name)
        resources=menus.menus(directory/name);assert len(resources)==3
        assert all(menus.menu_items(data)==[(40018,'笔画输入法'),(40017,'笔画设置')] for _,_,data in resources)
        results['menus'][name]=len(resources)
    server_resources=menus.menus(directory/'WeaselServer.exe');assert len(server_resources)==3
    assert all(menus.menu_items(data)==[(40018,'笔画输入法'),(40017,'笔画设置')] for _,_,data in server_resources)
    results['menus']['WeaselServer.exe']=len(server_resources)
    launcher=json.loads((directory/'settings-last-launch.json').read_text(encoding='utf-8'))
    assert launcher['exit_code']==0
    results['native_menu_IPC_launcher_completed']=launcher
    for entry in receipt['registry']:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,entry['path'],0,winreg.KEY_READ|entry['view']) as key:
            value,kind=winreg.QueryValueEx(key,entry['name'])
        assert {'data':value,'type':kind}==entry['installed']
    results['registry_readback']=True
    shell=subprocess.run(['powershell','-NoProfile','-Command',
        "@(Get-Process explorer -ErrorAction SilentlyContinue | ForEach-Object { $_.Modules | Where-Object { $_.ModuleName -match '^weasel.*\\.dll$' } | Select-Object -ExpandProperty FileName }) | ConvertTo-Json -Compress"],
        capture_output=True,text=True,timeout=10)
    assert shell.returncode==0, 'Cannot inspect taskbar input-method modules'
    loaded=json.loads(shell.stdout) if shell.stdout.strip() else []
    if isinstance(loaded,str):loaded=[loaded]
    assert loaded, 'Taskbar input-method DLL not loaded; live menu verification incomplete'
    assert all(Path(path).parent==directory for path in loaded), 'Taskbar still uses old input-method DLL; reload taskbar before claiming menu deployed'
    results['actual_taskbar_modules']=loaded
    results['already_loaded_application_DLLs']='existing applications may need restart; no application terminated'
    results['login_startup']='custom Run starts immediately; stock late startup tested; actual logout/login not tested'
    assert [p.name for p in (directory/'data').rglob('*.schema.yaml')]==['bihua_mvp.schema.yaml']
    assert 'status.schema_id=bihua_mvp' in (directory/'bihua-engine-session.txt').read_text(encoding='utf-8')
    results['single_schema_and_real_session']=True
    results['files']={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in receipt['files']}
    (ROOT/'.verification/native-settings-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'result':'PASS','COM':results['COM'],'menus':results['menus'],'native_menu_IPC_launcher_completed':True}))
if __name__=='__main__':main()
