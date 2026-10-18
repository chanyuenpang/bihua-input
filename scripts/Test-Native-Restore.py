"""Private HKCU fixture verifies all-or-nothing restore preflight and own-key cleanup."""
import importlib.util
from pathlib import Path
import uuid
import winreg
spec=importlib.util.spec_from_file_location('native_install',Path(__file__).with_name('Install-Native-Settings.py'))
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
path='Software\\BihuaNativeTest\\'+uuid.uuid4().hex
entries=[{'path':path,'name':name,'view':0,'created_key':True,'before':None,'installed':{'data':'installed','type':winreg.REG_SZ}} for name in ('first','last')]
try:
    for entry in entries:native.write(path,entry['name'],0,entry['installed'])
    native.write(path,'last',0,{'data':'external','type':winreg.REG_SZ})
    try:
        native.restore_registry(entries)
        raise AssertionError('Restore accepted an external conflict')
    except RuntimeError:pass
    assert native.value(path,'first',0)==entries[0]['installed'],'Restore changed first value before detecting last conflict'
    native.write(path,'last',0,entries[1]['installed'])
    native.restore_registry(entries)
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER,path)
        raise AssertionError('Owned empty key survived restore')
    except FileNotFoundError:pass
    print('PASS: restore conflict causes no partial changes; only owned empty fixture key removed')
finally:
    try:winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
    except FileNotFoundError:pass
