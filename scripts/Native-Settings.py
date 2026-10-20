"""Windows settings window using native controls and the bundled Python runtime."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import importlib.util
import json
import os
from pathlib import Path
import threading
import struct
import zlib

from key_bindings import ACTIONS, LETTER, KEYPAD, physical_vk, physical_key, parse_key, reserved_reason, overlaps, validate as validate_keys, assign as assign_key
import appearance
import stroke_icons

PAGES=(('keys','键盘与按键'),('mouse','鼠标面板'),('paging','候选与翻页'),
       ('prediction','本地联想'),('words','个人词库'),('strokes','个人笔顺'),('appearance','外观'))

spec=importlib.util.spec_from_file_location('panel',Path(__file__).with_name('Settings-Panel.py'))
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
u=c.WinDLL('user32',use_last_error=True);g=c.WinDLL('gdi32',use_last_error=True)
k=c.WinDLL('kernel32',use_last_error=True)
# Declare awareness before creating any HWND, so Windows never bitmap-scales us.
u.SetProcessDpiAwarenessContext.argtypes=[c.c_void_p]
u.SetThreadDpiAwarenessContext.argtypes=[c.c_void_p];u.SetThreadDpiAwarenessContext.restype=c.c_void_p
u.SetProcessDpiAwarenessContext(c.c_void_p(-4))
u.SetThreadDpiAwarenessContext(c.c_void_p(-4))
u.GetDpiForSystem.restype=w.UINT
u.GetWindowDpiAwarenessContext.argtypes=[w.HWND];u.GetWindowDpiAwarenessContext.restype=c.c_void_p
u.AreDpiAwarenessContextsEqual.argtypes=[c.c_void_p,c.c_void_p]
u.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
u.MoveWindow.argtypes=[w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.BOOL]
LRESULT=c.c_ssize_t
PROC=c.WINFUNCTYPE(LRESULT,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
class WNDCLASS(c.Structure):
    _fields_=[('style',w.UINT),('proc',PROC),('cls_extra',c.c_int),('wnd_extra',c.c_int),
              ('instance',w.HINSTANCE),('icon',w.HICON),('cursor',w.HANDLE),('background',w.HBRUSH),
              ('menu',w.LPCWSTR),('name',w.LPCWSTR)]
u.DefWindowProcW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];u.DefWindowProcW.restype=LRESULT
u.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]
u.CreateWindowExW.restype=w.HWND
u.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];u.SendMessageW.restype=LRESULT
u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
u.SetWindowTextW.argtypes=[w.HWND,w.LPCWSTR]
u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,c.c_int]
u.GetWindowTextLengthW.argtypes=[w.HWND];u.GetWindowTextLengthW.restype=c.c_int
u.ShowWindow.argtypes=[w.HWND,c.c_int];u.DestroyWindow.argtypes=[w.HWND]
u.IsWindowVisible.argtypes=[w.HWND];u.IsWindowVisible.restype=w.BOOL
u.EnableWindow.argtypes=[w.HWND,w.BOOL]
u.MessageBoxW.argtypes=[w.HWND,w.LPCWSTR,w.LPCWSTR,w.UINT]
u.FindWindowW.argtypes=[w.LPCWSTR,w.LPCWSTR];u.FindWindowW.restype=w.HWND
u.SetForegroundWindow.argtypes=[w.HWND]
u.SetTimer.argtypes=[w.HWND,c.c_size_t,w.UINT,c.c_void_p]
u.IsDialogMessageW.argtypes=[w.HWND,c.POINTER(w.MSG)]
k.GetModuleHandleW.argtypes=[w.LPCWSTR];k.GetModuleHandleW.restype=w.HMODULE
g.CreateFontW.restype=w.HANDLE
g.CreateFontW.argtypes=[c.c_int]*5+[w.DWORD]*8+[w.LPCWSTR]
g.DeleteObject.argtypes=[w.HANDLE]
u.LoadCursorW.argtypes=[w.HINSTANCE,c.c_void_p];u.LoadCursorW.restype=w.HANDLE

def rgb(value): return int(value[1:3],16)|(int(value[3:5],16)<<8)|(int(value[5:7],16)<<16)
COLORS={key:rgb(value) for key,value in {'background':'#f5f6f8','sidebar':'#f5f6f8','card':'#ffffff',
        'text':'#202830','muted':'#6b7480','green':'#196b50','selected':'#e8f3ee','line':'#e0e5e9','key':'#ffffff'}.items()}
class DRAWITEM(c.Structure):
    _fields_=[('kind',w.UINT),('id',w.UINT),('item',w.UINT),('action',w.UINT),('state',w.UINT),('window',w.HWND),('dc',w.HDC),('rect',w.RECT),('data',c.c_size_t)]
class PAINT(c.Structure):
    _fields_=[('dc',w.HDC),('erase',w.BOOL),('rect',w.RECT),('restore',w.BOOL),('update',w.BOOL),('reserved',w.BYTE*32)]
class KEYINFO(c.Structure):
    _fields_=[('vk',w.DWORD),('scan',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',c.c_size_t)]
HOOK=c.WINFUNCTYPE(LRESULT,c.c_int,w.WPARAM,w.LPARAM)
u.SetWindowsHookExW.argtypes=[c.c_int,HOOK,w.HINSTANCE,w.DWORD];u.SetWindowsHookExW.restype=w.HANDLE
u.UnhookWindowsHookEx.argtypes=[w.HANDLE]
u.CallNextHookEx.argtypes=[w.HANDLE,c.c_int,w.WPARAM,w.LPARAM];u.CallNextHookEx.restype=LRESULT
u.GetForegroundWindow.restype=w.HWND
u.InvalidateRect.argtypes=[w.HWND,c.POINTER(w.RECT),w.BOOL]
u.BeginPaint.argtypes=[w.HWND,c.POINTER(PAINT)];u.BeginPaint.restype=w.HDC
u.EndPaint.argtypes=[w.HWND,c.POINTER(PAINT)]
u.FillRect.argtypes=[w.HDC,c.POINTER(w.RECT),w.HBRUSH]
u.DrawTextW.argtypes=[w.HDC,w.LPCWSTR,c.c_int,c.POINTER(w.RECT),w.UINT]
u.DrawFocusRect.argtypes=[w.HDC,c.POINTER(w.RECT)]
g.CreateSolidBrush.argtypes=[w.DWORD];g.CreateSolidBrush.restype=w.HBRUSH
g.SetBkMode.argtypes=[w.HDC,c.c_int]
g.SetTextColor.argtypes=[w.HDC,w.DWORD]
g.SelectObject.argtypes=[w.HDC,w.HANDLE];g.SelectObject.restype=w.HANDLE
g.GetStockObject.argtypes=[c.c_int];g.GetStockObject.restype=w.HANDLE
g.RoundRect.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int]
g.CreatePen.argtypes=[c.c_int,c.c_int,w.DWORD];g.CreatePen.restype=w.HANDLE
g.GetTextFaceW.argtypes=[w.HDC,c.c_int,w.LPWSTR]

def work_area():
    rect=w.RECT();u.SystemParametersInfoW(0x30,0,c.byref(rect),0);return rect

class MONITORINFO(c.Structure):
    _fields_=[('size',w.DWORD),('monitor',w.RECT),('work',w.RECT),('flags',w.DWORD)]

def monitor_work(rect):
    u.MonitorFromRect.argtypes=[c.POINTER(w.RECT),w.DWORD];u.MonitorFromRect.restype=w.HANDLE
    u.GetMonitorInfoW.argtypes=[w.HANDLE,c.POINTER(MONITORINFO)]
    info=MONITORINFO();info.size=c.sizeof(info)
    return info.work if u.GetMonitorInfoW(u.MonitorFromRect(c.byref(rect),2),c.byref(info)) else work_area()

def fit_scale(dpi,rect):
    return max(.55,min(dpi/96,(rect.right-rect.left-60)/980,(rect.bottom-rect.top-80)/620))

def key_label(value):
    if not value:return '未设置'
    if value.startswith('win-v1:'):
        key=parse_key(value);buf=c.create_unicode_buffer(128)
        if key['scan'] and u.GetKeyNameTextW((key['scan']<<16)|(key['extended']<<24),buf,len(buf)):
            return buf.value
        return 'VK '+format(key['vk'],'02X')+'（无扫描码）'
    if value=='Num_Lock':return 'Num Lock'
    return {'KP_Divide':'小键盘 /','KP_Multiply':'小键盘 *','KP_Decimal':'小键盘 .'}.get(value,'小键盘 '+value[3:] if value.startswith('KP_') else value.upper())

def show_native_window(handle):
    # The launcher hides its console with STARTUPINFO. Windows uses that show
    # state on the first ShowWindow call, so explicitly restore on the second.
    u.ShowWindow(handle,5)
    u.ShowWindow(handle,9)

class Window:
    def __init__(self,service,smoke=None,initial_page='keys'):
        self.service=service;self.state=service.state();self.controls={};self.groups={};self.handlers={};self.options={}
        self.next_id=100;self.busy=False;self.dirty=False;self.result=None;self.smoke=smoke;self.icon_actions={}
        self.key_values={};self.key_styles={};self.capture_name=None;self.hook=None;self.button_info={};self.positions={};self.page='keys';self.preview_dark=False;self.appearance_font='Microsoft YaHei'
        self.dpi=u.GetDpiForSystem();self.scale=fit_scale(self.dpi,work_area());self.font_roles={}
        self.brushes={name:g.CreateSolidBrush(color) for name,color in COLORS.items()}
        self.instance=k.GetModuleHandleW(None)
        self.proc=PROC(self.wndproc)
        wc=WNDCLASS(0,self.proc,0,0,self.instance,None,u.LoadCursorW(None,c.c_void_p(32512)),self.brushes['background'],None,'BihuaNativeSettingsV18')
        if not u.RegisterClassW(c.byref(wc)) and c.get_last_error()!=1410: raise c.WinError(c.get_last_error())
        self.hwnd=u.CreateWindowExW(0,wc.name,'笔画设置',0x00ca0000,100,40,int(980*self.scale),int(620*self.scale),None,None,self.instance,None)
        if not self.hwnd: raise c.WinError(c.get_last_error())
        self.make_fonts()
        self.build();self.load();self.show(initial_page)
        show_native_window(self.hwnd)
        if smoke: u.SetTimer(self.hwnd,1,300,None)

    def send(self,handle,msg,wp=0,lp=0):
        return u.SendMessageW(handle,msg,wp,lp)

    def make_fonts(self):
        self.font=g.CreateFontW(-round(16*self.scale),0,0,0,400,0,0,0,1,0,0,4,0,'Microsoft YaHei UI')
        self.heading_font=g.CreateFontW(-round(24*self.scale),0,0,0,600,0,0,0,1,0,0,4,0,'Microsoft YaHei UI')
        self.line_pen=g.CreatePen(0,max(1,round(self.scale)),COLORS['line'])
        if not self.font or not self.heading_font: raise c.WinError(c.get_last_error())
        u.GetDC.argtypes=[w.HWND];u.GetDC.restype=w.HDC
        u.ReleaseDC.argtypes=[w.HWND,w.HDC]
        dc=u.GetDC(self.hwnd);old=g.SelectObject(dc,self.font)
        face=c.create_unicode_buffer(128);g.GetTextFaceW(dc,len(face),face)
        self.font_face=face.value
        g.SelectObject(dc,old);u.ReleaseDC(self.hwnd,dc)

    def rescale(self,dpi,suggested=None):
        self.dpi=dpi;self.scale=fit_scale(dpi,monitor_work(suggested) if suggested else work_area())
        old=(self.font,self.heading_font,self.line_pen);self.make_fonts()
        for handle,(x,y,width,height) in self.positions.items():
            u.MoveWindow(handle,round(x*self.scale),round(y*self.scale),round(width*self.scale),round(height*self.scale),True)
            self.send(handle,0x30,self.heading_font if self.font_roles.get(handle)=='heading' else self.font,1)
        x=suggested.left if suggested else 100;y=suggested.top if suggested else 40
        u.SetWindowPos(self.hwnd,None,x,y,round(980*self.scale),round(620*self.scale),0x14)
        for obj in old: g.DeleteObject(obj)
        u.InvalidateRect(self.hwnd,None,True)

    def send_text(self,handle,msg,text):
        # Keep UTF-16 storage alive until synchronous SendMessage returns.
        buffer=c.create_unicode_buffer(text)
        return self.send(handle,msg,0,c.addressof(buffer))

    def read_item(self,handle,index):
        length=self.send(handle,0x149,index)
        if length<0: raise ValueError('无法读取下拉选项')
        buffer=c.create_unicode_buffer(length+1)
        self.send(handle,0x148,index,c.addressof(buffer))
        return buffer.value

    def choose_preset(self,device,style):
        self.cancel_capture()
        self.set_value(device+'_style',style)
        self.changed(device+'_style')

    def arm_capture(self,name):
        self.cancel_capture()
        self.capture_name=name
        u.SetWindowTextW(self.controls[name],'请按键…   Esc 取消')
        u.SetWindowTextW(self.status,'请按要绑定的键；Esc 取消')
        self.hook_callback=HOOK(self.keyboard_hook)
        self.hook=u.SetWindowsHookExW(13,self.hook_callback,self.instance,0)
        if not self.hook:
            self.cancel_capture();raise c.WinError(c.get_last_error())

    def cancel_capture(self):
        if self.hook: u.UnhookWindowsHookEx(self.hook);self.hook=None
        name=self.capture_name
        self.capture_name=None
        if name:
            self.set_value(name,self.key_values[name])
            u.SetWindowTextW(self.status,'有未应用的更改' if self.dirty else '已取消录入')

    def keyboard_hook(self,code,wp,lp):
        if code>=0 and self.capture_name and wp in (0x100,0x104):
            key=c.cast(lp,c.POINTER(KEYINFO)).contents
            if self.handle_capture_key(key.vk,u.GetForegroundWindow()==self.hwnd,key.scan,bool(key.flags&1),bool(key.flags&0x10)): return 1
        return u.CallNextHookEx(self.hook,code,wp,lp)

    def handle_capture_key(self,vk,foreground,scan=0,extended=False,injected=False):
        if injected:return False
        if not foreground or vk in (0x09,0x11,0x12,0x5b,0x5c,0xa2,0xa3,0xa4,0xa5):
            self.cancel_capture();return False
        if vk in (0x10,0xa0,0xa1,0x14):
            u.SetWindowTextW(self.status,reserved_reason(physical_key(vk,scan,extended)));return False
        self.capture_vk(vk,scan,extended);return True

    def capture_vk(self,vk,scan=0,extended=False):
        name=self.capture_name
        if not name: return
        if vk==0x1b:
            self.cancel_capture();u.SetWindowTextW(self.status,'已取消录入');return
        value=physical_key(vk,scan,extended)
        try:proposed,cleared=assign_key(self.values(),name,value)
        except ValueError as error:
            u.SetWindowTextW(self.status,str(error)+'；Esc 取消');return
        self.cancel_capture()
        for device in ('letter','keypad'):
            self.set_value(device+'_style',proposed[device+'_style'])
            for action in ACTIONS:self.set_value(device+'_'+action,proposed[device+'_keys'][action])
        self.set_value('symbol_toggle',proposed['symbol_toggle']);self.mark_dirty()
        u.SetWindowTextW(self.status,'已录入 '+key_label(value)+(' · 已清空原绑定' if cleared else '')+' · 保存并应用后生效')

    def paint(self,hwnd):
        paint=PAINT();dc=u.BeginPaint(hwnd,c.byref(paint))
        try:
            rect=w.RECT(0,0,round(210*self.scale),round(620*self.scale))
            u.FillRect(dc,c.byref(rect),self.brushes['sidebar'])
            rect=w.RECT(round(220*self.scale),round(18*self.scale),round(936*self.scale),round(528*self.scale))
            brush=g.SelectObject(dc,self.brushes['card']);pen=g.SelectObject(dc,g.GetStockObject(8))
            g.RoundRect(dc,rect.left,rect.top,rect.right,rect.bottom,round(18*self.scale),round(18*self.scale))
            g.SelectObject(dc,pen);g.SelectObject(dc,brush)
        finally: u.EndPaint(hwnd,c.byref(paint))

    def draw_button(self,item):
        if item.window in self.icon_actions:
            u.FillRect(item.dc,c.byref(item.rect),self.brushes['card'])
            stroke_icons.draw(item.dc,item.rect,self.icon_actions[item.window],COLORS['text'],self.scale)
            return
        if item.window==self.controls.get('appearance_preview'):
            self.draw_preview(item);return
        info=self.button_info.get(item.window,{})
        name=info.get('name') or ''
        is_nav=info.get('page') is None and name!='save'
        active=(is_nav and info.get('text')==dict(PAGES).get(self.page))
        if '_preset_' in name:
            device,style=name.split('_preset_');active=self.key_styles.get(device+'_style')==style
        selected=name=='save' or ('_preset_' in name and active)
        background='green' if selected else 'selected' if active or name==self.capture_name else 'sidebar' if is_nav else 'key'
        dc=item.dc;rect=item.rect
        u.FillRect(dc,c.byref(rect),self.brushes['sidebar' if is_nav else 'card'])
        old_brush=g.SelectObject(dc,self.brushes[background]);old_pen=g.SelectObject(dc,g.GetStockObject(8) if is_nav or selected else self.line_pen)
        g.RoundRect(dc,rect.left,rect.top,rect.right,rect.bottom,round(10*self.scale),round(10*self.scale))
        g.SelectObject(dc,old_pen);g.SelectObject(dc,old_brush)
        g.SetBkMode(dc,1);g.SetTextColor(dc,rgb('#ffffff') if selected else COLORS['green'] if active else COLORS['text'])
        old_font=g.SelectObject(dc,self.font)
        text=c.create_unicode_buffer(u.GetWindowTextLengthW(item.window)+1)
        u.GetWindowTextW(item.window,text,len(text))
        u.DrawTextW(dc,text,-1,c.byref(rect),0x25)
        if item.state&0x10:
            focus=w.RECT(rect.left+4,rect.top+4,rect.right-4,rect.bottom-4);u.DrawFocusRect(dc,c.byref(focus))
        g.SelectObject(dc,old_font)
        if is_nav and active:
            marker=w.RECT(rect.left,rect.top+7,rect.left+3,rect.bottom-7)
            u.FillRect(dc,c.byref(marker),self.brushes['green'])

    def snapshot(self,path):
        """Render only this app's client area for visual regression inspection."""
        u.GetClientRect.argtypes=[w.HWND,c.POINTER(w.RECT)]
        u.GetDC.argtypes=[w.HWND];u.GetDC.restype=w.HDC
        u.ReleaseDC.argtypes=[w.HWND,w.HDC]
        g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
        g.CreateDIBSection.argtypes=[w.HDC,c.c_void_p,w.UINT,c.POINTER(c.c_void_p),w.HANDLE,w.DWORD];g.CreateDIBSection.restype=w.HBITMAP
        g.DeleteDC.argtypes=[w.HDC]
        u.PrintWindow.argtypes=[w.HWND,w.HDC,w.UINT]
        rect=w.RECT();u.GetClientRect(self.hwnd,c.byref(rect));width,height=rect.right,rect.bottom
        source=u.GetDC(self.hwnd);dc=g.CreateCompatibleDC(source)
        info=c.create_string_buffer(struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,0,0,0,0,0))
        pixels=c.c_void_p();bitmap=g.CreateDIBSection(source,info,0,c.byref(pixels),None,0)
        old=g.SelectObject(dc,bitmap)
        try:
            if not u.PrintWindow(self.hwnd,dc,1): raise c.WinError(c.get_last_error())
            raw=c.string_at(pixels,width*height*4)
            rows=[]
            for y in range(height):
                row=raw[y*width*4:(y+1)*width*4]
                rgbrow=bytearray(width*3);rgbrow[0::3]=row[2::4];rgbrow[1::3]=row[1::4];rgbrow[2::3]=row[0::4]
                rows.append(b'\0'+rgbrow)
            def chunk(kind,data): return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
            path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))
        finally:
            g.SelectObject(dc,old);g.DeleteObject(bitmap);g.DeleteDC(dc);u.ReleaseDC(self.hwnd,source)

    def control(self,kind,text,x,y,width,height,name=None,page=None,style=0):
        ident=self.next_id;self.next_id+=1
        handle=u.CreateWindowExW(0,kind,text,0x50000000|style,round(x*self.scale),round(y*self.scale),round(width*self.scale),round(height*self.scale),self.hwnd,ident,self.instance,None)
        if not handle: raise c.WinError(c.get_last_error())
        self.positions[handle]=(x,y,width,height)
        self.send(handle,0x30,self.font,1)
        if name: self.controls[name]=handle
        if page: self.groups.setdefault(page,[]).append(handle)
        return handle,ident

    def label(self,text,x,y,width=670,height=28,page=None):
        handle=self.control('STATIC',text,x,y,width,height,page=page)[0]
        if y in (24,26,30,32):
            self.font_roles[handle]='heading';self.send(handle,0x30,self.heading_font,1)
        return handle

    def button(self,text,x,y,width,callback,page=None,name=None):
        handle,ident=self.control('BUTTON',text,x,y,width,34,name,page,0x10000|11)
        self.button_info[handle]={'name':name,'page':page,'text':text}
        self.handlers[ident]=lambda _:callback()
        return handle

    def combo(self,name,values,x,y,width=180,page='keys'):
        handle,ident=self.control('COMBOBOX','',x,y,width,390,name,page,0x10000|0x200000|3)
        self.options[name]=values
        for value,label in values:
            self.send_text(handle,0x143,label)
        self.handlers[ident]=lambda notification:self.changed(name) if notification==1 else None

    def checkbox(self,name,text,y,page,x=230,width=675):
        handle,ident=self.control('BUTTON',text,x,y,width,33,name,page,0x10000|3)
        self.handlers[ident]=lambda _:self.changed(name)

    def edit(self,name,x,y,width,page):
        handle,ident=self.control('EDIT','',x,y,width,30,name,page,0x10000|0x800000|0x80)
        self.handlers[ident]=lambda notification:self.mark_dirty() if notification==0x300 and not name.startswith('stroke_') else None

    def build(self):
        self.label('笔画',28,30,160,36)
        self.label('输入法偏好设置',28,76,160,26)
        for i,(page,title) in enumerate(PAGES):
            self.button(title,24,120+i*48,170,lambda p=page:self.show(p))
        self.label('键盘与按键',246,32,height=38,page='keys')
        self.label('鼠标面板',246,32,height=38,page='mouse')
        self.checkbox('mouse_input','开启常驻鼠标面板',100,'mouse',246,600)
        self.checkbox('stroke_info','长按候选显示笔画',150,'mouse',246,600)
        self.checkbox('copy_stroke','复制单字时显示自定义笔顺入口',200,'mouse',246,600)
        self.checkbox('selection_stroke','选中单字时显示入口（支持 TSF 的文本控件）',250,'mouse',246,650)
        self.label('Shift 切换中英文；英文状态下 Caps Lock 切换 a / A。',246,322,650,page='mouse')
        self.label('Enter 使用软件原有功能；失去输入焦点时保留极简栏。',246,364,650,page='mouse')
        self.label('更新输入法后，已打开的软件需重新打开后生效。',246,448,650,page='mouse')
        self.label('点击键帽修改按键',635,78,280,page='keys')
        self.label('笔画 / 功能',238,124,140,page='keys')
        for device,x,title,presets in [('letter',385,'字母键',LETTER),('keypad',660,'数字小键盘',KEYPAD)]:
            self.controls[device+'_style']=self.label(title,x,124,255,page='keys')
            for i,(style,keys) in enumerate(presets.items()):
                caption=''.join(keys[a].replace('KP_','').upper() for a in ACTIONS[:6])
                self.button(caption,x+i*122,158,115,lambda d=device,t=style:self.choose_preset(d,t),'keys',device+'_preset_'+style)
        labels=['横','竖','撇','点 / 捺','折','通配符','分词']
        for i,(action,label) in enumerate(zip(ACTIONS,labels)):
            y=208+i*40
            handle=self.control('STATIC',label,246,y,32,34,page='keys',style=13)[0]
            self.icon_actions[handle]=action
            self.label(label,292,y+5,84,page='keys')
            for device,x in [('letter',385),('keypad',660)]:
                name=device+'_'+action
                self.key_values[name]=''
                self.button('',x,y,236,lambda n=name:self.arm_capture(n),'keys',name)
        self.label('符号入口',292,501,84,page='keys')
        self.key_values['symbol_toggle']=''
        self.button('',385,496,236,lambda:self.arm_capture('symbol_toggle'),'keys','symbol_toggle')
        self.button('停用',660,496,115,self.clear_symbol_key,'keys')
        self.label('候选与翻页',246,32,height=38,page='paging')
        self.checkbox('arrow_navigation','方向键选字 · ↓ 展开五行，首行 ↑ 收起',100,'paging',246,650)
        self.label('左右移动；空格 / 小键盘 0 确认。',246,142,650,page='paging')
        self.label('翻页快捷键',246,202,page='paging')
        for i,(name,title) in enumerate([('page_minus','减号 / 等号　− / ='),('page_brackets','左右中括号　[ / ]'),('page_comma','逗号 / 句号　, / .'),('page_tab','Shift+Tab / Tab（键盘模式）'),('page_keypad','小键盘　− 上一页 / + 下一页')]):
            self.checkbox(name,title,246+i*46,'paging',246,650)
        self.label('本地联想',246,32,height=38,page='prediction')
        self.checkbox('association','开启本地联想',100,'prediction')
        self.label('最多展示页数（每页 9 个）',230,168,350,page='prediction')
        self.combo('prediction_pages',[(i,str(i)+' 页') for i in range(1,6)],630,160,page='prediction')
        self.label('外观',246,32,height=38,page='appearance')
        self.label('配色方案',246,90,280,page='appearance')
        self.combo('color_scheme',[],246,122,280,'appearance')
        self.label('系统深色模式',246,170,280,page='appearance')
        self.combo('dark_scheme',[],246,202,280,'appearance')
        self.label('字体',246,250,280,page='appearance')
        self.button('',246,282,280,self.choose_font,'appearance','font_face')
        self.label('字号',246,338,70,page='appearance')
        self.combo('font_size',[(i,str(i)) for i in range(8,73)],322,330,100,'appearance')
        self.checkbox('horizontal','候选横排',380,'appearance',246,280)
        self.label('圆角',246,438,60,page='appearance')
        self.combo('corner_radius',[(i,str(i)) for i in range(31)],306,430,70,'appearance')
        self.label('间距',404,438,60,page='appearance')
        self.combo('candidate_spacing',[(i,str(i)) for i in range(41)],464,430,70,'appearance')
        self.label('预览',580,90,280,page='appearance')
        self.control('STATIC','',570,132,340,300,'appearance_preview','appearance',13)
        self.button('预览深色配色',610,448,240,self.toggle_preview,'appearance','preview_mode')
        self.label('个人词库',246,32,height=38,page='words')
        self.label('词语（2–4 字）',230,85,200,page='words');self.edit('word',230,115,220,'words')
        self.label('标准编码（留空自动填写）',480,85,400,page='words');self.edit('codes',480,115,400,'words')
        self.button('添加 / 更新',230,165,160,self.add_word,'words')
        self.button('删除选中词',410,165,160,self.delete_word,'words')
        self.button('导入 TSV',590,165,130,lambda:self.file_words(False),'words')
        self.button('导出 TSV',740,165,140,lambda:self.file_words(True),'words')
        handle,ident=self.control('LISTBOX','',230,220,650,280,'word_list','words',0x800000|0x200000|0x10000|1)
        self.handlers[ident]=lambda notification:self.select_word() if notification==1 else None
        self.label('个人笔顺',246,32,height=38,page='strokes')
        self.label('汉字',246,88,100,page='strokes');self.edit('stroke_char',246,120,100,'strokes')
        self.label('习惯笔顺（12345）',370,88,460,page='strokes');self.edit('stroke_code',370,120,510,'strokes')
        self.button('保存笔顺',246,166,150,self.upsert_stroke,'strokes','stroke_save')
        self.button('删除选中',410,166,140,self.delete_stroke,'strokes')
        self.button('导入',670,166,98,lambda:self.file_strokes(False),'strokes')
        self.button('导出',782,166,98,lambda:self.file_strokes(True),'strokes')
        self.label('汉字',246,218,64,page='strokes')
        self.label('个人笔顺',314,218,180,page='strokes')
        self.label('系统笔顺（同时保留）',496,218,360,page='strokes')
        handle,ident=self.control('LISTBOX','',246,250,634,238,'stroke_list','strokes',0x800000|0x200000|0x10000|0x80|1)
        tabs=(c.c_int*2)(32,120);self.send(handle,0x192,2,c.addressof(tabs))
        self.handlers[ident]=lambda notification:self.select_stroke() if notification==1 else None
        self.label('保存立即生效；系统笔顺始终保留。',246,500,410,page='strokes')
        self.button('恢复上次保存',706,494,174,self.restore_strokes,'strokes')
        self.status=self.label('',230,540,510,28)
        self.button('保存并应用',755,533,155,self.save,name='save')

    def value(self,name):
        if name=='font_face':return self.appearance_font
        if name in self.key_values: return self.key_values[name]
        if name in ('letter_style','keypad_style'): return self.key_styles.get(name)
        index=self.send(self.controls[name],0x147)
        return self.options[name][index][0] if 0<=index<len(self.options[name]) else None

    def set_value(self,name,value):
        if name=='font_face':
            self.appearance_font=value;u.SetWindowTextW(self.controls[name],value);return
        if name in self.key_values:
            self.key_values[name]=value
            u.SetWindowTextW(self.controls[name],key_label(value))
            u.InvalidateRect(self.controls[name],None,True)
            return
        if name in ('letter_style','keypad_style'):
            self.key_styles[name]=value
            u.SetWindowTextW(self.controls[name],('字母键' if name=='letter_style' else '数字小键盘')+(' · 自定义' if value=='custom' else ''))
            for handle in self.button_info: u.InvalidateRect(handle,None,True)
            return
        values=[x[0] for x in self.options[name]]
        if value not in values:
            if name in ('corner_radius','candidate_spacing'):
                self.options[name].append((value,str(value)));self.send_text(self.controls[name],0x143,str(value));values.append(value)
            else:raise ValueError('未支持的设置值：'+str(value))
        self.send(self.controls[name],0x14e,values.index(value))

    def text(self,name):
        handle=self.controls[name];buf=c.create_unicode_buffer(u.GetWindowTextLengthW(handle)+1)
        u.GetWindowTextW(handle,buf,len(buf));return buf.value

    def load(self):
        self.state=self.service.state();s=self.state['settings']
        for name in ('color_scheme','dark_scheme'):
            self.options[name]=([('','与上面相同')] if name=='dark_scheme' else [])+[(row['id'],row['name']) for row in self.state['appearance']['schemes']]
            self.send(self.controls[name],0x14b)
            for _,label in self.options[name]:self.send_text(self.controls[name],0x143,label)
        for name in panel.BOOLS: self.send(self.controls[name],0xf1,1 if s[name] else 0)
        for name in ('prediction_pages','font_size','letter_style','keypad_style',*appearance.FIELDS): self.set_value(name,s[name])
        for device in ('letter','keypad'):
            for action in ACTIONS: self.set_value(device+'_'+action,s[device+'_keys'][action])
        self.set_value('symbol_toggle',s['symbol_toggle'])
        self.refresh_words();self.refresh_strokes();self.dirty=False
        u.SetWindowTextW(self.status,'已读取当前设置')

    def values(self):
        s={name:bool(self.send(self.controls[name],0xf0)) for name in panel.BOOLS}
        for name in ('prediction_pages','font_size','letter_style','keypad_style',*appearance.FIELDS): s[name]=self.value(name)
        for device in ('letter','keypad'): s[device+'_keys']={a:self.value(device+'_'+a) for a in ACTIONS}
        s['symbol_toggle']=self.value('symbol_toggle')
        return s

    def clear_symbol_key(self):
        self.set_value('symbol_toggle','');self.mark_dirty()

    def mark_dirty(self):
        self.dirty=True;u.SetWindowTextW(self.status,'有未应用的更改')
        if self.controls.get('appearance_preview'):u.InvalidateRect(self.controls['appearance_preview'],None,True)

    def choose_font(self):
        chosen=font_dialog(self.hwnd,self.appearance_font,self.value('font_size'),self.dpi)
        if chosen:
            self.set_value('font_face',chosen[0]);self.set_value('font_size',chosen[1]);self.mark_dirty()

    def toggle_preview(self):
        self.preview_dark=not self.preview_dark
        u.SetWindowTextW(self.controls['preview_mode'],'预览浅色配色' if self.preview_dark else '预览深色配色')
        u.InvalidateRect(self.controls['appearance_preview'],None,True)

    def draw_preview(self,item):
        rows=self.state.get('appearance',{}).get('schemes',[])
        identity=(self.value('dark_scheme') if self.preview_dark else '') or self.value('color_scheme')
        colors=next((row['colors'] for row in rows if row['id']==identity),appearance.palette({}))
        dc=item.dc;scale=self.scale
        brushes={key:g.CreateSolidBrush(rgb(value)) for key,value in colors.items()}
        point=min(30,self.value('font_size') or 18);height=round(point*4/3*scale)
        font=g.CreateFontW(-height,0,0,0,400,0,0,0,1,0,0,4,0,self.appearance_font.split(',')[0].strip())
        pen=g.CreatePen(0,max(1,round(scale)),rgb(colors['border']))
        oldfont=g.SelectObject(dc,font);oldpen=g.SelectObject(dc,pen);oldbrush=g.SelectObject(dc,brushes['background'])
        try:
            u.FillRect(dc,c.byref(item.rect),self.brushes['card'])
            radius=round(min(30,self.value('corner_radius') or 0)*2*scale)
            spacing=round(min(25,self.value('candidate_spacing') or 0)*scale)
            row_height=height+round(14*scale)
            horizontal=bool(self.send(self.controls['horizontal'],0xf0))
            columns=max(1,int((item.rect.right-round(28*scale)+spacing)//(round(height*3.25+16*scale)+spacing))) if horizontal else 1
            rows=(3+columns-1)//columns
            panel_bottom=min(item.rect.bottom-1,round(90*scale)+rows*row_height+(rows-1)*spacing)
            g.RoundRect(dc,item.rect.left+1,item.rect.top+1,item.rect.right-1,panel_bottom,radius,radius)
            g.SetBkMode(dc,1);g.SetTextColor(dc,rgb(colors['text']))
            rect=w.RECT(round(18*scale),round(14*scale),item.rect.right-round(18*scale),round(58*scale))
            u.DrawTextW(dc,'一丨丿丶𠃌',-1,c.byref(rect),0x24)
            x=round(14*scale);y=round(76*scale)
            for i,word in enumerate(('中国','中文','中间')):
                width=round(height*3.25+16*scale) if horizontal else item.rect.right-round(28*scale)
                if horizontal and x+width>item.rect.right-round(10*scale) and i:
                    x=round(14*scale);y+=row_height+spacing
                cell=w.RECT(x,y,min(x+width,item.rect.right-round(8*scale)),y+row_height)
                selected=i==0
                if selected:
                    g.SelectObject(dc,brushes['selected_background']);g.SelectObject(dc,g.GetStockObject(8))
                    g.RoundRect(dc,cell.left,cell.top,cell.right,cell.bottom,radius,radius)
                label=w.RECT(cell.left+round(8*scale),cell.top,cell.left+height,cell.bottom)
                g.SetTextColor(dc,rgb(colors['selected_label' if selected else 'label']))
                u.DrawTextW(dc,str(i+1),-1,c.byref(label),0x24)
                text=w.RECT(cell.left+height,cell.top,cell.right-round(6*scale),cell.bottom)
                g.SetTextColor(dc,rgb(colors['selected_text' if selected else 'text']))
                u.DrawTextW(dc,word,-1,c.byref(text),0x8024)
                if horizontal:x+=width+spacing
                else:y+=row_height+spacing
        finally:
            g.SelectObject(dc,oldfont);g.SelectObject(dc,oldpen);g.SelectObject(dc,oldbrush)
            g.DeleteObject(font);g.DeleteObject(pen)
            for brush in brushes.values():g.DeleteObject(brush)

    def changed(self,name):
        for device,presets in [('letter',LETTER),('keypad',KEYPAD)]:
            if name==device+'_style' and self.value(name)!='custom':
                style=self.value(name);proposed=self.values()
                for action,value in presets[style].items():proposed,_=assign_key(proposed,device+'_'+action,value)
                proposed[device+'_style']=style
                for group in ('letter','keypad'):
                    self.set_value(group+'_style',proposed[group+'_style'])
                    for action in ACTIONS:self.set_value(group+'_'+action,proposed[group+'_keys'][action])
                self.set_value('symbol_toggle',proposed['symbol_toggle'])
            elif name.startswith(device+'_') and name!=device+'_style': self.set_value(device+'_style','custom')
        self.mark_dirty()

    def show(self,page):
        self.cancel_capture()
        self.page=page
        if page=='strokes':self.refresh_strokes()
        for handle in self.button_info: u.InvalidateRect(handle,None,True)
        for key,handles in self.groups.items():
            for handle in handles: u.ShowWindow(handle,5 if key==page else 0)
        u.ShowWindow(self.controls['save'],0 if page=='strokes' else 5)

    def save(self):
        if self.busy: return
        self.cancel_capture()
        try:
            preview=self.service.preview(self.values())
            if u.MessageBoxW(self.hwnd,'应用当前按键、联想及外观设置？\n应用时输入法会短暂重新部署。','保存并应用',0x24)!=6: return
            self.busy=True;u.EnableWindow(self.controls['save'],False)
            u.SetWindowTextW(self.status,'正在保存并应用…')
            def apply():
                try: self.result=(True,self.service.apply(preview['preview_id'])['message'])
                except Exception as error: self.result=(False,str(error))
                u.PostMessageW(self.hwnd,0x8001,0,0)
            threading.Thread(target=apply,daemon=True).start()
        except Exception as error: self.error(error)

    def error(self,error): u.MessageBoxW(self.hwnd,str(error),'笔画设置',0x10)

    def refresh_words(self):
        self.state['words']=self.service.state()['words']
        handle=self.controls['word_list'];self.send(handle,0x184)
        for row in self.state['words']:
            self.send_text(handle,0x180,row['text']+'    '+row['digits'])

    def select_word(self):
        index=self.send(self.controls['word_list'],0x188)
        if 0<=index<len(self.state['words']):
            row=self.state['words'][index];u.SetWindowTextW(self.controls['word'],row['text']);u.SetWindowTextW(self.controls['codes'],row['digits'])

    def add_word(self):
        self.service.word_action('add',{'text':self.text('word').strip(),'codes':self.text('codes').strip()})
        self.refresh_words();self.mark_dirty()

    def delete_word(self):
        index=self.send(self.controls['word_list'],0x188)
        if 0<=index<len(self.state['words']):
            self.service.word_action('delete',{'text':self.state['words'][index]['text']});self.refresh_words();self.mark_dirty()

    def file_words(self,save):
        path=file_dialog(self.hwnd,save)
        if not path: return
        if save:
            panel.atomic_write(Path(path),panel.read(self.service.directory/'bihua_personal_phrases.tsv'))
        else:
            if Path(path).stat().st_size>2*1024*1024: raise ValueError('词库文件请小于 2 MB')
            self.service.word_action('import',{'content':Path(path).read_text(encoding='utf-8-sig')});self.refresh_words();self.mark_dirty()

    def refresh_strokes(self):
        self.stroke_rows=self.service.stroke_action('list')['rows']
        self.send(self.controls['stroke_list'],0x184)
        for row in self.stroke_rows:
            short=lambda text:text if len(text)<=22 else text[:21]+'…'
            self.send_text(self.controls['stroke_list'],0x180,row['text']+'\t'+short(row['digits'])+'\t'+short(row['system_digits']))

    def select_stroke(self):
        index=self.send(self.controls['stroke_list'],0x188)
        if 0<=index<len(self.stroke_rows):
            row=self.stroke_rows[index]
            u.SetWindowTextW(self.controls['stroke_char'],row['text']);u.SetWindowTextW(self.controls['stroke_code'],row['digits'])
            u.SetWindowTextW(self.controls['stroke_save'],'覆盖保存')

    def upsert_stroke(self):
        result=self.service.stroke_action('upsert',{'text':self.text('stroke_char'),'code':self.text('stroke_code')})
        self.refresh_strokes();u.SetWindowTextW(self.status,'' if result.get('skipped_system') else '个人笔顺已保存，立即生效')

    def delete_stroke(self):
        index=self.send(self.controls['stroke_list'],0x188)
        if 0<=index<len(self.stroke_rows):
            self.service.stroke_action('delete',{'text':self.stroke_rows[index]['text']});self.refresh_strokes()
            u.SetWindowTextW(self.status,'个人笔顺已删除，系统笔顺保留')

    def restore_strokes(self):
        self.service.stroke_action('restore-previous');self.refresh_strokes()
        u.SetWindowTextW(self.status,'已恢复上次保存，立即生效')

    def file_strokes(self,save):
        path=file_dialog(self.hwnd,save)
        if not path:return
        if save:
            import personal_strokes
            result=self.service.stroke_action('list')
            panel.atomic_write(Path(path),personal_strokes.render(max(1,result['revision']),{r['text']:r['code'] for r in result['rows']}))
        else:
            if Path(path).stat().st_size>4*1024*1024:raise ValueError('个人笔顺文件请小于 4 MB')
            self.service.stroke_action('import',{'content':Path(path).read_text(encoding='utf-8-sig')});self.refresh_strokes()
        u.SetWindowTextW(self.status,'个人笔顺已导出' if save else '个人笔顺已导入，立即生效')

    def wndproc(self,hwnd,msg,wp,lp):
        try:
            if msg==0x8002 and int(wp) in range(len(PAGES)):
                self.show(PAGES[int(wp)][0]);show_native_window(hwnd);u.SetForegroundWindow(hwnd);return 0
            if msg==0x2b:
                self.draw_button(c.cast(lp,c.POINTER(DRAWITEM)).contents);return 1
            if msg==0x2e0 and hasattr(self,'font'):
                self.rescale(wp&0xffff,c.cast(lp,c.POINTER(w.RECT)).contents);return 0
            if msg==0xf:
                self.paint(hwnd);return 0
            if msg in (0x138,0x135,0x133):
                g.SetBkMode(wp,1);g.SetTextColor(wp,COLORS['text'])
                return self.brushes['sidebar' if self.positions.get(lp,(230,))[0]<210 else 'card']
            if msg==0x6 and (wp&0xffff)==0:
                self.cancel_capture()
            if msg==0x111:
                callback=self.handlers.get(wp&0xffff)
                if callback and not self.busy: callback((wp>>16)&0xffff)
                return 0
            if msg==0x8001:
                self.busy=False;u.EnableWindow(self.controls['save'],True)
                ok,message=self.result
                if ok: self.load()
                u.SetWindowTextW(self.status,message)
                if not ok: self.error(message)
                return 0
            if msg==0x10:
                self.cancel_capture()
                if self.busy: return 0
                if self.dirty and u.MessageBoxW(hwnd,'还有未应用的更改，确定关闭？','笔画设置',0x24)!=6: return 0
                u.DestroyWindow(hwnd);return 0
            if msg==0x113 and self.smoke:
                assert len(self.controls)>=30
                assert self.values()==self.state['settings']
                for name,rows in self.options.items():
                    for index,(_,label) in enumerate(rows):
                        assert self.read_item(self.controls[name],index)==label,(name,index)
                self.set_value('letter_style','asdfgt');self.changed('letter_style')
                self.set_value('keypad_style','789456');self.changed('keypad_style')
                self.service.preview(self.values())
                self.arm_capture('letter_h')
                assert self.hook
                def capture_event(vk):
                    assert self.handle_capture_key(vk,True)
                capture_event(ord('S'))
                assert not self.capture_name and self.value('letter_h')==physical_key(ord('S'),0)
                assert self.value('letter_s')=='','old same-group key was not cleared'
                self.arm_capture('letter_h')
                capture_event(ord('Q'))
                assert self.value('letter_style')=='custom'
                expected_q=physical_key(ord('Q'),0)
                assert self.value('letter_h')==expected_q and not self.hook
                self.arm_capture('keypad_h')
                self.capture_vk(ord('1'))
                assert self.value('keypad_h')==physical_key(ord('1'),0) and not self.hook
                self.arm_capture('keypad_h');self.capture_vk(0xff,0x63,False)
                assert self.value('keypad_h')==physical_key(0xff,0x63) and not self.hook
                self.arm_capture('keypad_h');self.capture_vk(ord('Q'))
                assert not self.capture_name and self.value('letter_h')=='','cross-group old binding was not cleared'
                assert self.value('keypad_h')==expected_q
                self.arm_capture('keypad_h')
                self.capture_vk(0xff,0x63,False)
                self.arm_capture('keypad_separator');self.capture_vk(0x2e,0x53,False)
                assert self.value('keypad_separator')==physical_key(0x2e,0x53) and not self.hook
                assert physical_vk(0x2e,0x53,True)==0x2e
                self.arm_capture('letter_h');self.capture_vk(0x1b)
                assert not self.hook and self.value('letter_h')==''
                self.arm_capture('letter_h');self.wndproc(hwnd,0x6,0,0)
                assert not self.hook and not self.capture_name
                self.arm_capture('letter_h')
                assert not self.handle_capture_key(ord('W'),False)
                assert not self.hook and self.value('letter_h')==''
                self.service.preview(self.values())
                self.load();self.show('keys')
                initial=self.values();actual_dpi=self.dpi
                self.show('mouse')
                for name,page in (('stroke_info','mouse'),('arrow_navigation','paging')):
                    self.show(page)
                    assert u.IsWindowVisible(self.controls[name])
                    self.send(self.controls[name],0xf1,0)
                assert not self.values()['stroke_info'] and not self.values()['arrow_navigation']
                self.service.preview(self.values())
                self.load();self.show('mouse')
                self.snapshot(self.smoke.with_name(self.smoke.stem+'-mouse.png'))
                self.show('paging');self.snapshot(self.smoke.with_name(self.smoke.stem+'-paging.png'))
                for page,_ in PAGES:
                    self.wndproc(hwnd,0x8002,[p for p,_ in PAGES].index(page),0)
                    assert self.page==page
                    for group,handles in self.groups.items():
                        assert all(bool(u.IsWindowVisible(handle))==(group==page) for handle in handles),group
                if self.service.directory.resolve().is_relative_to((panel.ROOT/'.verification').resolve()) or self.service.directory.resolve()==(panel.ROOT/'.validation-user').resolve():
                    self.show('strokes')
                    u.SetWindowTextW(self.controls['stroke_char'],'鼠');u.SetWindowTextW(self.controls['stroke_code'],'12345')
                    self.upsert_stroke();assert any(r['text']=='鼠' and r['digits']=='12345' for r in self.stroke_rows)
                    self.send(self.controls['stroke_list'],0x186,next(i for i,r in enumerate(self.stroke_rows) if r['text']=='鼠'))
                    self.select_stroke();assert self.text('stroke_code')=='12345'
                    self.snapshot(self.smoke.with_name(self.smoke.stem+'-strokes.png'))
                    self.delete_stroke();assert not any(r['text']=='鼠' for r in self.stroke_rows)
                for name,value in [('color_scheme',self.state['appearance']['schemes'][-1]['id']),('font_face','Microsoft YaHei UI'),('corner_radius',12),('candidate_spacing',9)]:
                    self.set_value(name,value)
                self.changed('color_scheme');self.service.preview(self.values())
                self.show('appearance');self.toggle_preview();self.snapshot(self.smoke.with_name(self.smoke.stem+'-dark-preview.png'));self.toggle_preview()
                self.load()
                assert self.values()==initial
                for dpi in (96,120,144,192):
                    self.rescale(dpi)
                    assert self.values()==initial
                    assert all(round((x+width)*self.scale)<=round(980*self.scale) for x,y,width,height in self.positions.values())
                self.rescale(actual_dpi)
                self.show('keys');self.snapshot(self.smoke.with_name(self.smoke.stem+'-keys.png'))
                assert set(self.icon_actions.values())==set(ACTIONS)
                self.snapshot(self.smoke.with_suffix('.png'))
                for page in ('prediction','appearance'):
                    self.show(page);self.snapshot(self.smoke.with_name(self.smoke.stem+'-'+page+'.png'))
                aware=bool(u.AreDpiAwarenessContextsEqual(u.GetWindowDpiAwarenessContext(self.hwnd),c.c_void_p(-4)))
                assert aware
                self.smoke.write_text(json.dumps({'result':'PASS','native_controls':len(self.controls),'settings_categories':dict(PAGES),'all_category_visibility_and_navigation':True,'mouse_interaction_switches_visible_and_previewed':True,'unicode_item_readback':True,'key_capture_duplicate_reserved_device_escape_focus':True,'preset_custom_preview':True,'appearance_theme_font_layout':True,'appearance_schemes':len(self.state['appearance']['schemes']),'writes_config':False,'dpi':self.dpi,'scale':self.scale,'font_face':self.font_face,'per_monitor_v2':aware}),encoding='utf-8')
                self.dirty=False;u.DestroyWindow(hwnd);return 0
            if msg==2:
                self.cancel_capture();u.PostQuitMessage(0);return 0
        except Exception as error:
            if self.smoke:
                self.smoke_failed=__import__('traceback').format_exc()
                self.smoke.write_text(json.dumps({'result':'FAIL','error':self.smoke_failed}),encoding='utf-8');u.DestroyWindow(hwnd)
            else: self.error(error)
        return u.DefWindowProcW(hwnd,msg,wp,lp)

    def run(self):
        msg=w.MSG()
        while u.GetMessageW(c.byref(msg),None,0,0)>0:
            if not u.IsDialogMessageW(self.hwnd,c.byref(msg)):
                u.TranslateMessage(c.byref(msg));u.DispatchMessageW(c.byref(msg))
        g.DeleteObject(self.font);g.DeleteObject(self.heading_font);g.DeleteObject(self.line_pen)
        for brush in self.brushes.values(): g.DeleteObject(brush)
        if getattr(self,'smoke_failed',None): raise RuntimeError(self.smoke_failed)

class OPENFILENAME(c.Structure):
    _fields_=[('size',w.DWORD),('owner',w.HWND),('instance',w.HINSTANCE),('filter',w.LPCWSTR),
              ('custom_filter',w.LPWSTR),('max_custom',w.DWORD),('filter_index',w.DWORD),
              ('file',w.LPWSTR),('max_file',w.DWORD),('title_buffer',w.LPWSTR),('max_title',w.DWORD),
              ('initial_dir',w.LPCWSTR),('title',w.LPCWSTR),('flags',w.DWORD),('file_offset',w.WORD),
              ('extension_offset',w.WORD),('extension',w.LPCWSTR),('data',w.LPARAM),('hook',c.c_void_p),
              ('template',w.LPCWSTR),('reserved',c.c_void_p),('reserved_size',w.DWORD),('flags_ex',w.DWORD)]

def file_dialog(owner,save):
    filename=c.create_unicode_buffer('笔画个人词库.tsv' if save else '',32768)
    ofn=OPENFILENAME();ofn.size=c.sizeof(ofn);ofn.owner=owner
    ofn.filter='TSV 词库\0*.tsv;*.txt\0所有文件\0*.*\0\0';ofn.file=c.cast(filename,w.LPWSTR);ofn.max_file=len(filename)
    ofn.flags=0x80000|0x8|(0x2 if save else 0x1000);ofn.extension='tsv'
    dialog=c.WinDLL('comdlg32').GetSaveFileNameW if save else c.WinDLL('comdlg32').GetOpenFileNameW
    return filename.value if dialog(c.byref(ofn)) else None

class LOGFONT(c.Structure):
    _fields_=[('height',w.LONG),('width',w.LONG),('escapement',w.LONG),('orientation',w.LONG),('weight',w.LONG),
              ('italic',w.BYTE),('underline',w.BYTE),('strikeout',w.BYTE),('charset',w.BYTE),('outprecision',w.BYTE),
              ('clipprecision',w.BYTE),('quality',w.BYTE),('pitch',w.BYTE),('face',w.WCHAR*32)]
class CHOOSEFONT(c.Structure):
    _fields_=[('size',w.DWORD),('owner',w.HWND),('dc',w.HDC),('font',c.POINTER(LOGFONT)),('points',c.c_int),
              ('flags',w.DWORD),('color',w.DWORD),('data',w.LPARAM),('hook',c.c_void_p),('template',w.LPCWSTR),
              ('instance',w.HINSTANCE),('style',w.LPWSTR),('type',w.WORD),('minimum',c.c_int),('maximum',c.c_int)]

def font_dialog(owner,face,size,dpi):
    font=LOGFONT();font.height=-round(size*dpi/72);font.charset=1;font.face=face.split(',')[0].strip()[:31]
    chooser=CHOOSEFONT();chooser.size=c.sizeof(chooser);chooser.owner=owner;chooser.font=c.pointer(font)
    chooser.points=size*10;chooser.flags=0x1|0x40|0x2000|0x10000|0x100000;chooser.minimum=8;chooser.maximum=72
    dialog=c.WinDLL('comdlg32').ChooseFontW;dialog.argtypes=[c.POINTER(CHOOSEFONT)];dialog.restype=w.BOOL
    return (font.face,max(8,min(72,round(chooser.points/10)))) if dialog(c.byref(chooser)) else None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rime-dir',type=Path,default=Path(os.environ['APPDATA'])/'Rime')
    parser.add_argument('--smoke',type=Path)
    parser.add_argument('--page',choices=[page for page,_ in PAGES],default='keys')
    args=parser.parse_args()
    previous=u.FindWindowW('BihuaNativeSettingsV18',None)
    if previous and not args.smoke:
        u.SendMessageW(previous,0x8002,[page for page,_ in PAGES].index(args.page),0);return
    Window(panel.Settings(args.rime_dir),args.smoke,args.page).run()

if __name__=='__main__':
    try: main()
    except Exception as error:
        if '--smoke' in __import__('sys').argv:
            args=__import__('sys').argv
            Path(args[args.index('--smoke')+1]).write_text(json.dumps({'result':'FAIL','error':str(error)}),encoding='utf-8')
        else: u.MessageBoxW(None,str(error),'无法打开笔画设置',0x10)
        raise
