"""Antialiased 24-unit stroke paths matching the native mouse panel."""
import atexit
import ctypes as c
from ctypes import wintypes as w

PATHS={
 'h':[('L',3,12,21,12)],
 's':[('L',12,3,12,21)],
 'p':[('C',17.5,3,17.8,11,13.2,17.2,6.5,21)],
 'n':[('C',8.5,8,11.1,9,13.8,12.1,15.6,16)],
 'z':[('L',4,4,19.5,4),('C',19.5,4,20.2,4,20.5,4.4,20.4,5.2),
      ('C',20.4,5.2,20,10.5,19.1,16,18.1,18.5),
      ('C',18.1,18.5,17.4,20.5,16.5,21,14.8,20.1),('L',14.8,20.1,12,18.5)],
 'wildcard':[('C',7,8,7,5.2,9.1,3.5,12,3.5),('C',12,3.5,14.9,3.5,17,5.4,17,8),
             ('C',17,8,17,10.2,15.5,11.2,13.5,12.5),('C',13.5,12.5,12.4,13.2,12,14,12,15.5)],
 'separator':[('C',13.5,8.5,13.5,11.5,12,14,10.5,15.5)]
}

gd=c.WinDLL('gdiplus')
def bind(name,*args):
    fn=getattr(gd,name);fn.argtypes=list(args);fn.restype=c.c_int;return fn
ptr=c.c_void_p;out=c.POINTER(ptr);f=c.c_float
class Startup(c.Structure):
    _fields_=[('version',c.c_uint),('callback',ptr),('thread',w.BOOL),('codecs',w.BOOL)]
startup=bind('GdiplusStartup',c.POINTER(c.c_size_t),c.POINTER(Startup),ptr)
gd.GdiplusShutdown.argtypes=[c.c_size_t]
token=c.c_size_t();assert startup(c.byref(token),c.byref(Startup(1,None,False,False)),None)==0
atexit.register(gd.GdiplusShutdown,token.value)
create_graphics=bind('GdipCreateFromHDC',w.HDC,out);delete_graphics=bind('GdipDeleteGraphics',ptr)
smooth=bind('GdipSetSmoothingMode',ptr,c.c_int)
create_path=bind('GdipCreatePath',c.c_int,out);delete_path=bind('GdipDeletePath',ptr)
line=bind('GdipAddPathLine',ptr,*([f]*4));bezier=bind('GdipAddPathBezier',ptr,*([f]*8))
create_pen=bind('GdipCreatePen1',w.DWORD,f,c.c_int,out);delete_pen=bind('GdipDeletePen',ptr)
caps=bind('GdipSetPenLineCap197819',ptr,c.c_int,c.c_int,c.c_int)
join=bind('GdipSetPenLineJoin',ptr,c.c_int);draw_path=bind('GdipDrawPath',ptr,ptr,ptr)
create_brush=bind('GdipCreateSolidFill',w.DWORD,out);delete_brush=bind('GdipDeleteBrush',ptr)
ellipse=bind('GdipFillEllipse',ptr,ptr,f,f,f,f)

def draw(dc,rect,action,color,scale):
    graphics=ptr();path=ptr();pen=ptr();brush=ptr()
    icon_scale=.84 if action in ('h','s','p','n','z','wildcard') else 1
    side=min(24*scale,rect.right-rect.left-4*scale,rect.bottom-rect.top-4*scale)*icon_scale
    unit=side/24;left=(rect.left+rect.right-side)/2;top=(rect.top+rect.bottom-side)/2
    argb=0xff000000|((color&255)<<16)|(color&0xff00)|((color>>16)&255)
    try:
        assert create_graphics(dc,c.byref(graphics))==0
        assert smooth(graphics,4)==0
        assert create_path(0,c.byref(path))==0
        assert create_pen(argb,unit*1.7/icon_scale,2,c.byref(pen))==0
        caps(pen,2,2,0);join(pen,2)
        for command,*points in PATHS[action]:
            values=[(left if i%2==0 else top)+value*unit for i,value in enumerate(points)]
            assert (line if command=='L' else bezier)(path,*values)==0
        assert draw_path(graphics,pen,path)==0
        if action=='wildcard':
            assert create_brush(argb,c.byref(brush))==0
            dot_side=2.1/icon_scale
            assert ellipse(graphics,brush,left+(12-dot_side/2)*unit,top+(20-dot_side/2)*unit,dot_side*unit,dot_side*unit)==0
    finally:
        if brush:delete_brush(brush)
        if pen:delete_pen(pen)
        if path:delete_path(path)
        if graphics:delete_graphics(graphics)
