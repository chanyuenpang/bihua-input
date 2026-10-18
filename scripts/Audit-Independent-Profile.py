"""External final audit of the separate frontend and shipped Return behavior."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

root=Path(sys.argv[1]);output=Path(sys.argv[2])
directory=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.5.2'
frontend=Path(os.environ['ProgramFiles'])/'BihuaInputMethod/0.5.3'
shutil.copy2(root/'.verification/weasel-native/package/BihuaProfileSetup.exe',directory/'BihuaProfileSetup.exe')
shutil.copy2(root/'scripts/Restore-Independent.py',directory/'scripts/Restore-Independent.py')
proof=directory/'independent-profile-audit.json'
assert subprocess.run([str(directory/'BihuaProfileSetup.exe'),'--inspect',str(frontend),str(proof)],timeout=15).returncode==0
profile=json.loads(proof.read_text())
output.with_name('independent-profile-state.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
assert profile['own_enabled'] and profile['own_default'] and not profile['stock_enabled']
spec=importlib.util.spec_from_file_location('menus',root/'scripts/Patch-Native-Menus.py')
menus=importlib.util.module_from_spec(spec);spec.loader.exec_module(menus)
for name in ['bihua64.dll','bihua32.dll']:
    rows=menus.menus(frontend/name)
    assert len(rows)==3 and all(menus.menu_items(data)==[(40018,'笔画输入法'),(40017,'笔画设置')] for _,_,data in rows)
user=Path(os.environ['APPDATA'])/'Rime'
for name in ['bihua_learning_guard.lua','bihua_association_runtime.lua']:
    assert (user/'lua'/name).read_bytes()==(root/'rime/lua'/name).read_bytes()
# Start a fresh backend from its Windows task so no old Lua module cache survives.
assert subprocess.run([str(directory/'WeaselServer.exe'),'/q'],timeout=10).returncode==0
time.sleep(.25)
assert subprocess.run(['schtasks','/Run','/TN','BihuaInputMethod'],capture_output=True,timeout=10).returncode==0
time.sleep(.7)
assert subprocess.run([str(directory/'WeaselServer.exe'),'/bihua-engine-probe'],timeout=10).returncode==0
restore=subprocess.run([str(directory/'python/python.exe'),str(directory/'scripts/Restore-Independent.py')],capture_output=True,text=True,encoding='utf-8',timeout=10)
assert restore.returncode==0,restore.stderr
result={'result':'PASS','profile':profile,'frontend':str(frontend),'menu_resources':6,
        'return_runtime_files_match':True,'fresh_backend_from_windows_task':True,'restore_preview':True,
        'actual_system_reboot_tested':False,'fresh_machine_tested':False}
output.write_text(json.dumps(result,indent=2),encoding='utf-8')
