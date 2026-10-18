"""Real Windows scheduler checks; only create/delete our unique temporary task."""
from pathlib import Path
import importlib.util
import json
import re
import tempfile
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('installer',ROOT/'packaging/Install-Release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original_powershell=m.powershell
name='BihuaInstallerTest_'+uuid.uuid4().hex
assert re.fullmatch(r'BihuaInstallerTest_[0-9a-f]{32}',name)

def scoped_powershell(script):
    return original_powershell(script.replace('BihuaInputMethod',name))

with tempfile.TemporaryDirectory(prefix='installer-scheduler-',dir=ROOT/'.verification') as tmp:
    home=Path(tmp).resolve();app=home/'runtime';app.mkdir()
    (app/'WeaselServer.exe').write_text('test placeholder; never executed')
    try:
        with patch.multiple(m,HOME=home,APP=app,powershell=scoped_powershell):
            assert m.task_xml()=='','Missing task must be a successful empty result'
            m.create_task()
            text=m.task_xml();assert 'WeaselServer.exe' in text and name in text
            with patch.object(m,'HOME',home/'unrelated'):
                try:m.task_xml();raise AssertionError('unrelated task must be rejected')
                except ValueError as error:assert '不属于' in str(error)
            # A real PowerShell failure must retain a readable diagnostic.
            try:original_powershell("throw 'bihua-scheduler-diagnostic-test'");raise AssertionError('failure was hidden')
            except RuntimeError as error:assert 'bihua-scheduler-diagnostic-test' in str(error)
    finally:
        # Guard the exact unique task and its action before deleting it.
        original_powershell("$s=New-Object -ComObject Schedule.Service;$s.Connect();$f=$s.GetFolder('\\');"+
            "$t=$null;try{$t=$f.GetTask("+m.psquote(name)+")}catch{if($_.Exception.HResult -ne -2147024894){throw}};"+
            "if($t){if($t.Definition.Actions.Item(1).Path -ne "+m.psquote(app/'WeaselServer.exe')+"){throw 'Test task identity mismatch'};$f.DeleteTask("+m.psquote(name)+",0)};exit 0")
result={'result':'PASS','real_windows':True,'missing_task':True,'create_and_read_task':True,
        'foreign_task_rejected':True,'powershell_error_diagnostic':True,'production_task_changed':False}
(ROOT/'.verification/installer-scheduler-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
