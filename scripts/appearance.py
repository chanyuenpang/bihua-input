"""Appearance values shared by the native and web settings clients."""
FIELDS=('color_scheme','dark_scheme','font_face','corner_radius','candidate_spacing')

def color(value,fmt='abgr',fallback='#202830'):
    try:
        raw=value
        if isinstance(value,str):value=int(value.strip().lstrip('#'),16)
        if not isinstance(value,int):return fallback
        if fmt=='rgba' and (value>0xffffff or isinstance(raw,str) and len(raw.lstrip('#').removeprefix('0x'))==8):value>>=8
        if fmt not in ('rgba','argb','rgb'):
            value=((value&255)<<16)|(value&0xff00)|((value>>16)&255)
        return f'#{value&0xffffff:06x}'
    except (ValueError,TypeError):return fallback

def palette(scheme):
    fmt=scheme.get('color_format','abgr')
    back=color(scheme.get('back_color'),fmt,'#ffffff')
    normal=color(scheme.get('text_color'),fmt,'#000000')
    text=color(scheme.get('candidate_text_color'),fmt,normal)
    selected=color(scheme.get('hilited_candidate_back_color',scheme.get('hilited_back_color')),fmt,back)
    selected_text=color(scheme.get('hilited_candidate_text_color',scheme.get('hilited_text_color')),fmt,normal)
    return {'background':back,'text':text,'border':color(scheme.get('border_color'),fmt,normal),
            'label':color(scheme.get('label_color',scheme.get('candidate_text_color',scheme.get('text_color'))),fmt,text),
            'selected_background':selected,'selected_text':selected_text,
            'selected_label':color(scheme.get('hilited_label_color',scheme.get('hilited_candidate_text_color')),fmt,selected_text)}

def catalog(compiled,shared,active):
    schemes={str(key):value for key,value in (shared.get('preset_color_schemes') or {}).items()}
    schemes.update({str(key):value for key,value in (compiled.get('preset_color_schemes') or {}).items()})
    for identity in active:
        if identity and identity not in schemes:schemes[identity]={'name':'当前配色 · '+identity}
    if not schemes:schemes={'aqua':{'name':'默认'}}
    return [{'id':str(identity),'name':str(data.get('name',identity)),'colors':palette(data)}
            for identity,data in schemes.items() if isinstance(data,dict)]

def values(compiled,patch):
    style=compiled.get('style') or {};layout=style.get('layout') or {}
    def current(key,default):return patch.get('style/'+key,layout.get(key[7:],default) if key.startswith('layout/') else style.get(key,default))
    light=str(current('color_scheme','aqua'))
    dark=str(current('color_scheme_dark',light))
    return {'color_scheme':light,'dark_scheme':'' if dark==light else dark,
            'font_face':str(current('font_face','Microsoft YaHei')),
            'corner_radius':current('layout/corner_radius',4),'candidate_spacing':current('layout/candidate_spacing',5)}

def updates(settings,schemes):
    identities={row['id'] for row in schemes}
    if not isinstance(settings['color_scheme'],str) or not isinstance(settings['dark_scheme'],str):raise ValueError('配色名称无效')
    if settings['color_scheme'] not in identities or settings['dark_scheme'] and settings['dark_scheme'] not in identities:
        raise ValueError('请选择已有配色方案')
    font=settings['font_face']
    if not isinstance(font,str) or not 1<=len(font.strip())<=160 or any(c in font for c in '\0\r\n\t'):
        raise ValueError('字体名称无效')
    for name in ('corner_radius','candidate_spacing'):
        if type(settings[name]) is not int or not 0<=settings[name]<=100:raise ValueError('外观数值须为 0–100')
    return {'style/color_scheme':settings['color_scheme'],
            'style/color_scheme_dark':settings['dark_scheme'] or settings['color_scheme'],
            'style/font_face':font.strip(),'style/label_font_face':font.strip(),'style/comment_font_face':font.strip(),
            'style/font_point':settings['font_size'],'style/label_font_point':settings['font_size'],
            'style/comment_font_point':settings['font_size'],'style/horizontal':settings['horizontal'],
            'style/layout/corner_radius':settings['corner_radius'],
            'style/layout/candidate_spacing':settings['candidate_spacing']}
