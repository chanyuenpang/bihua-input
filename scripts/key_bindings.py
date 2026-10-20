"""Validated physical keys; dictionaries/learning always use canonical strokes."""
import re
import os
import copy

ACTIONS = ('h', 's', 'p', 'n', 'z', 'wildcard', 'separator')
LETTER = {'standard': dict(zip(ACTIONS, ('h','s','p','d','z','t','f'))),
          'asdfgt': dict(zip(ACTIONS, ('a','s','d','f','g','t','r')))}
KEYPAD = {'standard': dict(zip(ACTIONS, ('KP_1','KP_2','KP_3','KP_4','KP_5','KP_6','KP_Decimal'))),
          '789456': dict(zip(ACTIONS, ('KP_7','KP_8','KP_9','KP_4','KP_5','KP_6','KP_Decimal')))}
FIELDS = ('letter_style','keypad_style','letter_keys','keypad_keys','symbol_toggle')

def physical_key(vk,scan,extended=False):
    """Lossless Windows identity. Display labels never become key identities."""
    if type(vk) is not int or type(scan) is not int or not 0<=vk<=255 or not 0<=scan<=255 or not (vk or scan):
        raise ValueError('没有收到有效的 Windows 按键事件')
    return f'win-v1:{scan:02x}:{int(bool(extended))}:{vk:02x}'

def parse_key(value):
    if not isinstance(value,str):raise ValueError('按键必须为字符串')
    match=re.fullmatch(r'win-v1:([0-9a-f]{2}):([01]):([0-9a-f]{2})',value)
    if match:
        scan,extended,vk=int(match[1],16),int(match[2]),int(match[3],16)
        if not (scan or vk):raise ValueError('按键身份为空')
        return {'kind':'physical','scan':scan,'extended':extended,'vk':vk}
    # Old configurations have semantic Rime names, without a recorded scan.
    # Keep them as semantic keys; never guess and rewrite their physical scan.
    legacy={'KP_Divide':0x6f,'KP_Multiply':0x6a,'KP_Decimal':0x6e,'KP_Add':0x6b,'KP_Subtract':0x6d,'Num_Lock':0x90,
            'space':0x20,'Return':0x0d,'KP_Enter':0x0d,'Escape':0x1b,'BackSpace':0x08,'Tab':0x09,
            'Left':0x25,'Up':0x26,'Right':0x27,'Down':0x28}
    if re.fullmatch('[a-z]',value):vk=ord(value.upper())
    elif re.fullmatch('KP_[0-9]',value):vk=0x60+int(value[-1])
    elif value in legacy:vk=legacy[value]
    elif re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-4])',value):vk=0x70+int(value[1:])-1
    else:raise ValueError('无法解析按键，请点击键帽重新按键录入')
    return {'kind':'legacy','name':value,'vk':vk}

def reserved_reason(value):
    spec=parse_key(value)
    vk=resolved_vk(spec)
    names={0x10:'Shift 用于切换中英文',0xa0:'左 Shift 用于切换中英文',0xa1:'右 Shift 用于切换中英文',
           0x14:'Caps Lock 用于切换大小写状态',0x11:'Ctrl 属于系统快捷键',0xa2:'左 Ctrl 属于系统快捷键',0xa3:'右 Ctrl 属于系统快捷键',
           0x12:'Alt 属于系统快捷键',0xa4:'左 Alt 属于系统快捷键',0xa5:'右 Alt 属于系统快捷键',0x5b:'左 Win 属于系统快捷键',0x5c:'右 Win 属于系统快捷键',
           0x1b:'Esc 用于取消输入',0x08:'Backspace 用于退格',0x09:'Tab 保留切换与翻页功能',0x20:'空格用于确认',0x0d:'Enter 保留确认或应用回车功能'}
    return names.get(vk,'')

