"""Copy stock TSF binaries with the two-item daily menu; executable code stays intact."""
import argparse
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import shutil
import struct
import hashlib
import json

k=c.WinDLL('kernel32',use_last_error=True)
def bind(name, result, *args):
    f=getattr(k,name); f.restype=result;f.argtypes=args;return f
load=bind('LoadLibraryExW',w.HMODULE,w.LPCWSTR,w.HANDLE,w.DWORD)
free=bind('FreeLibrary',w.BOOL,w.HMODULE)
find=bind('FindResourceExW',w.HANDLE,w.HMODULE,c.c_void_p,c.c_void_p,w.WORD)
size=bind('SizeofResource',w.DWORD,w.HMODULE,w.HANDLE)
resource=bind('LoadResource',w.HANDLE,w.HMODULE,w.HANDLE)
lock=bind('LockResource',c.c_void_p,w.HANDLE)
begin=bind('BeginUpdateResourceW',w.HANDLE,w.LPCWSTR,w.BOOL)
update=bind('UpdateResourceW',w.BOOL,w.HANDLE,c.c_void_p,c.c_void_p,w.WORD,c.c_void_p,w.DWORD)
end=bind('EndUpdateResourceW',w.BOOL,w.HANDLE,w.BOOL)
LANGCB=c.WINFUNCTYPE(w.BOOL,w.HMODULE,c.c_void_p,c.c_void_p,w.WORD,c.c_ssize_t)
enumlangs=bind('EnumResourceLanguagesW',w.BOOL,w.HMODULE,c.c_void_p,c.c_void_p,LANGCB,c.c_ssize_t)
def menus(path):
    module=load(str(path),None,2)
    if not module: raise c.WinError(c.get_last_error())
    out=[]
    try:
        for identity in (105,108,109):
            def collect(module,kind,name,language,param):
                handle=find(module,4,identity,language)
                out.append((identity,language,c.string_at(lock(resource(module,handle)),size(module,handle))))
                return True
            callback=LANGCB(collect)
            enumlangs(module,4,identity,callback,0)
    finally:free(module)
    return out
def patched(data):
    version,offset=struct.unpack_from('<HH',data)
    if version!=0:raise ValueError('Expected standard MENU template')
    out=bytearray(struct.pack('<HHH',0,0,0x90))
    out.extend('笔画输入法\0'.encode('utf-16-le'))
    for index,(identity,label) in enumerate(((40017,'笔画设置'),)):
        out.extend(struct.pack('<HH',0x80,identity))
        out.extend((label+'\0').encode('utf-16-le'))
    return bytes(out)

def menu_items(data):
    version,offset=struct.unpack_from('<HH',data);assert version==0
    pos=4+offset;items=[]
    def word():
        nonlocal pos
        value=struct.unpack_from('<H',data,pos)[0];pos+=2;return value
    def text():
        start=pos
        while word():pass
        return data[start:pos-2].decode('utf-16-le')
    def level():
        while True:
            flags=word();identity=None if flags&0x10 else word();label=text()
            if flags&0x10:level()
            else:items.append((identity,label))
            if flags&0x80:break
    level();assert pos==len(data);return items
def main():
    p=argparse.ArgumentParser();p.add_argument('--stock',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True); report={}
    for name in ('weasel.dll','weaselx64.dll'):
        original=a.stock/name;target=a.output/name
        shutil.copy2(original,target); rows=menus(original);assert len(rows)>=3
        handle=begin(str(target),False);assert handle
        try:
            for identity,language,data in rows:
                packed=patched(data);buffer=c.create_string_buffer(packed)
                if not update(handle,4,identity,language,buffer,len(packed)):raise c.WinError(c.get_last_error())
        except BaseException:
            end(handle,True);raise
        if not end(handle,False):raise c.WinError(c.get_last_error())
        readback=menus(target);assert len(readback)==len(rows)
        assert all(menu_items(data)==[(40017,'笔画设置')] for _,_,data in readback)
        report[name]={'stock_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'patched_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'menu_resources':len(rows)}
    (a.output/'menus.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__':main()
