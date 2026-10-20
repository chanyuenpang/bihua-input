"""Validated physical keys; dictionaries/learning always use canonical strokes."""
import string

ACTIONS = ('h', 's', 'p', 'n', 'z', 'wildcard', 'separator')
LETTER = {'standard': dict(zip(ACTIONS, ('h','s','p','d','z','t','f'))),
          'asdfgt': dict(zip(ACTIONS, ('a','s','d','f','g','t','r')))}
KEYPAD = {'standard': dict(zip(ACTIONS, ('KP_1','KP_2','KP_3','KP_4','KP_5','KP_6','KP_Decimal'))),
          '789456': dict(zip(ACTIONS, ('KP_7','KP_8','KP_9','KP_4','KP_5','KP_6','KP_Decimal')))}
FIELDS = ('letter_style','keypad_style','letter_keys','keypad_keys')

def physical_vk(vk, scan, extended=False):
    """Identify physical keypad keys even when Num Lock is off."""
    if not extended:
        return {0x4f:0x61,0x50:0x62,0x51:0x63,0x4b:0x64,0x4c:0x65,
                0x4d:0x66,0x47:0x67,0x48:0x68,0x49:0x69,0x53:0x6e}.get(scan,vk)
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
    for device, presets in [('letter', LETTER), ('keypad', KEYPAD)]:
        style = settings[device+'_style']
        keys = settings[device+'_keys']
        if not isinstance(style, str) or style not in (*presets, 'custom'):
            raise ValueError('未知按键风格：'+device)
        if not isinstance(keys, dict) or set(keys) != set(ACTIONS):
            raise ValueError('请为每种笔画、通配和分词设置按键')
        allowed = set(string.ascii_lowercase) if device=='letter' else {*(f'KP_{i}' for i in range(1,10)), 'KP_Divide','KP_Multiply','KP_Decimal'}
        if any(not isinstance(v,str) or v not in allowed for v in keys.values()):
            raise ValueError('按键无效；字母使用 A–Z，小键盘使用 1–9、.、/ 或 *；确认和翻页键保留')
        if len(set(keys.values())) != len(ACTIONS):
            raise ValueError('同一键盘内不能重复绑定按键')
        if style != 'custom' and keys != presets[style]:
            raise ValueError('预设按键已修改，请选择自定义风格')
        result[device+'_style']=style
        result[device+'_keys']=dict(keys)
    return result
