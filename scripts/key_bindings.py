"""Validated physical keys; dictionaries/learning always use canonical strokes."""
import string

ACTIONS = ('h', 's', 'p', 'n', 'z', 'wildcard', 'separator')
LETTER = {'standard': dict(zip(ACTIONS, ('h','s','p','d','z','t','f'))),
          'asdfgt': dict(zip(ACTIONS, ('a','s','d','f','g','t','r')))}
KEYPAD = {'standard': dict(zip(ACTIONS, ('KP_1','KP_2','KP_3','KP_4','KP_5','KP_6','KP_7'))),
          '789456': dict(zip(ACTIONS, ('KP_7','KP_8','KP_9','KP_4','KP_5','KP_6','KP_Divide')))}
FIELDS = ('letter_style','keypad_style','letter_keys','keypad_keys')

def validate(settings):
    result = {}
    for device, presets in [('letter', LETTER), ('keypad', KEYPAD)]:
        style = settings[device+'_style']
        keys = settings[device+'_keys']
        if not isinstance(style, str) or style not in (*presets, 'custom'):
            raise ValueError('未知按键风格：'+device)
        if not isinstance(keys, dict) or set(keys) != set(ACTIONS):
            raise ValueError('请为每种笔画、通配和分词设置按键')
        allowed = set(string.ascii_lowercase) if device=='letter' else {*(f'KP_{i}' for i in range(1,10)), 'KP_Divide','KP_Multiply'}
        if any(not isinstance(v,str) or v not in allowed for v in keys.values()):
            raise ValueError('按键无效；字母使用 A–Z，小键盘使用 1–9、/ 或 *；确认、翻页和点选字键保留')
        if len(set(keys.values())) != len(ACTIONS):
            raise ValueError('同一键盘内不能重复绑定按键')
        if style != 'custom' and keys != presets[style]:
            raise ValueError('预设按键已修改，请选择自定义风格')
        result[device+'_style']=style
        result[device+'_keys']=dict(keys)
    return result
