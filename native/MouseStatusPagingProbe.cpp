#define UNICODE
#define _UNICODE
#include <windows.h>
#include "BihuaKeyboardRoute.h"
#include "BihuaMouseView.h"
#include "BihuaMousePanel.h"
#include <cassert>
#include <filesystem>
#include <iostream>

static void pump(){MSG m;while(PeekMessageW(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
static void snapshot(HWND window,const std::filesystem::path& path){
  RedrawWindow(window,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);
  RECT r{};GetClientRect(window,&r);HDC dc=GetDC(window);
  HDC memory=CreateCompatibleDC(dc);HBITMAP bitmap=CreateCompatibleBitmap(dc,r.right,r.bottom);
  auto old=SelectObject(memory,bitmap);BitBlt(memory,0,0,r.right,r.bottom,dc,0,0,SRCCOPY);
  Gdiplus::Bitmap image(bitmap,nullptr);
  CLSID png{0x557cf406,0x1a04,0x11d3,{0x9a,0x73,0x00,0x00,0xf8,0x1e,0xf3,0x2e}};
  assert(image.Save(path.c_str(),&png)==Gdiplus::Ok);
  SelectObject(memory,old);DeleteObject(bitmap);DeleteDC(memory);ReleaseDC(window,dc);
}
int wmain(int argc,wchar_t** argv){
  assert(argc==2);std::filesystem::create_directories(argv[1]);
  BihuaKeyboardRoute route;
  auto shift=[&]{route.Shift(VK_LSHIFT,true,false);return route.Shift(VK_LSHIFT,false,false);};
  auto caps=[&](bool on){assert(route.Caps(on));assert(!route.Caps(on));};
  for(int i=0;i<2;++i){
    assert(route.mode==BihuaKeyboardRoute::Chinese);
    assert(shift()&&route.mode==BihuaKeyboardRoute::EnglishLower);
    caps(true);assert(route.mode==BihuaKeyboardRoute::EnglishUpper);
    caps(false);assert(route.mode==BihuaKeyboardRoute::EnglishLower);
    assert(shift()&&!route.English());
    caps(true);assert(route.mode==BihuaKeyboardRoute::EnglishUpper);
    caps(false);assert(route.mode==BihuaKeyboardRoute::EnglishLower);
    assert(shift()&&!route.English());
  }
  int edges=0;
  for(int n:{1,3,9}){
    BihuaMouseView v;v.Sync(1,1,0,n,5*n,0,true);
    assert(v.Navigate(BihuaMouseView::Down)==BihuaMouseView::LocalMove&&v.expanded);
    for(int i=0;i<4;++i)v.Navigate(BihuaMouseView::Down);
    if(n>1)v.Navigate(BihuaMouseView::Right);
    int col=n>1?1:0;
    assert(v.Navigate(BihuaMouseView::Down)==BihuaMouseView::PageDown);
    v.PreparePage(1,true);v.Sync(1,2,n,n,5*n,0,true);
    assert(v.expanded&&v.navigation==n+4*n+col);++edges;
    for(int i=0;i<4;++i)v.Navigate(BihuaMouseView::Up);
    assert(v.Navigate(BihuaMouseView::Up)==BihuaMouseView::PageUp);
    v.PreparePage(-1,true);v.Sync(1,3,0,n,5*n,0,true);
    assert(v.expanded&&v.navigation==col);++edges;
    assert(v.Navigate(BihuaMouseView::Up)==BihuaMouseView::LocalMove&&!v.expanded);++edges;
    v.expanded=true;v.navigation=4*n+col;
    v.PreparePage(1,true);v.Sync(1,4,n,n,4*n+1,0,false);
    assert(v.navigation==5*n&&v.expanded); // Last partial row clamps the column.
    assert(v.Navigate(BihuaMouseView::Down)==BihuaMouseView::LocalMove&&v.navigation==5*n);++edges;
    v.PreparePage(-1,true);v.Sync(1,5,n,n,4*n+1,0,false);
    assert(v.navigation==-1&&v.expanded); // Failed page movement never replays.
    v.PreparePage(-1,true);v.Sync(2,6,0,n,5*n,0,true);
    assert(v.navigation==-1&&!v.expanded);++edges;
    v.expanded=true;v.PreparePage(1,false);v.Sync(2,7,n,n,5*n,0,true);
    assert(v.navigation==-1&&v.expanded);++edges;
  }
  BihuaMousePanel panel;panel.Create();panel.SetProfileActive(true);panel.SetTargetActive(true);panel.SetModeAvailable(true);
  weasel::UIStyle style;style.font_point=14;style.candidate_spacing=0;
  weasel::Context context;int actions=0,last=-1;
  panel.clicked=[&](int action,int,uint32_t,uint64_t,uint64_t){++actions;last=action;};
  auto hidden=[&](int id){auto r=panel.ButtonRect(id);return IsRectEmpty(&r);};
  auto click=[&](int id){auto r=panel.ButtonRect(id);assert(!IsRectEmpty(&r));auto p=MAKELPARAM((r.left+r.right)/2,(r.top+r.bottom)/2);
    SendMessageW(panel.window,WM_LBUTTONDOWN,MK_LBUTTON,p);SendMessageW(panel.window,WM_LBUTTONUP,0,p);pump();};
  HWND front=GetForegroundWindow();int geometries=0;
  for(int dpi:{96,144,192})for(bool dark:{false,true}){
    SendMessageW(panel.window,WM_DPICHANGED,MAKELONG(dpi,dpi),0);
    style.back_color=dark?RGB(28,30,29):RGB(255,255,255);
    style.candidate_text_color=dark?RGB(240,240,240):RGB(25,25,25);
    for(int mode=0;mode<3;++mode){
      panel.Update(true,true,style,{},1);panel.SetKeyboardMode(mode);pump();
      assert(SendMessageW(panel.window,WM_APP+45,0,0)==mode+1);
      assert(!hidden(55));for(int id:{6,7,8,17,18})assert(hidden(id));
      int before=actions;click(55);assert(actions==before+1&&last==21); // Intent only; TSF owns conversion.
      if(dpi==144)snapshot(panel.window,std::filesystem::path(argv[1])/
          (std::wstring(dark?L"dark-":L"light-")+std::to_wstring(mode)+L".png"));
      ++geometries;
    }
    context.preedit.str=L"一";std::vector<std::wstring> rows(45,L"天");
    panel.Update(true,true,style,context,1,rows,9,0,3,true,-1,4,true,true);pump();
    assert(hidden(6)&&!hidden(7)&&!hidden(18));
    assert(panel.ButtonRect(7).top>panel.ButtonRect(18).bottom);
    click(7);assert(last==7);click(18);assert(last==20);
    panel.Update(true,true,style,context,1,rows,9,9,4,true,-1,5,true,true);pump();
    assert(!hidden(6)&&!hidden(7)&&hidden(18));click(6);assert(last==6);
    assert(panel.ButtonRect(6).top>panel.ButtonRect(0).bottom); // No toolbar arrows.
    panel.Update(true,true,style,context,1,rows,9,18,5,true,-1,6,true,false);pump();
    assert(!hidden(6)&&hidden(7)&&hidden(18));
    if(dpi==144)snapshot(panel.window,std::filesystem::path(argv[1])/(dark?L"expanded-dark.png":L"expanded-light.png"));
  }
  assert(GetForegroundWindow()==front);
  std::cout<<"{\"result\":\"PASS\",\"three_route_modes\":true,\"mode_visual_cases\":"<<geometries
      <<",\"edge_navigation_cases\":"<<edges<<",\"status_intent_only\":true,\"caps_lock_direct_english\":true,\"vertical_page_controls\":true,\"no_activation\":true}";
}
