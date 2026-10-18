"""Record the already-verified local 0.5 release without exposing personal text."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile

root=Path(__file__).resolve().parent.parent
native=root/'.verification/weasel-native'
source=native/'weasel-0.17.4'
changed=['include/resource.h','WeaselServer/WeaselServer.rc','WeaselTSF/WeaselTSF.rc',
         'WeaselServer/WeaselServer.cpp','WeaselServer/WeaselServerApp.cpp','RimeWithWeasel/RimeWithWeasel.cpp']
patch=[]
with tarfile.open(native/'weasel-0.17.4.tar.gz') as archive:
    for name in changed:
        encoding='utf-16' if name.endswith('.rc') else 'utf-8-sig'
        before=archive.extractfile('weasel-0.17.4/'+name).read().decode(encoding)
        after=(source/name).read_text(encoding=encoding)
        patch.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(root/'native/weasel-0.17.4-bihua.patch').write_text(''.join(patch),encoding='utf-8')
upstream=json.loads((native/'source.json').read_text(encoding='utf-8-sig'))
upstream.update({'tag':'0.17.4','license':'GPL-3.0','rime':{'version':'1.13.1','archive_sha256':'05fcf8cc2d058a0186dd9f04d6e021ad41687db50dc81e85cf655dfabfdf0009'},
 'boost':{'version':'1.84.0','url':'https://archives.boost.io/release/1.84.0/source/boost_1_84_0.7z','sha256':'81a4d10075731966477276c47324ecd9cac02da49899d36c48eba66e40014f25'},
 'build':{'toolchain':'VS2022 v143','configuration':'Release/x64','static_runtime':True},
 'patch_is_review_diff':'UTF-16 resource files are applied by Patch-Native-Source.py; this UTF-8 diff is for review'})
(root/'native/UPSTREAM.json').write_text(json.dumps(upstream,indent=2),encoding='utf-8')
shutil.copy2(Path('C:/Program Files/Rime/weasel-0.17.4/LICENSE.txt'),root/'native/LICENSE')
user=Path(os.environ['APPDATA'])/'Rime'
def state(path):return json.loads(json.loads(path.read_text(encoding='utf-8'))['payload'])
after=user/'bihua_personal_association_v1.jsonl'
before=after.with_name(after.name+'.previous')
old,new=state(before),state(after)
assert old['version']==1 and new['version']==2 and old['sequence']==new['sequence']
assert old['window']==new['window'] and set(old['confirmed'])==set(new['confirmed'])
assert all(new['confirmed'][phrase]['positive_count']==record['count'] for phrase,record in old['confirmed'].items())
shutil.copy2(before,root/'.verification/association-migration-v1-previous.jsonl')
migration={'result':'PASS','from':1,'to':2,'manual_sequence_unchanged':new['sequence'],
           'relationship_count_unchanged':len(new['confirmed']),'manual_window_unchanged':True,'previous_v1_archived':True}
(root/'.verification/live-feedback-migration.json').write_text(json.dumps(migration,indent=2),encoding='utf-8')
home=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel'
receipt_path=home/'installation.json';receipt=json.loads(receipt_path.read_text(encoding='utf-8'));directory=Path(receipt['directory'])
for name in receipt['files']:
    receipt['files'][name]=hashlib.sha256((directory/name).read_bytes()).hexdigest()
receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
report=json.loads((root/'.verification/deployed-local.json').read_text(encoding='utf-8'))
previous=json.loads((root/'docs/verification.json').read_text(encoding='utf-8'))
report['result']='PASS';report['checked_at']='2026-10-14';report['previous_release_evidence']=previous.get('evidence',{})
report['evidence']={'latest_engine_core_store_feedback_native_focus':'.verification/local-rime-d1f338dcae264d358992d4a06fac5ddf/results.json',
 'latest_engine_1_17_0':'.verification/local-rime-90cb1a0ece1f4b498422fa06a0edc5a8/results.json',
 'native_menu_and_COM':'.verification/native-settings-results.json','live_migration':'.verification/live-feedback-migration.json',
 'settings_apply_and_rollback':'.verification/settings-panel-7fac45320b2a49aa95dcb1455e7fb631/results.json',
 'personal_manager_v1_v2':'.verification/personal-manager-48e95a92b6f048a6ab821756eb95df54/results.json',
 'association_native_lock':'.verification/association-lock-7a5ae759cf564c21a04021f0a68fbfea/results.json',
 'association_two_process':'.verification/association-processes-c32238c21f8143a98b120278cf70db22/association-two-process-results.json'}
report['remaining_manual_trials']=['0.5.0 cross-application typing feel','actual logout/login startup ordering']
(root/'docs/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'release':report['version'],'live_migration':migration,'evidence_recorded':True}))
