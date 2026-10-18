"""Preview/restore this local repair installation; leave all personal data intact."""
import argparse
import json
from pathlib import Path
import subprocess
import shutil
import importlib.util
spec=importlib.util.spec_from_file_location('independent_install',Path(__file__).with_name('Install-Independent.py'))
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
physical,value,write=install.physical,install.value,install.write

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');a=parser.parse_args()
    directory=Path(__file__).resolve().parent.parent
    path=directory.parent/'installation.json'
    if Path(physical(path))!=path:raise RuntimeError('Run recovery outside packaged development apps')
    state=json.loads(path.read_text(encoding='utf-8-sig'))
    if state['version']!='0.5.2' or Path(state['directory'])!=directory:raise RuntimeError('Receipt does not own this package')
    for entry in state['registry']:
        current=value(entry['path'],entry['name'],entry['view'])
        if current not in (entry['installed'],entry['before']):raise RuntimeError('External registry change; recovery stopped without writes')
    if not a.apply:print('Restore recorded registration and previous configuration; preserve personal data and package.');return
    if state.get('independent_profile'):
        profile_report=directory/'user-profile-restore.json'
        subprocess.run([str(directory/'BihuaProfileSetup.exe'),'--restore-user',state['frontend_directory'],str(profile_report),
                        '1' if state.get('stock_enabled_before') else '0'],check=True,timeout=15)
    subprocess.run([str(directory/'WeaselServer.exe'),'/q'],check=True,timeout=10)
    # Only remove the task when its action still points to this exact package.
    import xml.etree.ElementTree as ET
    task=state.get('scheduled_task')
    if task:
        query=subprocess.run(['schtasks','/Query','/TN',task,'/XML'],capture_output=True,timeout=10)
        if query.returncode==0:
            command=ET.fromstring(query.stdout).find('.//{http://schemas.microsoft.com/windows/2004/02/mit/task}Command')
            if command is None or Path(command.text)!=directory/'WeaselServer.exe':raise RuntimeError('Startup task changed externally; recovery stopped')
            subprocess.run(['schtasks','/Delete','/TN',task,'/F'],check=True,timeout=10)
    for entry in reversed(state['registry']):write(entry,entry['before'])
    backup=Path(state['backup']);user=Path(next(e['installed']['data'] for e in state['registry'] if e['name']=='RimeUserDir'))
    for previous in backup.iterdir():
        if previous.name.startswith('bihua_personal'):continue
        target=user/previous.name
        if previous.is_dir():shutil.copytree(previous,target,dirs_exist_ok=True)
        else:shutil.copy2(previous,target)
    state['status']='restored';path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    subprocess.Popen([str(Path(state['stock_directory'])/'WeaselServer.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
    print('Original registration restored; personal data and recovery files retained.')

if __name__=='__main__':main()
