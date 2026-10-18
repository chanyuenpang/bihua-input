"""Apply the punctuation fix outside the development app's redirected view."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

root, report = map(Path, sys.argv[1:])
directory = Path(os.environ['LOCALAPPDATA']) / 'BihuaWeasel/0.5.2'
user = Path(os.environ['APPDATA']) / 'Rime'
spec = importlib.util.spec_from_file_location('install', directory / 'scripts/Install-Independent.py')
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)
target = user / 'lua/bihua_learning_guard.lua'
assert Path(install.physical(target)) == target, 'Refuse redirected deployment'
backup = directory / ('question-patch-backup-' + uuid.uuid4().hex + '.lua')
shutil.copy2(target, backup)
shutil.copy2(root / 'rime/lua/bihua_learning_guard.lua', target)
assert target.read_bytes() == (root / 'rime/lua/bihua_learning_guard.lua').read_bytes()
exe = str(directory / 'WeaselServer.exe')
subprocess.run([exe, '/q'], check=True, timeout=10)
time.sleep(.5)
subprocess.run(['schtasks', '/Run', '/TN', 'BihuaInputMethod'], check=True, capture_output=True, timeout=10)
time.sleep(1)
subprocess.run([exe, '/bihua-engine-probe'], check=True, timeout=10)
report.write_text(json.dumps({'result': 'PASS', 'physical_target': str(target),
                             'backup': str(backup), 'fresh_windows_task_backend': True}, indent=2), encoding='utf-8')
