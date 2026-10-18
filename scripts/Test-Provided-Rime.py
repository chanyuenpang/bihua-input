"""Fresh-profile real Rime queries must reproduce the supplied static ranking."""
from pathlib import Path
import argparse,ctypes as c,importlib.util,json,shutil,uuid
import release_profile as product

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True);args=parser.parse_args()
    runtime=args.runtime.resolve();root=product.ROOT
    user=root/'.verification'/('provided-rime-'+uuid.uuid4().hex)
    shutil.copytree(runtime/'profile',user)
    spec=importlib.util.spec_from_file_location('abi',root/'packaging/rime_abi.py');abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)
    dll=c.CDLL(str(runtime/'rime.dll'))
    def bind(name,result,*types):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(types);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits));finish=bind('RimeFinalize',None)
    maintain=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    create=bind('RimeCreateSession',c.c_size_t);destroy=bind('RimeDestroySession',c.c_int,c.c_size_t)
    select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
    key=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    context=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));free=bind('RimeFreeContext',None,c.POINTER(abi.Context))
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(runtime/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.provided_data_test';traits.min_log_level=2;traits.log_dir=b''
    setup(c.byref(traits));init(c.byref(traits))
    def page(session):
        value=abi.initialized(abi.Context);assert context(session,c.byref(value))
        try:return {'page':value.menu.page_no,'last':bool(value.menu.is_last_page),'candidates':[abi.text(value.menu.candidates[i].text) for i in range(value.menu.num_candidates)]}
        finally:free(c.byref(value))
    cases={}
    try:
        maintain(1);join()
        queries=['h','s','p','n','z','hh','hs','hp','hsh','hshs','hshsz','hshszh','sz','szh','szhh','szhhshnh','ph','nh','nph','hhpn']
        for code in queries:
            session=create();assert select(session,b'bihua_mvp')
            try:
                for char in code:key(session,ord(char),0)
                first=page(session)
                assert first['candidates'],code
                cases[code]=first['candidates']
                if code=='hshsz':
                    all_rows=first['candidates'][:]
                    for _ in range(4):
                        key(session,0xffab,0);all_rows+=page(session)['candidates']
                    # The raw snapshot contains traditional forms; Rime's final
                    # simplifier/uniquifier output is the user's reference UI.
                    reference=list('提喜担吉博损扣抽操鼓摆贡坦戴嘉押揭捐埋袁坤坝捏拐彭捉塌拽堤摧哉捆揣捍汞撮场远鼙台摁撂卖揖熹')
                    assert all_rows==reference and all_rows.index('吉')==3,all_rows
            finally:destroy(session)
        assert cases['hshsz']==list('提喜担吉博损扣抽操')
        proof={'result':'PASS','clean_user_directory':str(user),'personal_history_loaded':False,'queries':cases,
               'first_45_match_reference':True,'ji_rank_for_12125':4,'real_rime_dll':str(runtime/'rime.dll')}
        (root/'.verification/provided-rime-0628.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'result':'PASS','fresh_rime_queries':len(cases),'first_45_match_reference':True,'ji_rank':4}))
    finally:finish()
if __name__=='__main__':main()
