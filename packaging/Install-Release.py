"""Per-user installation transaction for the redistributable Windows package."""
import sys
sys.dont_write_bytecode=True
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import winreg
import yaml
import xml.etree.ElementTree as ET

APP=Path(__file__).resolve().parent.parent
HOME=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel'
RECEIPT=APP/'user-install.json'

def physical_install_directory():
    # Packaged desktop hosts can redirect AppData. Never register a redirected copy.
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes=[w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD]
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateFileW(str(APP/'WeaselServer.exe'),0,7,None,3,0,None)
    if handle==w.HANDLE(-1).value:raise OSError(c.get_last_error(),'无法读取安装目录')
    try:
        value=c.create_unicode_buffer(32768)
        if not kernel.GetFinalPathNameByHandleW(handle,value,len(value),0):raise OSError(c.get_last_error(),'无法解析安装目录')
        if Path(value.value.removeprefix('\\\\?\\')).parent!=APP:raise ValueError('请从文件资源管理器双击安装包，当前应用重定向了安装目录')
    finally:kernel.CloseHandle(handle)
def run(args,**kwargs):
    return subprocess.run(list(map(str,args)),check=True,timeout=kwargs.pop('timeout',90),creationflags=subprocess.CREATE_NO_WINDOW,**kwargs)

