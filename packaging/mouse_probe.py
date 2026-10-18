"""Compare mouse and keyboard paths using packaged product data without user history."""
import ctypes as c
import json
from pathlib import Path
import shutil
import subprocess
import sys
import rime_abi as abi

def branch(runtime,user,mode,style):
    import yaml
    user.mkdir(parents=True,exist_ok=True)
    for source in (runtime/'profile').iterdir():
        if source.is_dir():shutil.copytree(source,user/source.name,dirs_exist_ok=True)
        else:shutil.copy2(source,user/source.name)
    bindings={'h':'h','s':'s','p':'p','n':'d','z':'z','wildcard':'t','separator':'f'}
    if style=='asdfgt':bindings.update(h='a',s='s',p='d',n='f',z='g',wildcard='t',separator='r')
    if style=='custom':bindings=dict(zip(bindings,['j','k','l','o','u','y','i']))
    (user/'bihua_mvp.custom.yaml').write_text(yaml.safe_dump({'patch':{'bihua_keys/letter_style':style,'bihua_keys/letter':bindings}}),encoding='utf-8')
    dll=c.CDLL(str(runtime/'rime.dll'))
    def bind(name,result,*args):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(args);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits))
    maintain=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    finalize=bind('RimeFinalize',None);create=bind('RimeCreateSession',c.c_size_t)
    destroy=bind('RimeDestroySession',c.c_int,c.c_size_t);select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
    process=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    prop=bind('RimeSetProperty',c.c_int,c.c_size_t,c.c_char_p,c.c_char_p)
    get=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));free=bind('RimeFreeContext',c.c_int,c.POINTER(abi.Context))
    commit=bind('RimeGetCommit',c.c_int,c.c_size_t,c.POINTER(abi.Commit));free_commit=bind('RimeFreeCommit',c.c_int,c.POINTER(abi.Commit))
    clear=bind('RimeClearComposition',None,c.c_size_t)
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(runtime/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.bihua_mouse_probe';traits.min_log_level=2;traits.log_dir=b''
    setup(c.byref(traits));init(c.byref(traits));session=0;frames=[]
    try:
        maintain(1);join();session=create();assert session and select(session,b'bihua_mvp')
        def state():
            ctx=abi.initialized(abi.Context);assert get(session,c.byref(ctx))
            try:out={'preedit':abi.text(ctx.composition.preedit),'page':ctx.menu.page_no,'candidates':[abi.text(ctx.menu.candidates[i].text) for i in range(ctx.menu.num_candidates)]}
            finally:free(c.byref(ctx))
            value=abi.initialized(abi.Commit);out['commit']=''
            if commit(session,c.byref(value)):
                out['commit']=abi.text(value.text);free_commit(c.byref(value))
            frames.append(out);return out
        def action(name):
            if mode=='mouse' and name in bindings and name!='separator':
                prop(session,b'bihua_mouse_action',name.encode());assert process(session,0xffd5,0)
            else:
                key=bindings.get(name,name)
                process(session,{'Page_Down':0xff56,'Page_Up':0xff55,'Return':0xff0d,'BackSpace':0xff08}.get(key,ord(key) if len(key)==1 else 0),0)
            return state()
        def query(code):
            clear(session)
            for name in code:out=action(name)
            return out
        query('h');assert action('Page_Down')['page']==1;assert action('Page_Up')['page']==0
        out=query('hhpn');assert '天' in out['candidates']
        assert action('BackSpace')['preedit']=='一一丿'
        out=action('n');assert '天' in out['candidates'];chosen=out['candidates'].index('天')
        out=action(str(chosen+1));assert out['commit']=='天' and out['candidates']
        expected=out['candidates'][0];assert action('1')['commit']==expected
        action('Return');assert not frames[-1]['candidates']
        out=query(['h','wildcard','p','n']);assert '天' in out['candidates'] and '？' in out['preedit']
        clear(session);assert action('BackSpace')['commit']==''
        out=query('z');assert out['preedit']=='𠃌'
        clear(session)
        for name in ['s','z','separator','s','z']:out=action(name)
        assert '中国' in out['candidates']
        return frames
    finally:
        if session:destroy(session)
        finalize()

def probe(runtime,user):
    runtime=Path(runtime).resolve();user=Path(user).resolve();user.mkdir(parents=True,exist_ok=True)
    for style in ('standard','asdfgt','custom'):
        frames=[]
        for mode in ('keyboard','mouse'):
            output=user/(style+'-'+mode+'.json')
            subprocess.run([sys.executable,'-B',__file__,'--branch',runtime,user/(style+'-'+mode),mode,style,output],check=True,timeout=90,capture_output=True)
            frames.append(json.loads(output.read_text(encoding='utf-8')))
        assert frames[0]==frames[1],style+' mouse/keyboard mismatch'
    return {'result':'PASS','real_rime':True,'packaged_product_data_only':True,'keyboard_mouse_frames_equal':True,
            'custom_key_independent':True,'five_strokes':True,'wildcard':True,'paging':True,'candidate_commit':True,
            'continuation_commit':True,'enter_closes':True,'keyboard_separator':True,'backspace':True,'empty_backspace_no_commit':True,'fold_glyph':True}

if __name__=='__main__':
    if sys.argv[1]=='--branch':
        result=branch(Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4],sys.argv[5]);output=Path(sys.argv[6])
    else:result=probe(sys.argv[1],sys.argv[2]);output=Path(sys.argv[3])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
