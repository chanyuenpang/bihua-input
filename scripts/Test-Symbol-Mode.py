"""Real Rime punctuation menu, suspended-query and neutral-learning checks."""
from pathlib import Path
import argparse,ctypes as c,importlib.util,json,shutil,uuid,yaml
ROOT=Path(__file__).resolve().parent.parent
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--packaged',action='store_true');parser.add_argument('--user',type=Path);parser.add_argument('--report',type=Path);args=parser.parse_args()
    app=args.runtime.resolve();user=args.user.resolve() if args.user else ROOT/'.verification'/('symbols-'+uuid.uuid4().hex)
    shutil.copytree(app/'profile',user)
    if not args.packaged:
        for p in (ROOT/'rime/lua').glob('*.lua'):shutil.copy2(p,user/'lua'/p.name)
    schema=yaml.safe_load((user/'bihua_mvp.schema.yaml').read_text(encoding='utf-8-sig'))
    if not args.packaged:schema['bihua_symbols']=yaml.safe_load((ROOT/'rime/bihua_local.schema.yaml').read_text(encoding='utf-8'))['bihua_symbols']
    (user/'bihua_mvp.schema.yaml').write_text(yaml.safe_dump(schema,allow_unicode=True),encoding='utf-8')
    abi_path=ROOT/'packaging/rime_abi.py' if (ROOT/'packaging/rime_abi.py').exists() else app/'scripts/rime_abi.py'
    spec=importlib.util.spec_from_file_location('abi',abi_path);abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)
    dll=c.CDLL(str(app/'rime.dll'))
    def bind(name,result,*types):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(types);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits));finish=bind('RimeFinalize',None)
    maintain=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    create=bind('RimeCreateSession',c.c_size_t);destroy=bind('RimeDestroySession',c.c_int,c.c_size_t)
    select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p);key=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    getctx=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));freectx=bind('RimeFreeContext',None,c.POINTER(abi.Context))
    getcommit=bind('RimeGetCommit',c.c_int,c.c_size_t,c.POINTER(abi.Commit));freecommit=bind('RimeFreeCommit',None,c.POINTER(abi.Commit))
    clear=bind('RimeClearComposition',None,c.c_size_t);setprop=bind('RimeSetProperty',None,c.c_size_t,c.c_char_p,c.c_char_p)
    getprop=bind('RimeGetProperty',c.c_int,c.c_size_t,c.c_char_p,c.c_char_p,c.c_size_t)
    option=bind('RimeSetOption',None,c.c_size_t,c.c_char_p,c.c_int)
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(app/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.symbol_test';traits.min_log_level=2;traits.log_dir=b''
    setup(c.byref(traits));init(c.byref(traits));session=0
    def press(code,mask=0):return key(session,ord(code) if isinstance(code,str) else code,mask)
    def prop(name):
        buf=c.create_string_buffer(256);getprop(session,name.encode(),buf,len(buf));return buf.value.decode()
    def state():
        value=abi.initialized(abi.Context);assert getctx(session,c.byref(value))
        try:return {'preedit':abi.text(value.composition.preedit),'page':value.menu.page_no,'highlight':value.menu.highlighted_candidate_index,'last':bool(value.menu.is_last_page),'candidates':[abi.text(value.menu.candidates[i].text) for i in range(value.menu.num_candidates)]}
        finally:freectx(c.byref(value))
    def committed():
        value=abi.initialized(abi.Commit)
        if not getcommit(session,c.byref(value)):return ''
        try:return abi.text(value.text)
        finally:freecommit(c.byref(value))
    def query(text):
        clear(session);committed()
        for code in text:press(code)
        return state()
    def toggle():
        setprop(session,b'bihua_mouse_action',b'symbol_toggle');press(0xffd5)
    def history():
        path=user/'bihua_personal_association_v1.jsonl'
        return path.read_bytes() if path.exists() else None
    try:
        maintain(1);join();session=create();assert session and select(session,b'bihua_mvp')
        symbols=schema['bihua_symbols']['items'];assert len(symbols)==36
        for text in ('','h','hshsz','hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh'):
            before=query(text);saved=history();toggle()
            assert state()['candidates']==symbols[:9] and not committed(),(text,state(),prop('bihua_symbol_status'))
            press(0xffae);assert state()['candidates']==symbols[:9] and not committed()
            press(0xff1b);assert state()==before and not committed(),(text,state(),before)
            assert history()==saved,'open/cancel changed association storage'
            toggle();toggle();assert state()==before and not committed()
        before=query('h');toggle()
        press('-');assert state()['page']==0
        press('=');assert state()['page']==1
        press('-');assert state()['page']==0
        press(0xffaf);assert state()['highlight']==0
        press(0xffaa);assert state()['highlight']==1
        press(0xffab);assert state()['page']==1
        press(0xffad);assert state()['page']==0
        for _ in range(9):press(0xffab)
        assert state()['page']==3 and state()['last']
        press(0xffb9);assert committed()=='\\' and state()['preedit']==before['preedit'],state()
        for index in range(1,10):
            before=query('h');toggle();press(0xffb0+index)
            assert committed()==symbols[index-1] and state()['preedit']==before['preedit'],(index,state())
        for confirmation in (0xffb0,0x20,0xff0d,0xff8d):
            before=query('h');toggle();press(0xffaa);press(confirmation)
            assert committed()=='。' and state()['preedit']==before['preedit'],(confirmation,state())
        before=query('h');toggle();option(session,b'ascii_mode',1)
        assert prop('bihua_symbol_active')=='' and not committed()
        option(session,b'ascii_mode',0)
        assert state()==before and not committed(),state()
        query('hhpd');press('1');assert committed()=='天';before=state();saved=history()
        toggle();press(0xff1b);assert state()==before and history()==saved,(state(),before)
        old=json.loads(json.loads(history().decode('utf-8-sig'))['payload'])
        toggle();press(0xffb1);assert committed()=='，'
        now=json.loads(json.loads(history().decode('utf-8-sig'))['payload'])
        assert now['window']==old['window'] and now['confirmed']==old['confirmed'],'symbol learned or discounted predictions'
        assert not state()['candidates'],'symbol must not produce a prediction'
        result={'result':'PASS','cases':22,'directory':str(user),'suspended_queries_restored':True,'cancel_preserves_history_bytes':True,'symbol_commit_does_not_learn':True,'keypad_selection_navigation_paging':True,'symbol_catalog_size':36,'scope':'Private Rime process. Num Lock native hook and physical keyboard not exercised.'}
    finally:
        if session:destroy(session)
        finish()
    (args.report or user/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()
