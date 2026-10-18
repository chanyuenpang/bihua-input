"""Update only the installed settings window, outside MSIX redirection."""
import ctypes as c
from ctypes import wintypes as w
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

root,report=map(Path,sys.argv[1:3])
remove_fuzzy='--remove-fuzzy' in sys.argv[3:]
directory=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.5.2'
spec=importlib.util.spec_from_file_location('install',directory/'scripts/Install-Independent.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
target=directory/'scripts/Native-Settings.py'
assert Path(install.physical(target))==target, 'Refuse redirected deployment'
backup=directory/('hdpi-settings-backup-'+uuid.uuid4().hex);backup.mkdir()
for name in ('Native-Settings.py','Settings-Panel.py'):
    shutil.copy2(directory/'scripts'/name,backup/name)
    shutil.copy2(root/'scripts'/name,directory/'scripts'/name)
if remove_fuzzy:
    user=Path(os.environ['APPDATA'])/'Rime'
    shutil.copy2(user/'lua/bihua_matcher.lua',backup/'bihua_matcher.lua')
    shutil.copy2(root/'rime/lua/bihua_matcher.lua',user/'lua/bihua_matcher.lua')
    for name in ('index.html','app.js','style.css'):
        shutil.copy2(directory/'settings'/name,backup/name)
        shutil.copy2(root/'settings'/name,directory/'settings'/name)
    import yaml
    base=user/'bihua_mvp.schema.yaml'
    shutil.copy2(base,backup/base.name)
    config=yaml.safe_load(base.read_text(encoding='utf-8-sig'))
    for key in ('fuzzy_enabled','learning_enabled'): config.get('bihua_matcher',{}).pop(key,None)
    config['translator'].pop('user_dict',None)
    config['translator']['enable_user_dict']=False
    base.write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False),encoding='utf-8')
sys.path.insert(0,str(directory/'scripts'))
spec=importlib.util.spec_from_file_location('settings',directory/'scripts/Settings-Panel.py')
settings=importlib.util.module_from_spec(spec);spec.loader.exec_module(settings)
service=settings.Settings(Path(os.environ['APPDATA'])/'Rime')
original=service.state()['settings']
trial=dict(original,keypad_style='789456',keypad_keys=settings.KEYPAD['789456'].copy())
try:
    service.apply(service.preview(trial)['preview_id'])
    assert service.state()['settings']['keypad_style']=='789456'
    raw=settings.get(service.compiled(),'bihua_keys/keypad_style')
finally:
    service.apply(service.preview(original)['preview_id'])
assert service.state()['settings']==original
if remove_fuzzy:
    assert 'fuzzy' not in original
    assert settings.get(service.compiled(),'bihua_matcher/fuzzy_enabled') is None
    exe=str(directory/'WeaselServer.exe')
    subprocess.run([exe,'/q'],check=True,timeout=10);time.sleep(.5)
    subprocess.run(['schtasks','/Run','/TN','BihuaInputMethod'],check=True,capture_output=True,timeout=10)
    time.sleep(1)
    subprocess.run([exe,'/bihua-engine-probe'],check=True,timeout=10)
smoke=report.with_name('installed-hdpi-settings-smoke.json')
subprocess.run([str(directory/'python/python.exe'),str(target),'--smoke',str(smoke)],check=True,timeout=20)
assert json.loads(smoke.read_text())['result']=='PASS'
u=c.WinDLL('user32');u.FindWindowW.argtypes=[w.LPCWSTR,w.LPCWSTR];u.FindWindowW.restype=w.HWND
u.ShowWindow.argtypes=[w.HWND,c.c_int];u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
u.SetWindowTextW.argtypes=[w.HWND,w.LPCWSTR];u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,c.c_int]
callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
u.EnumChildWindows.argtypes=[w.HWND,callback,w.LPARAM]
preserved=False
for old_class in ('BihuaNativeSettings','BihuaNativeSettingsV2','BihuaNativeSettingsV3'):
    old=u.FindWindowW(old_class,None)
    if not old: continue
    clean=[]
    def inspect(handle,_):
        text=c.create_unicode_buffer(1024);u.GetWindowTextW(handle,text,len(text))
        if text.value.startswith('已读取当前设置'): clean.append(True)
        return True
    visitor=callback(inspect);u.EnumChildWindows(old,visitor,0)
    if clean: u.PostMessageW(old,0x10,0,0)
    else:
        preserved=True;u.SetWindowTextW(old,'旧版笔画设置（未保存内容已保留）');u.ShowWindow(old,6)
subprocess.run([str(directory/'WeaselServer.exe'),'/bihua-settings'],check=True,timeout=15)
for _ in range(40):
    if u.FindWindowW('BihuaNativeSettingsV4',None): break
    time.sleep(.1)
else: raise RuntimeError('Updated native settings window did not open')
report.write_text(json.dumps({'result':'PASS','installed_script':str(target),'fuzzy_removed':remove_fuzzy,'unicode_readback_and_capture_tests':True,'actual_789456_save':True,'compiled_style_type':type(raw).__name__,'original_settings_restored':True,
    'new_window_open':True,'old_unsaved_window_preserved':preserved,'backup':str(backup)},indent=2),encoding='utf-8')
