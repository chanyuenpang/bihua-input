"""Compile and exercise a release profile in an isolated directory."""
import ctypes as c
import json
from pathlib import Path
import shutil
import sys
import time
import rime_abi as abi

def probe(runtime,user):
    runtime=Path(runtime).resolve();user=Path(user).resolve();user.mkdir(parents=True,exist_ok=True)
    for source in (runtime/'profile').iterdir():
        target=user/source.name
        if source.is_dir(): shutil.copytree(source,target,dirs_exist_ok=True)
        else: shutil.copy2(source,target)
    dll=c.CDLL(str(runtime/'rime.dll'))
    def bind(name,result,*args):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(args);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));initialize=bind('RimeInitialize',None,c.POINTER(abi.Traits))
    finalize=bind('RimeFinalize',None);maintain=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    create=bind('RimeCreateSession',c.c_size_t);destroy=bind('RimeDestroySession',c.c_int,c.c_size_t)
    select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
    process=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    get_context=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));free_context=bind('RimeFreeContext',c.c_int,c.POINTER(abi.Context))
    clear=bind('RimeClearComposition',None,c.c_size_t)
    get_commit=bind('RimeGetCommit',c.c_int,c.c_size_t,c.POINTER(abi.Commit));free_commit=bind('RimeFreeCommit',c.c_int,c.POINTER(abi.Commit))
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(runtime/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.bihua_release_probe';traits.min_log_level=2;traits.log_dir=b''
    setup(c.byref(traits));initialize(c.byref(traits));session=0
    try:
        maintain(1);join();session=create();assert session and select(session,b'bihua_mvp')
        def key(value,mask=0): return process(session,ord(value) if isinstance(value,str) else value,mask)
        def state():
            value=abi.initialized(abi.Context);assert get_context(session,c.byref(value))
            try:return {'preedit':abi.text(value.composition.preedit),'page':value.menu.page_no,'candidates':[abi.text(value.menu.candidates[i].text) for i in range(value.menu.num_candidates)]}
            finally:free_context(c.byref(value))
        def committed():
            value=abi.initialized(abi.Commit)
            if not get_commit(session,c.byref(value)):return ''
            try:return abi.text(value.text)
            finally:free_commit(c.byref(value))
        def query(code):
            clear(session);committed()
            for char in code:key(char)
            return state()
        profile=json.loads((runtime/'profile/bihua_local.manifest.json').read_text(encoding='utf-8-sig'))
        assert profile['source_role']=='user_provided' and profile['profile_id']=='wetype-android-4.0.0-provided-v1','Wrong product-data source'
        assert query('hshsz')['candidates']==list('提喜担吉博损扣抽操'),'Product ranking differs from the supplied reference'
        for char,code in [('天','hhpd'),('中','szhs'),('国','szhhshnh')]:
            rows=query(code)['candidates'];assert char in rows,(char,rows)
            key(str(rows.index(char)+1));assert committed()==char
        rows=query('hhpd')['candidates'];key(str(rows.index('天')+1));assert committed()=='天'
        assert state()['candidates'],'a real public-data continuation is required'
        key('h');assert '一' in state()['candidates'],'the normal horizontal-stroke first candidate must remain visible'
        query('h');key(0xffab);assert state()['page']==1
        key(0xffae);chosen=state()['candidates'][1];key(0xffb2);assert committed()==chosen
        key(0xffae,1<<30)
        query('h');key(0xffb0);assert committed() and state()['candidates']
        key(0xff0d);assert committed() and not state()['candidates']
        rows=query('szfsz')['candidates'];assert '中国' in rows,rows
        rows=query('htpd');assert '天' in rows['candidates'] and '？' in rows['preedit'],rows
        clear(session);key('?',1);assert committed()=='？'
        return {'result':'PASS','provided_mobile_profile':profile['profile_id'],'ji_rank_for_12125':4,'strokes':True,'simplified':True,'phrase_prefix':True,'wildcard':True,'local_predictions':True,'ordinary_first_candidate_with_carry':True,'keypad_zero':True,'keypad_dot_selection':True,'keypad_paging':True,'enter_closes':True,'question_punctuation':True}
    finally:
        if session:destroy(session)
        finalize()

if __name__=='__main__':
    result=probe(sys.argv[1],sys.argv[2]);Path(sys.argv[3]).write_text(json.dumps(result,indent=2),encoding='utf-8')
