"""Measure engine commit latency in a private copy; never type into live Rime."""
import ctypes as c
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics
import time
import uuid
import argparse

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('abi',ROOT/'scripts/Test-Rime.py')
abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)
p=argparse.ArgumentParser();p.add_argument('--without-save',action='store_true');p.add_argument('--candidate-store',action='store_true');a=p.parse_args()
source=Path(os.environ['APPDATA'])/'Rime'
user=ROOT/'.verification'/('commit-latency-'+uuid.uuid4().hex)
user.mkdir()
for name in ('build','lua','opencc'):
    if (source/name).exists():shutil.copytree(source/name,user/name)
for file in source.iterdir():
    if file.is_file():shutil.copy2(file,user/file.name)
if a.candidate_store:
    shutil.copy2(ROOT/'rime/lua/bihua_association_store.lua',user/'lua/bihua_association_store.lua')
if a.without_save:
    file=user/'lua/bihua_association_store.lua'
    text=file.read_text(encoding='utf-8').replace('function M.save(owner)','function M.save(owner)\n  if true then return true end')
    file.write_text(text,encoding='utf-8')
home=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.5.1'
dll=c.CDLL(str(home/'rime.dll'))
def bind(name,result,*args):
    f=getattr(dll,name);f.restype=result;f.argtypes=args;return f
setup=bind('RimeSetup',None,c.POINTER(abi.Traits))
initialize=bind('RimeInitialize',None,c.POINTER(abi.Traits))
finalize=bind('RimeFinalize',None)
create=bind('RimeCreateSession',c.c_size_t)
select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
process=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
clear=bind('RimeClearComposition',None,c.c_size_t)
destroy=bind('RimeDestroySession',c.c_int,c.c_size_t)
commit=bind('RimeGetCommit',c.c_int,c.c_size_t,c.POINTER(abi.Commit))
free=bind('RimeFreeCommit',c.c_int,c.POINTER(abi.Commit))
traits=abi.initialized(abi.Traits)
traits.shared_data_dir=str(home/'data').encode()
traits.user_data_dir=str(user).encode()
traits.app_name=b'rime.commit_benchmark';traits.min_log_level=2;traits.log_dir=b''
setup(c.byref(traits));initialize(c.byref(traits))
session=create();assert session and select(session,b'bihua_mvp')
timings={'stroke':[],'confirm':[]}
try:
    for index in range(25):
        clear(session)
        start=time.perf_counter();process(session,ord('h'),0)
        timings['stroke'].append((time.perf_counter()-start)*1000)
        start=time.perf_counter();assert process(session,32,0)
        timings['confirm'].append((time.perf_counter()-start)*1000)
        out=abi.initialized(abi.Commit);assert commit(session,c.byref(out));free(c.byref(out))
finally:
    destroy(session);finalize()
result={'without_save':a.without_save,'candidate_store':a.candidate_store,'samples':25,'private_dir':str(user),
        'ms':{name:{'median':round(statistics.median(rows),2),'max':round(max(rows),2)} for name,rows in timings.items()}}
(user/'timings.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
