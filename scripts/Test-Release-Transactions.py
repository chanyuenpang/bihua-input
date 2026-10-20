"""Exercise installer transactions with sandbox files and simulated Windows integration."""
from pathlib import Path
import importlib.util
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('installer',ROOT/'packaging/Install-Release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def scenario(base,preserve=False,fail=False,empty=False,no_task=False,fail_shortcut=False,legacy_role='local_research'):
    home=base/'local/BihuaWeasel';app=home/'0.6.30';user=base/'roaming/Rime'
    app.mkdir(parents=True);user.mkdir(parents=True)
    (app/'scripts').mkdir()
    for name in ['Settings-Panel.py','Manage-Personal.py','personal_data.py','personal_strokes.py','key_bindings.py','appearance.py']:
        shutil.copy2(ROOT/'scripts'/name,app/'scripts'/name)
    (app/'profile/lua').mkdir(parents=True)
    new_codes='---\nname: bihua_local\n...\n一\th\t1\n'
    local_codes=b'---\nname: bihua_local\n...\n'+ '一\tn\t1\n'.encode('utf-8')
    files={'bihua_mvp.schema.yaml':'schema: new\n','bihua_local.dict.yaml':new_codes,
           'bihua_local.manifest.json':json.dumps({'source_role':'user_provided','generated_files':{'bihua_local.dict.yaml':hashlib.sha256(new_codes.encode()).hexdigest()}}), 'lua/bihua_local_data.lua':'new data',
           'lua/bihua_matcher.lua':'new runtime', 'default.custom.yaml':'patch:\n  schema_list:\n    - schema: bihua_mvp\n', 'weasel.custom.yaml':'patch: {}\n'}
    for name,text in files.items():(app/'profile'/name).write_bytes(text.encode('utf-8'))
    original={'personal.json':b'personal history','custom.yaml':b'my keys',
              'bihua_personal_phrases.tsv':b'personal phrases','bihua_personal_strokes.tsv':b'personal strokes',
              'bihua_personal_association_v1.jsonl':b'personal learned history',
              'bihua_mvp.custom.yaml':b'patch:\n  bihua_keys/letter_style: custom\n',
              'default.custom.yaml':b'patch:\n  menu/page_size: 5\n  schema_list: [{schema: old}]\n'}
    if empty:original.pop('default.custom.yaml')
    if preserve:original.update({'bihua_local.manifest.json':json.dumps({'source_role':legacy_role,'generated_files':{'bihua_local.dict.yaml':hashlib.sha256(local_codes).hexdigest()}}).encode(),
                                 'bihua_local.dict.yaml':local_codes,'lua/bihua_local_data.lua':b'local data'})
    for name,data in original.items():
        (user/name).parent.mkdir(parents=True,exist_ok=True);(user/name).write_bytes(data)
    global_file=home/'installation.json';global_file.write_text('{"directory":"previous"}')
    previous_server=home/'0.5.2/WeaselServer.exe';previous_server.parent.mkdir();previous_server.write_text('old backend')
    old_task='<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Actions><Exec><Command>'+str(previous_server)+'</Command></Exec></Actions></Task>'
    if no_task:old_task=''
    before=global_file.read_bytes();registry={};task=[old_task];calls=[];commands=[]
    shortcuts=base/'roaming/Microsoft/Windows/Start Menu/Programs/笔画输入法'
    shortcuts.mkdir(parents=True)
    old_shortcut=shortcuts/'笔画设置.lnk';old_shortcut.write_bytes(b'previous owned shortcut')
    shortcut_count=0
    def powershell(script):
        nonlocal shortcut_count
        match=re.search(r"CreateShortcut\('((?:''|[^'])*)'\)",script)
        if match:
            shortcut_count+=1
            if fail_shortcut and shortcut_count==2:raise RuntimeError('simulated shortcut failure')
            Path(match[1].replace("''","'")).write_bytes(b'new owned shortcut')
        return ''
    def read(path,name):return registry.get((path,name))
    def write(path,name,item):
        if item is None:registry.pop((path,name),None)
        else:registry[path,name]=item
    def run(args,**kw):
        commands.append(list(map(str,args)))
        if str(args[0]).endswith('WeaselDeployer.exe'):
            if fail:raise RuntimeError('simulated deployment failure')
            assert task[0]=='new task enabled','New launch target must be registered before deployment can wake TSF'
            (user/'build').mkdir(exist_ok=True);(user/'build/bihua_mvp.schema.yaml').write_text('engine:\n  filters: [simplifier, uniquifier]\n')
        return None
    def helper(mode,*args):
        calls.append(mode)
        return {'own_enabled':False,'stock_enabled':True,'default_class':'{class}','default_profile':'{profile}'}
    with patch.multiple(m,APP=app,HOME=home,RECEIPT=app/'user-install.json',verify=lambda:1,
                         physical_install_directory=lambda:None,machine_profile=lambda:None,
                         reg_read=read,reg_write=write,task_xml=lambda:task[0],
                         create_task=lambda enabled=True:task.__setitem__(0,'new task enabled' if enabled else 'new task disabled'),
                         stop_owned_server=lambda executable=None:commands.append([str(executable or previous_server),'/q']),
                         server_info=lambda:{'pid':1,'path':app/'WeaselServer.exe','window':1},
                         restore_task=lambda xml,backup:task.__setitem__(0,xml),
                         powershell=powershell,helper=helper,run=run), \
         patch.dict(os.environ,{'APPDATA':str(base/'roaming')}), \
         patch.object(m.time,'sleep',lambda value:None),patch.object(m.subprocess,'run',lambda *a,**kw:None):
        if fail or fail_shortcut:
            try:m.install();raise AssertionError('failure was swallowed')
            except RuntimeError as e:assert 'simulated' in str(e)
            assert global_file.read_bytes()==before and task[0]==old_task and not registry
            for name,data in original.items():assert (user/name).read_bytes()==data,name
            assert old_shortcut.read_bytes()==b'previous owned shortcut'
            assert not list(shortcuts.glob('bihua-*.lnk'))
        else:
            assert m.install()['result']=='PASS'
            projection=app/'data/current-canonical_strokes.tsv'
            assert '一\t1\n' in projection.read_text(encoding='utf-8')
            assert hashlib.sha256(projection.read_bytes()).hexdigest()==projection.with_suffix('.sha256').read_text()
            assert commands[0]==[str(previous_server),'/q'],'Shutdown must identify the actual owned process, even when the task is stale or missing'
            if not empty:assert 'menu/page_size: 5' in (user/'default.custom.yaml').read_text()
            assert m.install()['already_installed']
            assert (user/'bihua_local.dict.yaml').read_bytes()==new_codes.encode()
            assert (user/'lua/bihua_local_data.lua').read_bytes()==b'new data'
            for name in ['bihua_personal_phrases.tsv','bihua_personal_strokes.tsv','bihua_personal_association_v1.jsonl']:
                assert (user/name).read_bytes()==original[name],name
            assert 'bihua_keys/letter_style: custom' in (user/'bihua_mvp.custom.yaml').read_text()
            (user/'lua/bihua_matcher.lua').write_text('user changed runtime')
            assert m.uninstall()['result']=='PASS'
            assert (user/'lua/bihua_matcher.lua').read_text()=='user changed runtime'
            assert global_file.read_bytes()==before and task[0]==old_task and not registry
            for name,data in original.items():assert (user/name).read_bytes()==data,name
            assert '--restore-user' in calls
            assert old_shortcut.read_bytes()==b'previous owned shortcut'
            assert not list(shortcuts.glob('bihua-*.lnk'))
            if empty:assert not (user/'default.custom.yaml').exists()

with tempfile.TemporaryDirectory(prefix='bihua-installer-test-',dir=ROOT/'.verification') as tmp:
    for name,preserve,fail in [('fresh',False,False),('upgrade',True,False),('rollback',True,True)]:
        scenario(Path(tmp)/name,preserve,fail)
    scenario(Path(tmp)/'empty',empty=True)
    scenario(Path(tmp)/'no-task',empty=True,no_task=True)
    scenario(Path(tmp)/'shortcut-rollback',preserve=True,fail_shortcut=True)
    scenario(Path(tmp)/'old-public-profile',preserve=True,legacy_role='redistributable')
result={'result':'PASS','fresh_install_transaction':True,'upgrade_unifies_provided_profile':True,'old_public_profile_migrated':True,'personal_files_and_custom_settings_preserved':True,
        'deployment_failure_rollback':True,'shortcut_failure_rollback':True,'shortcut_upgrade_restored_on_uninstall':True,'uninstall_preserves_user_changes':True,'old_backend_quit_uses_owned_path':True,'windows_integration':'simulated'}
(ROOT/'.verification/release-transaction-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
