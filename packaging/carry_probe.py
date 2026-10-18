"""Real-Rime tests of continuation pinning, with isolated deterministic fixtures."""
import ctypes as c
import json
from pathlib import Path
import shutil
import subprocess
import sys
import rime_abi as abi
import yaml


def branch(runtime,user,page_size,device):
    runtime=Path(runtime);user=Path(user);user.mkdir(parents=True)
    shutil.copytree(runtime/'profile',user,dirs_exist_ok=True)
    schema=yaml.safe_load((user/'bihua_mvp.schema.yaml').read_text(encoding='utf-8-sig'))
    schema['menu']['page_size']=page_size
    schema['bihua_matcher'].update(personal_association=True,static_association=True,phrase_enabled=False)
    schema['engine']['filters']=['simplifier','uniquifier','lua_filter@*bihua_association_filter']
    (user/'bihua_mvp.schema.yaml').write_text(yaml.safe_dump(schema,allow_unicode=True),encoding='utf-8')
    # Deliberately artificial stroke tables isolate rank from stroke matching.
    # In particular, a survivor moves beyond the ordinary first page at "sh".
    prefixes={'h':['星'], 's':list('中国河地天人月山上'),
              'sh':list('中月山日人下上个口河天地国'),
              'shp':list('中月天国日山人口上河'), 'shph':list('中月国'),
              'shphn':list('中日')}
    lua='return {codes={["期"]="sh"},prefixes={'
    for code,chars in prefixes.items():
        lua+='["'+code+'"]={'+','.join('{"'+char+'",'+str(100-i)+'}' for i,char in enumerate(chars))+'},'
    (user/'lua/bihua_local_data.lua').write_text(lua+'}}',encoding='utf-8')
    (user/'lua/bihua_local_associations.lua').write_text('return {["星"]={'+','.join('{suffix="'+ch+'",weight=100}' for ch in '期河天地国人上月山日')+'}}',encoding='utf-8')
    dll=c.CDLL(str(runtime/'rime.dll'))
    def bind(name,result,*args):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(args);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits))
    maintenance=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    create=bind('RimeCreateSession',c.c_size_t);destroy=bind('RimeDestroySession',c.c_int,c.c_size_t)
    finalize=bind('RimeFinalize',None);select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
    process=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    setprop=bind('RimeSetProperty',c.c_int,c.c_size_t,c.c_char_p,c.c_char_p)
    get=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));free=bind('RimeFreeContext',c.c_int,c.POINTER(abi.Context))
    commit=bind('RimeGetCommit',c.c_int,c.c_size_t,c.POINTER(abi.Commit));free_commit=bind('RimeFreeCommit',c.c_int,c.POINTER(abi.Commit))
    clear=bind('RimeClearComposition',None,c.c_size_t)
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(runtime/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.bihua_carry_probe';traits.min_log_level=2;traits.log_dir=b''
    setup(c.byref(traits));init(c.byref(traits));session=0;frames=[]
    try:
        maintenance(1);join();session=create();assert session and select(session,b'bihua_mvp')
        def key(value):return process(session,ord(value) if isinstance(value,str) else value,0)
        def stroke(value):
            if device=='mouse':
                setprop(session,b'bihua_mouse_action',value.encode());key(0xffd5)
            elif device=='keypad':key({'h':0xffb1,'s':0xffb2,'p':0xffb3,'n':0xffb4}[value])
            else:key('d' if value=='n' else value)
        def state():
            ctx=abi.initialized(abi.Context);assert get(session,c.byref(ctx))
            try:out={'preedit':abi.text(ctx.composition.preedit),'page':ctx.menu.page_no,'candidates':[abi.text(ctx.menu.candidates[i].text) for i in range(ctx.menu.num_candidates)],'comments':[abi.text(ctx.menu.candidates[i].comment) for i in range(ctx.menu.num_candidates)]}
            finally:free(c.byref(ctx))
            frames.append(out);return out
        def committed():
            value=abi.initialized(abi.Commit)
            if not commit(session,c.byref(value)):return ''
            try:return abi.text(value.text)
            finally:free_commit(c.byref(value))
        def disk():return json.loads(json.loads((user/'bihua_personal_association_v1.jsonl').read_text(encoding='utf-8-sig'))['payload'])
        def begin():
            clear(session);committed();stroke('h');key('1');assert committed()=='星';state()
        begin();before=disk();stroke('s');first=state()
        expected=list('期河天地国人上月') if page_size==9 else list('期河') if page_size==3 else []
        assert first['candidates'][:len(expected)]==expected,first
        assert len(first['candidates'])==len(set(first['candidates'])) and not any(first['comments'])
        assert '中' in first['candidates'],'ordinary first candidate must remain on the first page'
        assert disk()==before,'matching must not write feedback or training history'
        if page_size==1:
            assert first['candidates']==['中'],'a one-slot page must reserve its only slot for ordinary candidates'
            key('1');assert committed()=='中'
            assert disk()['confirmed']['星期']['negative_count']==1
            return {'result':'PASS','page_size':page_size,'device':device,'frames':frames,'zero_pin_slots':True,'ordinary_first_candidate_visible':True}
        key(0xff56);page=state();assert page['page']==1
        key(0xff55);assert state()['candidates']==first['candidates']
        stroke('h');second=state();assert second['candidates'][:len(expected)]==expected,second
        assert disk()==before,'persistent rank must not grow with typed strokes'
        key(0xff08);assert state()['candidates']==first['candidates'],'Backspace recomputes the same pinned set'
        stroke('h');stroke('p');third=state()
        expected_third=list('河天国人上月') if page_size==9 else list('河')
        assert third['candidates'][:len(expected_third)]==expected_third,third
        key('1');assert committed()=='河'
        after=disk();usage=after['confirmed']['星河']
        assert usage['score']==11 and usage['positive_count']==1 and usage['negative_count']==0,usage
        assert after['sequence']==before['sequence'],'a selected recommendation does not train itself as manual history'
        begin();stroke('s');stroke('h');stroke('p');stroke('h');stroke('n')
        assert state()['candidates']==['中','日'],'all filtered out must return to ordinary candidates; second-page predictions cannot enter'
        key('1');assert committed()=='中'
        last=disk();assert last['confirmed']['星河']['negative_count']==1,last['confirmed']
        # A context/focus boundary must abandon, rather than penalize, a carry.
        begin();stroke('s');neutral_before=disk()
        setprop(session,b'bihua_feedback_neutral_boundary',b'1');stroke('h')
        assert state()['candidates'][0]=='中'
        assert disk()==neutral_before,'neutral boundary must not learn rejection'
        return {'result':'PASS','page_size':page_size,'device':device,'frames':frames,
                'source_is_prediction_first_page':True,'maximum_page_size_minus_one':True,'ordinary_first_candidate_visible':True,'survivors_stay_first_beyond_normal_first_page':True,
                'matching_does_not_write_weight':True,'selection_adds_one':True,'all_filtered_out':True,
                'deduplicated':True,'backspace':True,'paging':True,'neutral_boundary':True}
    finally:
        if session:destroy(session)
        finalize()


def probe(runtime,user):
    runtime=Path(runtime).resolve();user=Path(user).resolve();user.mkdir(parents=True,exist_ok=True)
    results=[]
    for page_size in (9,3,1):
        for device in ('letter','keypad','mouse'):
            output=user/f'{page_size}-{device}.json'
            subprocess.run([sys.executable,'-B',__file__,'--branch',runtime,user/f'{page_size}-{device}',str(page_size),device,output],check=True,capture_output=True,timeout=70)
            results.append(json.loads(output.read_text(encoding='utf-8')))
        assert results[-1]['frames']==results[-2]['frames']==results[-3]['frames']
    return {'result':'PASS','real_rime':True,'production_runtime_with_isolated_fixture':True,'branches':results}

if __name__=='__main__':
    if sys.argv[1]=='--branch':result=branch(Path(sys.argv[2]),Path(sys.argv[3]),int(sys.argv[4]),sys.argv[5]);output=Path(sys.argv[6])
    else:result=probe(sys.argv[1],sys.argv[2]);output=Path(sys.argv[3])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