def overlaps(left,right):
    a,b=parse_key(left),parse_key(right)
    if a['kind']==b['kind']=='legacy':return a['name']==b['name']
    if a['kind']==b['kind']=='physical':
        return (a['scan'],a['extended'],a['vk'] if not a['scan'] else 0)==(b['scan'],b['extended'],b['vk'] if not b['scan'] else 0)
    physical,legacy=(a,b) if a['kind']=='physical' else (b,a)
    return resolved_vk(physical)==legacy['vk']

def resolved_vk(spec):
    vk=spec['vk'];scan=spec.get('scan',0);extended=bool(spec.get('extended',0))
    if scan and os.name=='nt':
        import ctypes
        mapped=ctypes.windll.user32.MapVirtualKeyW(scan|(0xe000 if extended else 0),3)
        if mapped:vk=mapped
    return physical_vk(vk,scan,extended)

def physical_vk(vk, scan, extended=False):
    """Identify physical keypad keys even when Num Lock is off."""
    if not extended:
        return {0x4f:0x61,0x50:0x62,0x51:0x63,0x4b:0x64,0x4c:0x65,
                0x4d:0x66,0x47:0x67,0x48:0x68,0x49:0x69,0x52:0x60,0x53:0x6e,0x37:0x6a}.get(scan,vk)
    if scan==0x35:return 0x6f
    return vk

def migrate_keypad(style, keys):
    """Only update a recognized old preset; keep genuine custom assignments."""
    style=str(style)
    if style in KEYPAD:
        old=dict(KEYPAD[style],separator='KP_7' if style=='standard' else 'KP_Divide')
        if keys==old:return style,KEYPAD[style].copy()
        if keys!=KEYPAD[style]:return 'custom',dict(keys)
    return style,dict(keys)

def validate(settings):
    result = {}
    claimed=[]
    for device, presets in [('letter', LETTER), ('keypad', KEYPAD)]:
        style = settings[device+'_style']
        keys = settings[device+'_keys']
        if not isinstance(style, str) or style not in (*presets, 'custom'):
            raise ValueError('未知按键风格：'+device)
        if not isinstance(keys, dict) or set(keys) != set(ACTIONS):
            raise ValueError('请为每种笔画、通配和分词设置按键')
        for action,value in keys.items():
            if value=='':continue
            reason=reserved_reason(value)
            if reason:raise ValueError(reason)
            for slot,previous in claimed:
                if overlaps(value,previous):raise ValueError(f'{device}.{action} 与 {slot} 的按键重复')
            claimed.append((device+'.'+action,value))
        if style != 'custom' and keys != presets[style]:
            raise ValueError('预设按键已修改，请选择自定义风格')
        result[device+'_style']=style
        result[device+'_keys']=dict(keys)
    toggle=settings.get('symbol_toggle','Num_Lock')
    if toggle:
        reason=reserved_reason(toggle)
        if reason:raise ValueError(reason)
        for slot,value in claimed:
            if overlaps(toggle,value):raise ValueError('符号入口与 '+slot+' 的按键重复；请更换或停用符号入口')
    elif toggle!='':raise ValueError('符号入口按键无效')
    result['symbol_toggle']=toggle
    return result

def assign(settings, slot, value):
    """The newly captured key owns its identity; displaced slots stay empty."""
    result=copy.deepcopy(settings)
    if value:
        reason=reserved_reason(value)
        if reason:raise ValueError(reason)
    slots={device+'_'+action:(device,action) for device in ('letter','keypad') for action in ACTIONS}
    if slot not in slots and slot!='symbol_toggle':raise ValueError('未知按键位置')
    cleared=[]
    for previous,(device,action) in slots.items():
        old=result[device+'_keys'][action]
        if previous!=slot and value and old and overlaps(value,old):
            result[device+'_keys'][action]=''
            result[device+'_style']='custom'
            cleared.append(previous)
    if slot!='symbol_toggle' and value and result.get('symbol_toggle') and overlaps(value,result['symbol_toggle']):
        result['symbol_toggle']='';cleared.append('symbol_toggle')
    if slot=='symbol_toggle':result[slot]=value
    else:
        device,action=slots[slot]
        result[device+'_keys'][action]=value;result[device+'_style']='custom'
    validate(result)
    return result,cleared
