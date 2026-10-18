"""Install the separately identified frontend from a normal Windows process."""
import ctypes as c
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import winreg

root=Path(sys.argv[1]);output=Path(sys.argv[2]);directory=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.5.2'
spec=importlib.util.spec_from_file_location('native_install',directory/'scripts/Install-Independent.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
if Path(install.physical(directory/'WeaselServer.exe'))!=directory/'WeaselServer.exe':raise RuntimeError('Profile installer is in a redirected view')
identity=json.loads((root/'native/bihua-profile-identity.json').read_text())
source=root/'.verification/weasel-native/package'
shutil.copy2(source/'BihuaProfileSetup.exe',directory/'BihuaProfileSetup.exe')
shutil.copy2(root/'native/bihua-profile-identity.json',directory/'bihua-profile-identity.json')
frontend=Path(os.environ['ProgramFiles'])/'BihuaInputMethod/0.5.3'
assert (frontend/'bihua64.dll').exists() and (frontend/'bihua32.dll').exists()
entries=[]
proof=directory/'independent-profile-result.json'
result=subprocess.run([str(directory/'BihuaProfileSetup.exe'),'--activate',str(frontend),str(proof)],timeout=20)
status=json.loads(proof.read_text())
receipt_path=directory.parent/'installation.json'
receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
if result.returncode:
    # Global registration is installer-owned; a failed user activation does not
    # remove machine-wide profiles or touch the user's existing input method.
    status.update(result='FAIL',old_profile_preserved=True)
    output.write_text(json.dumps(status,indent=2),encoding='utf-8')
    sys.exit(result.returncode)
receipt['independent_profile']=identity
if 'stock_enabled_before' not in receipt:
    receipt['stock_enabled_before']=status['stock_enabled_before']
receipt['frontend_directory']=str(frontend)
receipt['registry'].extend(entries)
receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
status.update(result='PASS',directory=str(directory),identity=identity)
output.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
