"""Real Rime keypad selection and character learning in disposable profiles."""
from pathlib import Path
import argparse, ctypes as c, hashlib, importlib.util, json, shutil, subprocess, sys, time, uuid
import yaml
from key_bindings import ACTIONS, KEYPAD

ROOT=Path(__file__).resolve().parent.parent

def run(args):
    runtime=args.runtime.resolve()
    user=args.user.resolve() if args.user else ROOT/'.verification'/('keypad-learning-'+uuid.uuid4().hex)
    assert user.is_relative_to((ROOT/'.verification').resolve())
    if not args.reuse:
        shutil.copytree(runtime/'profile',user)
        if not args.baseline:
            for path in (ROOT/'rime/lua').glob('*.lua'):shutil.copy2(path,user/'lua'/path.name)
        schema=yaml.safe_load((user/'bihua_mvp.schema.yaml').read_text(encoding='utf-8'))
        schema['bihua_matcher']['character_learning']=True
        schema['bihua_character']={'dictionary':'bihua_local','user_dict':'bihua_mvp_character_v1'}
        if args.mode=='keys':
            schema['bihua_matcher'].update(personal_association=True,static_association=True)
            keys=KEYPAD['standard' if args.style=='standard' else '789456'].copy()
            if args.style=='custom':keys=dict(zip(ACTIONS,['KP_9','KP_8','KP_7','KP_6','KP_5','KP_Divide','KP_Multiply']))
            if args.style=='legacy':keys['separator']='KP_Divide'
            schema['bihua_keys']['keypad']=keys
            schema['bihua_keys']['keypad_style']='custom'
            schema['menu']['page_size']=args.page_size
        else:
            # No prediction carry can conceal a character-ranking regression.
            schema['bihua_matcher'].update(personal_association=False,static_association=False)
        (user/'bihua_mvp.schema.yaml').write_text(yaml.safe_dump(schema,allow_unicode=True,sort_keys=False),encoding='utf-8')
    spec=importlib.util.spec_from_file_location('abi',ROOT/'packaging/rime_abi.py')
    abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)
    dll=c.CDLL(str(runtime/'rime.dll'))
    def bind(name,result,*types):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(types);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits));finish=bind('RimeFinalize',None)
    maintain=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    create=bind('RimeCreateSession',c.c_size_t);destroy=bind('RimeDestroySession',c.c_int,c.c_size_t)
    select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p);key=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    context=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));free=bind('RimeFreeContext',None,c.POINTER(abi.Context))
    clear=bind('RimeClearComposition',None,c.c_size_t)
    getcommit=bind('RimeGetCommit',c.c_int,c.c_size_t,c.POINTER(abi.Commit));freecommit=bind('RimeFreeCommit',None,c.POINTER(abi.Commit))
    getprop=bind('RimeGetProperty',c.c_int,c.c_size_t,c.c_char_p,c.c_char_p,c.c_size_t)
    setprop=bind('RimeSetProperty',None,c.c_size_t,c.c_char_p,c.c_char_p)
    option=bind('RimeSetOption',None,c.c_size_t,c.c_char_p,c.c_int)
    choose=bind('RimeSelectCandidate',c.c_int,c.c_size_t,c.c_size_t)
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(runtime/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.keypad_learning_test';traits.min_log_level=2;traits.log_dir=b''
    setup(c.byref(traits));init(c.byref(traits));session=0
    latencies=[]
    def press(code,mask=0):
        started=time.perf_counter();handled=key(session,ord(code) if isinstance(code,str) else code,mask)
        latencies.append((time.perf_counter()-started)*1000);return handled
    def page():
        value=abi.initialized(abi.Context);assert context(session,c.byref(value))
        try:return {'page':value.menu.page_no,'highlight':value.menu.highlighted_candidate_index,'last':bool(value.menu.is_last_page),'preedit':abi.text(value.composition.preedit),'candidates':[abi.text(value.menu.candidates[i].text) for i in range(value.menu.num_candidates)]}
        finally:free(c.byref(value))
    def commit():
        value=abi.initialized(abi.Commit)
        if not getcommit(session,c.byref(value)):return ''
        try:return abi.text(value.text)
        finally:freecommit(c.byref(value))
    def prop(name):
        buffer=c.create_string_buffer(1024);getprop(session,name.encode(),buffer,len(buffer));return buffer.value.decode()
    def query(code='hshsz'):
        clear(session);commit()
        for char in code:press('t' if char=='?' else char)
        return page()
    result={'user':str(user),'mode':args.mode,'baseline':args.baseline}
    hashes={name:hashlib.sha256((user/name).read_bytes()).hexdigest() for name in ['bihua_local.dict.yaml','lua/bihua_local_data.lua']}
    try:
        if not args.reuse:maintain(1);join()
        session=create();assert session and select(session,b'bihua_mvp')
        if args.mode=='keys':
            occupied=set(keys.values());spare=[i for i in range(1,10) if 'KP_'+str(i) not in occupied]
            for index,digit in enumerate(spare):
                for paging in (False,True):
                    first=query('h')
                    if paging:press(0xffab);first=page()
                    press(0xffb0+digit)
                    if index>=len(first['candidates']):
                        assert not commit() and page()==first
                        continue
                    assert commit()==first['candidates'][index],(digit,first,page())
                    assert page()['candidates'],'selection must continue predictions'
                    # The same free key selects a prediction, not another stroke.
                    prediction=page()['candidates']
                    if index<len(prediction):
                        press(0xffb0+digit);assert commit()==prediction[index]
            def physical(name):return {'KP_Divide':0xffaf,'KP_Multiply':0xffaa,'KP_Decimal':0xffae}.get(name,0xffb0+int(name[-1]) if name[-1].isdigit() else 0)
            clear(session);commit()
            for action in ('s','z','separator','s','z'):press(physical(keys[action]))
            assert '‘' in page()['preedit'],page()
            while '中国' not in page()['candidates'] and not page()['last']:press(0xffab)
            assert '中国' in page()['candidates'],page()
            if keys['separator']=='KP_Decimal':
                press(0xffae,1<<30)
                before=page();press(0xffb0+spare[0])
                assert commit()==before['candidates'][0],'bound decimal must not arm dot-held selection'
            if 'KP_Divide' not in occupied and 'KP_Multiply' not in occupied:
                before=query('h');press(0xffaa)
                assert page()['highlight']==1 and not commit(),page()
                press(0xffaf);assert page()['highlight']==0 and not commit()
                press(0xffaa);press(0xffb0);assert commit()==before['candidates'][1]
            clear(session);commit()
            for action in ('h','h','p','n'):press(physical(keys[action]))
            assert page()['preedit']=='一一丿丶',page()
            assert page()['candidates'][0]=='天'
            press(0xffb0);assert commit()=='天'
            if 'KP_Decimal' not in occupied:
                query('h');press(0xffab);before=page()
                press(0xffae);press(0xffb2);assert commit()==before['candidates'][1]
                press(0xffae,1<<30)
            before=query('h')
            for mask in (1,4,8,1<<30):
                press(0xffb0+spare[0],mask);assert not commit() and page()==before,(mask,page())
            if 'KP_Decimal' not in occupied:press(0xffae)
            setprop(session,b'bihua_keymap_reset',b'focus_out')
            press(physical(keys['h']));assert page()['preedit']=='一一' and not commit()
            press(0xffae,1<<30)
            # Missing slots, including a smaller configured page, are inert.
            before=query('hhpn')
            for index,digit in enumerate(spare):
                if index>=len(before['candidates']):press(0xffb0+digit);assert page()==before and not commit()
            clear(session);commit();before=page();press(0xffb0+spare[0]);assert page()==before and not commit()
            option(session,b'ascii_mode',1);assert not press(0xffb0+spare[0]);option(session,b'ascii_mode',0)
            result.update(style=args.style,page_size=args.page_size,free_digits=spare,selection=True,paging=True,prediction=True,modifiers=True,empty_and_missing=True,bindings_preserved=True)
        else:
            def position(code):
                row=query(code)
                while '吉' not in row['candidates'] and not row['last']:
                    press(0xffab);row=page()
                return row['page']*9+row['candidates'].index('吉')+1
            wildcard_before=position('hshs?')
            first=query();ranks=[first['candidates'].index('吉')+1]
            if args.reuse:assert ranks[0]==1,first
            else:assert ranks[0]==4,first
            for _ in range(3):
                before=query();slot=before['candidates'].index('吉')
                press(str(slot+1));assert commit()=='吉'
                assert not page()['candidates']
                ranks.append(query()['candidates'].index('吉')+1)
            if args.baseline:assert ranks==[4,4,4,4],ranks
            else:
                assert ranks[-1]==1 and (args.reuse or ranks[1]<ranks[0]),ranks
                assert prop('bihua_character_storage_status')=='ok'
                assert int(prop('bihua_character_usage'))==(7 if args.reuse else 3)
                # Wildcard and personal aliases share the same learned character.
                wildcard_after=position('hshs?')
                assert wildcard_after<wildcard_before or args.reuse,(wildcard_before,wildcard_after)
                assert query()['candidates'][0]=='吉'
                count=prop('bihua_character_usage')
                for _ in range(3):query();press(0xff1b)
                assert prop('bihua_character_usage')==count,'browsing must not learn'
                if not args.reuse:
                    # Same backend, another Rime session immediately sees the count.
                    old=session;session=create();assert select(session,b'bihua_mvp')
                    assert query()['candidates'][0]=='吉';destroy(session);session=old
                    # Explicit mouse selection uses the same path, exactly once.
                    query();setprop(session,b'bihua_explicit_selection',b'1');setprop(session,b'bihua_selection_input',b'hshsz')
                    assert choose(session,0) and commit()=='吉'
                    assert prop('bihua_character_usage')=='4'
            result.update(ranks=ranks,wildcard_before=wildcard_before,storage_status=prop('bihua_character_storage_status'),uses=prop('bihua_character_usage'))
        assert hashes=={name:hashlib.sha256((user/name).read_bytes()).hexdigest() for name in hashes}
        result.update(result='PASS',base_data_unchanged=True,key_latency_max_ms=round(max(latencies),3))
    finally:
        if session:destroy(session)
        finish()
    print(json.dumps(result,ensure_ascii=True));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--mode',choices=['keys','learning'],default='keys');parser.add_argument('--style',choices=['standard','789456','custom','legacy'],default='789456')
    parser.add_argument('--page-size',type=int,default=9);parser.add_argument('--baseline',action='store_true');parser.add_argument('--reuse',action='store_true');parser.add_argument('--user',type=Path)
    args=parser.parse_args();run(args)
