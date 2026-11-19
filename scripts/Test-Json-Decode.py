"""Check escaped snapshot correctness and latency inside the shipped Rime Lua VM."""
from pathlib import Path
import argparse
import ctypes as c
import importlib.util
import json
import shutil
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--packaged',action='store_true',help='Test the shipped parser without replacing it from source')
    args=parser.parse_args()
    runtime=args.runtime.resolve()
    user=ROOT/'.verification'/('json-decode-'+uuid.uuid4().hex)
    shutil.copytree(runtime/'profile',user)
    sources=[ROOT/'tests/lua/json_decode_spec.lua']
    if not args.packaged:sources.append(ROOT/'rime/lua/bihua_json.lua')
    for source in sources:
        shutil.copy2(source,user/'lua'/source.name)
    (user/'lua/bihua_matcher.lua').write_text('''local M={}
function M.init(env)
  local ok,result=pcall(require('json_decode_spec').run)
  env.engine.context:set_property('json_decode_result',(ok and '' or 'FAIL: ')..tostring(result))
end
function M.func() end
return M
''',encoding='utf-8')
    spec=importlib.util.spec_from_file_location('abi',ROOT/'packaging/rime_abi.py')
    abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)
    dll=c.CDLL(str(runtime/'rime.dll'))
    def bind(name,result,*types):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(types);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits))
    finish=bind('RimeFinalize',None);maintain=bind('RimeStartMaintenance',c.c_int,c.c_int)
    join=bind('RimeJoinMaintenanceThread',None);create=bind('RimeCreateSession',c.c_size_t)
    select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
    prop=bind('RimeGetProperty',c.c_int,c.c_size_t,c.c_char_p,c.c_char_p,c.c_size_t)
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(runtime/'data').encode()
    traits.user_data_dir=str(user).encode();traits.app_name=b'rime.json_decode_test'
    traits.min_log_level=2;traits.log_dir=str(user).encode()
    setup(c.byref(traits));init(c.byref(traits))
    try:
        maintain(1);join();started=time.perf_counter();session=create()
        assert session and select(session,b'bihua_mvp')
        result=c.create_string_buffer(4096)
        assert prop(session,b'json_decode_result',result,len(result))
        message=result.value.decode('utf-8')
        print(message,flush=True)
        assert message.startswith('PASS:'),message
        proof={'result':'PASS','real_rime':str(runtime/'rime.dll'),'message':message,
               'test_ms':round((time.perf_counter()-started)*1000,2),'production_data_changed':False}
        (ROOT/'.verification/json-decode-result.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    finally:finish()

if __name__=='__main__':main()