def server_info():
    ui=c.WinDLL('user32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
    ui.FindWindowW.argtypes=[w.LPCWSTR,w.LPCWSTR];ui.FindWindowW.restype=w.HWND
    ui.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes=[w.HANDLE]
    window=ui.FindWindowW('WeaselIPCWindow_1.0',None)
    if not window:return None
    pid=w.DWORD();ui.GetWindowThreadProcessId(window,c.byref(pid))
    process=kernel.OpenProcess(0x1000,False,pid.value)
    if not process:raise RuntimeError('无法核对输入法后台进程')
    try:
        path=c.create_unicode_buffer(32768);size=w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(process,0,path,c.byref(size)):raise RuntimeError('无法核对输入法后台路径')
        return {'pid':pid.value,'path':Path(path.value).resolve(),'window':window}
    finally:kernel.CloseHandle(process)

def wait_for_server():
    deadline=time.monotonic()+30
    last_error=None
    while time.monotonic()<deadline:
        try:
            info=server_info()
            if not info or info['path']!=APP/'WeaselServer.exe':
                last_error='后台运行版本与安装目录不一致：'+str(info and info['path'])
                if not info:run(['schtasks.exe','/Run','/TN','BihuaInputMethod'],capture_output=True)
                time.sleep(.5)
                continue
            run([APP/'WeaselServer.exe','/bihua-engine-probe'],timeout=5)
            current=server_info()
            if current and current['pid']==info['pid'] and current['path']==info['path']:return
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
            last_error=error
            time.sleep(.2)
    raise RuntimeError('输入法后台未能就绪：'+str(last_error))

def stop_owned_server(executable=None):
    info=server_info()
    if not info:return
    executable=Path(executable).resolve() if executable else info['path']
    if not executable.is_relative_to(HOME.resolve()) or executable.name.lower()!='weaselserver.exe':
        raise ValueError('后台路径不属于笔画输入法')
    if info['path']!=executable:return
    # An old pipe peer can stall its API lock. Its own GUI loop can still shut
    # down cleanly; verify the process image before sending that close request.
    ui=c.WinDLL('user32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
    ui.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
    ui.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
    kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.CloseHandle.argtypes=[w.HANDLE]
    window=info['window']
    process=kernel.OpenProcess(0x100000|0x1000,False,info['pid'])
    if not process:raise RuntimeError('无法核对旧后台进程，未关闭其他程序')
    try:
        path=c.create_unicode_buffer(32768);size=w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(process,0,path,c.byref(size)) or Path(path.value).resolve()!=executable:
            raise RuntimeError('后台窗口不属于旧安装，未关闭其他程序')
        if kernel.WaitForSingleObject(process,0)==0:return
        try:run([executable,'/q'],timeout=8)
        except (subprocess.TimeoutExpired,subprocess.CalledProcessError):pass
        # /q acknowledges the request before the process (and its task instance)
        # necessarily exits. Never treat that acknowledgement as an exit barrier.
        if kernel.WaitForSingleObject(process,5000)==0:return
        pid=w.DWORD();ui.GetWindowThreadProcessId(window,c.byref(pid))
        if pid.value!=info['pid'] or not ui.PostMessageW(window,0x10,0,0) or kernel.WaitForSingleObject(process,15000)!=0:
            raise RuntimeError('旧后台未能正常退出，未强制结束进程')
    finally:kernel.CloseHandle(process)
def psquote(value):return "'"+str(value).replace("'","''")+"'"
def powershell(script):
    command="[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$ErrorActionPreference='Stop';try{"+script+"}catch{[Console]::Error.WriteLine($_.Exception.Message);exit 1};exit 0"
    try:result=run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-Command',command],capture_output=True)
    except subprocess.CalledProcessError as error:
        detail=(error.stderr or error.stdout or b'').decode('utf-8-sig',errors='replace').strip()
        raise RuntimeError('Windows 配置操作失败：'+(detail or '系统未返回详细原因，退出码 '+str(error.returncode))) from error
    return result.stdout.decode('utf-8-sig',errors='replace').strip()
def verify():
    manifest=json.loads((APP/'release-manifest.json').read_text(encoding='utf-8-sig'))
    assert manifest['product']=='BihuaInput' and manifest['version']=='0.6.29'
    for name,expected in manifest['files'].items():
        target=(APP/name).resolve();assert target.is_relative_to(APP)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:raise ValueError('安装文件损坏：'+name)
    return len(manifest['files'])
def reg_read(path,name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
            value,kind=winreg.QueryValueEx(key,name);return {'value':value,'type':kind}
    except FileNotFoundError:return None
def reg_write(path,name,item):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:
        if item is None:
            try:winreg.DeleteValue(key,name)
            except FileNotFoundError:pass
        else:winreg.SetValueEx(key,name,0,item['type'],item['value'])
def task_xml():
    text=powershell("$s=New-Object -ComObject Schedule.Service;$s.Connect();$t=$null;"+
        "try{$t=$s.GetFolder('\\').GetTask('BihuaInputMethod')}catch{if($_.Exception.HResult -ne -2147024894){throw}};"+
        "if($t){[Console]::Write($t.Xml)}")
    if text:
        command=ET.fromstring(text).find('.//{http://schemas.microsoft.com/windows/2004/02/mit/task}Exec/{http://schemas.microsoft.com/windows/2004/02/mit/task}Command')
        if command is None or not Path(command.text).resolve().is_relative_to(HOME.resolve()):raise ValueError('已有同名启动任务不属于笔画输入法，未覆盖')
    return text
def create_task(enabled=True):
    powershell("$bihuaSchedule=New-Object -ComObject Schedule.Service;$bihuaSchedule.Connect();$d=$bihuaSchedule.NewTask(0);"+
      "$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;$d.Principal.UserId=$sid;$d.Principal.LogonType=3;"+
      "$d.Settings.ExecutionTimeLimit='PT0S';$d.Settings.DisallowStartIfOnBatteries=$false;$d.Settings.StopIfGoingOnBatteries=$false;$d.Settings.Hidden=$true;$d.Settings.MultipleInstances=2;"+
      "$d.Settings.Enabled="+('$true' if enabled else '$false')+";"+
      "$t=$d.Triggers.Create(9);$t.UserId=$sid;$a=$d.Actions.Create(0);$a.Path="+psquote(APP/'WeaselServer.exe')+";$a.WorkingDirectory="+psquote(APP)+";$null=$bihuaSchedule.GetFolder('\\').RegisterTaskDefinition('BihuaInputMethod',$d,6,$sid,$null,3)")
def restore_task(xml,backup):
    current=task_xml()
    if current:
        command=ET.fromstring(current).find('.//{http://schemas.microsoft.com/windows/2004/02/mit/task}Exec/{http://schemas.microsoft.com/windows/2004/02/mit/task}Command').text
        if Path(command).resolve()!=APP/'WeaselServer.exe':return
    if xml:
        path=backup/'previous-task.xml';path.write_text(xml,encoding='utf-16')
        run(['schtasks.exe','/Create','/TN','BihuaInputMethod','/XML',path,'/F'],capture_output=True)
    elif current:run(['schtasks.exe','/Delete','/TN','BihuaInputMethod','/F'],capture_output=True)
def helper(mode,*args):
    output=APP/('profile-'+uuid.uuid4().hex+'.json')
    run([APP/'BihuaProfileSetup.exe',mode,Path(os.environ['ProgramFiles'])/'BihuaInputMethod/0.5.11',output,*args])
    return json.loads(output.read_text(encoding='utf-8-sig'))
def machine_profile():
    dest=Path(os.environ['ProgramFiles'])/'BihuaInputMethod/0.5.11'
    key=r'Software\Classes\CLSID\{1D31BF35-F1B8-4352-980E-B337264D82FB}\InprocServer32'
    good=True
    for view,name in [(winreg.KEY_WOW64_64KEY,'bihua64.dll'),(winreg.KEY_WOW64_32KEY,'bihua32.dll')]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,key,0,winreg.KEY_READ|view) as handle:registered=winreg.QueryValue(handle,None)
            good=good and Path(registered)==dest/name and hashlib.sha256((dest/name).read_bytes()).digest()==hashlib.sha256((APP/name).read_bytes()).digest()
        except (FileNotFoundError,OSError):good=False
    if good:return
    class EXEC(c.Structure):
        _fields_=[('size',w.DWORD),('mask',w.ULONG),('window',w.HWND),('verb',w.LPCWSTR),('file',w.LPCWSTR),('parameters',w.LPCWSTR),('directory',w.LPCWSTR),('show',c.c_int),('instance',w.HINSTANCE),('idlist',c.c_void_p),('class_name',w.LPCWSTR),('class_key',w.HKEY),('hotkey',w.DWORD),('icon',w.HANDLE),('process',w.HANDLE)]
    output=APP/'machine-install.json'
    info=EXEC();info.size=c.sizeof(info);info.mask=0x40;info.verb='runas';info.file=str(APP/'BihuaProfileSetup.exe');info.parameters=subprocess.list2cmdline(['--machine',str(APP),str(output)]);info.show=0
    shell=c.WinDLL('shell32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[c.POINTER(EXEC)];kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.CloseHandle.argtypes=[w.HANDLE]
    if not shell.ShellExecuteExW(c.byref(info)):raise RuntimeError('安装输入法组件需要管理员确认；尚未更改输入方案')
    kernel.WaitForSingleObject(info.process,120000);kernel.CloseHandle(info.process)
    if not output.exists() or json.loads(output.read_text(encoding='utf-8-sig')).get('phase')!='machine_registered':raise RuntimeError('Windows输入法组件注册未完成')
def install():
    verify()
    physical_install_directory()
    if RECEIPT.exists():
        old=json.loads(RECEIPT.read_text(encoding='utf-8-sig'))
        if old.get('status')=='installed':
            create_task()
            info=server_info()
            if info and info['path']!=APP/'WeaselServer.exe':stop_owned_server()
            helper('--activate');run(['schtasks','/Run','/TN','BihuaInputMethod'],capture_output=True)
            wait_for_server()
            return {'result':'PASS','already_installed':True,'frontend_reload_policy':'reopen_existing_applications'}
    if APP.resolve()!= (HOME/'0.6.29').resolve():raise ValueError('安装目录不是本机用户目录，请双击安装程序')
    machine_profile()
    backup=HOME/'installer-backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
    old_profile=helper('--inspect')
    rime=reg_read(r'Software\Rime\Weasel','RimeUserDir')
    user=Path(rime['value']) if rime and Path(rime['value']).exists() else Path(os.environ['APPDATA'])/'Rime'
    user.mkdir(parents=True,exist_ok=True)
    previous_global=HOME/'installation.json'
    global_bytes=previous_global.read_bytes() if previous_global.exists() else None
    if global_bytes: (backup/'installation.json').write_bytes(global_bytes)
    previous_task=task_xml()
    record={'status':'preparing','directory':str(APP),'backup':str(backup),'user':str(user),'profile':old_profile,'task':previous_task,'global_before':bool(global_bytes),'files':[],'registry':[]}
    def put(target,contents):
        target=Path(target)
        for item in record['files']:
            if item['path']==str(target):
                target.write_bytes(contents);item['installed_hash']=hashlib.sha256(contents).hexdigest();return
        existing=target.exists();saved=backup/('file-'+str(len(record['files'])))
        if existing:shutil.copy2(target,saved)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(contents)
        record['files'].append({'path':str(target),'backup':str(saved) if existing else None,'installed_hash':hashlib.sha256(contents).hexdigest()})
    def setreg(path,name,value,kind=winreg.REG_SZ):
        item={'path':path,'name':name,'before':reg_read(path,name),'installed':{'value':value,'type':kind}};reg_write(path,name,item['installed']);record['registry'].append(item)
    try:
        # Prevent a still-open TSF client from waking the previous task while
        # files are replaced. Its original definition is already in the journal.
        create_task(enabled=False)
        stop_owned_server()
        for source in (APP/'profile').rglob('*'):
            if not source.is_file():continue
            rel=source.relative_to(APP/'profile');target=user/rel
            if source.name in ['default.custom.yaml','weasel.custom.yaml'] and target.exists():continue
            put(target,source.read_bytes())
        spec=importlib.util.spec_from_file_location('panel',APP/'scripts/Settings-Panel.py');panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
        default=user/'default.custom.yaml';put(default,panel.patch_text(panel.read(default),{'schema_list':[{'schema':'bihua_mvp'}]}).encode('utf-8'))
        # Product base tables always come from the pinned package. Personal
        # files and custom settings remain independent and are never replaced.
        schema=yaml.safe_load(panel.read(user/'build/bihua_mvp.schema.yaml') or panel.read(user/'bihua_mvp.schema.yaml')) or {}
        filters=schema.get('engine',{}).get('filters',['simplifier','uniquifier'])
        carry_filter='lua_filter@*bihua_association_filter'
        if carry_filter not in filters:
            custom=user/'bihua_mvp.custom.yaml'
            put(custom,panel.patch_text(panel.read(custom),{'engine/filters':[*filters,carry_filter]}).encode('utf-8'))
        # Rebuild the display projection from the verified active dictionary;
        # old releases may have kept a display table from a different profile.
        standard=panel.canonical_codes(rime_directory=user)
        current=APP/'data/current-canonical_strokes.tsv'
        contents='character\tstroke_digits\n'+''.join(char+'\t'+code+'\n' for char,code in sorted(standard.items()))
        panel.atomic_write(current,contents)
        panel.atomic_write(current.with_suffix('.sha256'),hashlib.sha256(contents.encode('utf-8')).hexdigest())
        (APP/'settings-script.txt').write_text(str(APP/'scripts/Open-Settings.ps1')+'\n',encoding='utf-8')
        setreg(r'Software\Rime\Weasel','RimeUserDir',str(user))
        setreg(r'Software\Microsoft\Windows\CurrentVersion\Run','BihuaWeasel','schtasks.exe /Run /TN "BihuaInputMethod"')
        previous_global.write_text(json.dumps({'status':'installed','version':'0.6.29','directory':str(APP)},indent=2),encoding='utf-8')
        create_task()
        run([APP/'WeaselDeployer.exe','/deploy'])
        assert (user/'build/bihua_mvp.schema.yaml').exists(),'输入方案编译失败'
        helper('--activate')
        run(['schtasks.exe','/Run','/TN','BihuaInputMethod'],capture_output=True);time.sleep(1)
        wait_for_server()
        path=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\BihuaInput'
        for name,value in {'DisplayName':'笔画输入法','DisplayVersion':'0.6.29','Publisher':'笔画输入法项目','InstallLocation':str(APP),'UninstallString':'"'+str(APP/'Uninstall.exe')+'"'}.items():setreg(path,name,value)
        for name in ['NoModify','NoRepair']:setreg(path,name,1,winreg.REG_DWORD)
        start=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/笔画输入法';start.mkdir(parents=True,exist_ok=True)
        for name,target in [('笔画设置',APP/'BihuaSettingsLauncher.exe'),('卸载笔画输入法',APP/'Uninstall.exe')]:
            # WScript can fail to save an existing link held by the Start menu.
            # Generate a fresh link, then replace its bytes through the same
            # backup/rollback transaction as other installed user files.
            temporary=start/('bihua-'+uuid.uuid4().hex+'.lnk')
            try:
                powershell('$s=(New-Object -ComObject WScript.Shell).CreateShortcut('+psquote(temporary)+');$s.TargetPath='+psquote(target)+';$s.Save()')
                put(start/(name+'.lnk'),temporary.read_bytes())
            finally:temporary.unlink(missing_ok=True)
        record.update(status='installed',shortcuts=str(start));RECEIPT.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return {'result':'PASS','directory':str(APP),'user_data_preserved':True,'frontend_reload_policy':'reopen_existing_applications'}
    except BaseException:
        rollback(record)
        raise
def rollback(record):
    for item in reversed(record['files']):
        target=Path(item['path'])
        if item['backup']:shutil.copy2(item['backup'],target)
        else:target.unlink(missing_ok=True)
    for item in reversed(record['registry']):
        if reg_read(item['path'],item['name'])==item['installed']:reg_write(item['path'],item['name'],item['before'])
    backup=Path(record['backup']);global_file=HOME/'installation.json'
    if record['global_before']:shutil.copy2(backup/'installation.json',global_file)
    else:global_file.unlink(missing_ok=True)
    stop_owned_server(APP/'WeaselServer.exe')
    restore_task(record['task'],backup)
    # Restore the launch target before deployment can awaken an older frontend.
    try:run([APP/'WeaselDeployer.exe','/deploy'])
    except Exception as error:(backup/'restore-deployment-warning.txt').write_text(str(error),encoding='utf-8')
    try:
        old=record['profile'];flag='2' if old['own_enabled'] else '1' if old['stock_enabled'] else '0'
        helper('--restore-user',flag,old['default_class'],old['default_profile'])
    finally:
        if record['task']:subprocess.run(['schtasks','/Run','/TN','BihuaInputMethod'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
def uninstall():
    record=json.loads(RECEIPT.read_text(encoding='utf-8'))
    stop_owned_server(APP/'WeaselServer.exe')
    # Keep user changes made after installation. Personal dictionaries are never managed files.
    managed={item['path'] for item in record['files']}
    record['files']=[item for item in record['files'] if Path(item['path']).exists() and hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['installed_hash']]
    rollback(record)
    start=Path(record.get('shortcuts',''))
    if start.is_dir():
        for name in ['笔画设置.lnk','卸载笔画输入法.lnk']:
            if str(start/name) not in managed:(start/name).unlink(missing_ok=True)
        if not list(start.iterdir()):start.rmdir()
    record['status']='uninstalled';RECEIPT.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'result':'PASS','personal_data_preserved':True,'shared_tsf_component_retained':True}
def validate():
    count=verify()
    task_xml()  # Read-only Windows integration check, including a clean first-install state.
    user=APP/'.validation-user'
    run([APP/'python/python.exe','-B',APP/'scripts/release_probe.py',APP,user,APP/'runtime-validation.json'])
    run([APP/'python/python.exe','-B',APP/'scripts/mouse_probe.py',APP,APP/'.mouse-validation',APP/'mouse-validation.json'])
    run([APP/'python/python.exe','-B',APP/'scripts/carry_probe.py',APP,APP/'.carry-validation',APP/'carry-validation.json'],timeout=150)
    run([APP/'python/python.exe','-B',APP/'scripts/Native-Settings.py','--rime-dir',user,'--smoke',APP/'settings-validation.json'])
    assert json.loads((APP/'settings-validation.json').read_text(encoding='utf-8-sig'))['result']=='PASS'
    result={'result':'PASS','files_verified':count,'runtime':json.loads((APP/'runtime-validation.json').read_text(encoding='utf-8-sig')),'mouse':json.loads((APP/'mouse-validation.json').read_text(encoding='utf-8-sig')),'carry':json.loads((APP/'carry-validation.json').read_text(encoding='utf-8-sig')),'settings':True,'scheduler_query':True,'windows_registration_tested':False}
    (APP/'validation-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
if __name__=='__main__':
    try:
        action=sys.argv[1] if len(sys.argv)>1 else 'install'
        print(json.dumps({'install':install,'uninstall':uninstall,'validate':validate}[action](),ensure_ascii=False))
    except BaseException as error:
        (APP/'installation-error.log').write_text(str(error),encoding='utf-8');raise
