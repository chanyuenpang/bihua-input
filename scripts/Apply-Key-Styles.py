"""Update the real installed runtime and native settings from an external task."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

root, report=map(Path,sys.argv[1:])
directory=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.5.2'
user=Path(os.environ['APPDATA'])/'Rime'
spec=importlib.util.spec_from_file_location('install',directory/'scripts/Install-Independent.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
assert Path(install.physical(directory/'WeaselServer.exe'))==directory/'WeaselServer.exe'
assert Path(install.physical(user/'lua/bihua_query_keys.lua'))==user/'lua/bihua_query_keys.lua'
backup=directory/('key-style-backup-'+uuid.uuid4().hex);backup.mkdir()
files=[]
for name in ['Settings-Panel.py','Native-Settings.py','key_bindings.py','Open-Settings.ps1']:
    files.append((root/'scripts'/name,directory/'scripts'/name))
for name in ['index.html','app.js','style.css']:
    files.append((root/'settings'/name,directory/'settings'/name))
for name in ['bihua_learning_guard.lua','bihua_query_keys.lua']:
    files.append((root/'rime/lua'/name,user/'lua'/name))
for i,(source,target) in enumerate(files):
    if target.exists(): shutil.copy2(target,backup/(str(i)+'-'+target.name))
    shutil.copy2(source,target)
    assert source.read_bytes()==target.read_bytes()
# Run installed modules so its package paths/runtime dependencies are exercised.
sys.path.insert(0,str(directory/'scripts'))
spec=importlib.util.spec_from_file_location('panel',directory/'scripts/Settings-Panel.py')
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
service=panel.Settings(user)
settings=service.state()['settings']
service.apply(service.preview(settings)['preview_id'])
assert service.state()['settings']==settings
exe=str(directory/'WeaselServer.exe')
subprocess.run([exe,'/q'],check=True,timeout=10);time.sleep(.5)
backend=root/'.verification/weasel-native/weasel-0.17.4/output/WeaselServer.exe'
if backend.exists():
    shutil.copy2(directory/'WeaselServer.exe',backup/'WeaselServer.exe')
    try:
        for attempt in range(20):
            try:
                shutil.copy2(backend,directory/'WeaselServer.exe');break
            except PermissionError:
                if attempt==19: raise
                time.sleep(.2)
    except Exception:
        subprocess.run(['schtasks','/Run','/TN','BihuaInputMethod'],capture_output=True,timeout=10)
        raise
subprocess.run(['schtasks','/Run','/TN','BihuaInputMethod'],check=True,capture_output=True,timeout=10)
time.sleep(1)
subprocess.run([exe,'/bihua-engine-probe'],check=True,timeout=10)
smoke=report.with_name('installed-native-settings-smoke.json')
subprocess.run([str(directory/'python/python.exe'),str(directory/'scripts/Native-Settings.py'),'--smoke',str(smoke)],check=True,timeout=20)
assert json.loads(smoke.read_text())['result']=='PASS'
# Start the actual installed entry point, which now opens a native window.
subprocess.run([exe,'/bihua-settings'],check=True,capture_output=True,timeout=15)
report.write_text(json.dumps({'result':'PASS','installed_directory':str(directory),
  'settings':settings,'native_window_smoke':True,'launched_installed_entry':True,
  'configuration_compiled_readback':True,'fresh_windows_task_backend':True,'backup':str(backup)},indent=2),encoding='utf-8')
