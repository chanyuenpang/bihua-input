#define UNICODE
#define _UNICODE
#include <windows.h>
#include "BihuaKeyboardRoute.h"
#include "BihuaMouseView.h"
#include "BihuaStrokeInfo.h"
#include "BihuaMousePanel.h"
#include <cassert>
#include <iostream>
static void pump(){MSG m;while(PeekMessageW(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
static void wait_ui(unsigned ms){auto until=GetTickCount64()+ms;do{pump();Sleep(5);}while(GetTickCount64()<until);pump();}
int wmain(int argc,wchar_t** argv){
  assert(argc==3);
  BihuaKeyboardRoute keyboard;
  keyboard.Shift(VK_LSHIFT,true,false);keyboard.Shift(VK_LSHIFT,true,false);
  assert(keyboard.Shift(VK_LSHIFT,false,false)&&keyboard.mode==BihuaKeyboardRoute::EnglishLower);
  assert(!keyboard.Shift(VK_LSHIFT,false,false)&&keyboard.English());
  assert(keyboard.Caps(true)&&keyboard.mode==BihuaKeyboardRoute::EnglishUpper);
  assert(!keyboard.Caps(true)&&keyboard.English());
  assert(keyboard.Caps(false)&&keyboard.mode==BihuaKeyboardRoute::EnglishLower);
  keyboard.Shift(VK_LSHIFT,true,false);assert(keyboard.Shift(VK_LSHIFT,false,false)&&!keyboard.English());
  keyboard.Shift(VK_RSHIFT,true,false);keyboard.OtherDown();
  assert(!keyboard.Shift(VK_RSHIFT,false,false)&&!keyboard.English());
  keyboard.Shift(VK_RSHIFT,true,true);assert(!keyboard.Shift(VK_RSHIFT,false,true));
  keyboard.Shift(VK_RSHIFT,true,false);keyboard.CancelGesture();assert(!keyboard.Shift(VK_RSHIFT,false,false));
  keyboard.Shift(VK_LSHIFT,true,false);keyboard.Shift(VK_RSHIFT,true,false);
  assert(!keyboard.Shift(VK_LSHIFT,false,false));
  for(int n:{1,3,9})for(int count:{0,1,n,n+1,5*n-2,5*n}){
    BihuaMouseView view;view.Sync(1,2,0,n,count,0);
    assert(view.Navigate(BihuaMouseView::Down)==(count>0));
    if(!count)continue;
    assert(view.navigation==0&&view.expanded==(count>n));
    view.Navigate(BihuaMouseView::Right);
    assert(view.navigation==(n>1&&count>1?1:0));
    if(view.expanded){view.Navigate(BihuaMouseView::Down);assert(view.navigation>=n);view.Navigate(BihuaMouseView::Up);}
    view.Navigate(BihuaMouseView::Up);assert(!view.expanded&&view.navigation<n);
    auto revision=view.revision;view.Sync(1,3,2*n,n,count,0);assert(view.navigation==-1&&view.revision>revision);
  }
  BihuaMouseView ordered;ordered.Sync(1,1,0,9,45,0);
  ordered.Navigate(BihuaMouseView::Down);ordered.Navigate(BihuaMouseView::Right);ordered.Navigate(BihuaMouseView::Down);
  assert(ordered.navigation==10); // confirmation cannot depend on UI message latency
  BihuaStrokeInfo strokes;strokes.Load(argv[1]);assert(strokes.available&&strokes.codes[L"天"]=="1134");
  assert(strokes.Describe(L"中国").size()==2);
  assert(BihuaStrokeInfo::Characters(L"𠮷").size()==1);
  assert(strokes.Describe(L"☃")[0].second.empty());
  std::filesystem::path bad=argv[2];std::filesystem::create_directories(bad);
  std::filesystem::copy_file(std::filesystem::path(argv[1])/L"canonical_strokes.tsv",bad/L"canonical_strokes.tsv");
  std::filesystem::copy_file(std::filesystem::path(argv[1])/L"canonical_strokes.sha256",bad/L"canonical_strokes.sha256");
  std::ofstream(bad/L"current-canonical_strokes.tsv")<<"character\tstroke_digits\n天\t111\n";
  std::ofstream(bad/L"current-canonical_strokes.sha256")<<std::string(64,'0');
  BihuaStrokeInfo corrupt;corrupt.Load(bad);assert(!corrupt.available&&corrupt.codes.empty());
  BihuaMousePanel panel;panel.Create();panel.SetProfileActive(true);panel.SetTargetActive(true);
  weasel::Context context;weasel::Text word;word.str=L"天";context.cinfo.candies.push_back(word);
  weasel::UIStyle style;style.font_point=14;style.back_color=RGB(255,255,255);style.candidate_text_color=RGB(20,20,20);
  int selected=0,inspected=0;
  panel.clicked=[&](int action,int index,uint32_t gen,uint64_t semantic,uint64_t view){
    if(action==18)++selected;
    if(action==19){++inspected;panel.ShowInformation(strokes.Describe(L"天"),gen,semantic,view);}
  };
  panel.Update(true,true,style,context,1,{},9,0,2,false,-1,3,true);pump();
  auto r=panel.ButtonRect(8);auto point=MAKELPARAM((r.left+r.right)/2,(r.top+r.bottom)/2);
  auto down=[&]{SendMessageW(panel.window,WM_LBUTTONDOWN,1,point);};
  auto up=[&]{SendMessageW(panel.window,WM_LBUTTONUP,0,point);pump();};
  HWND foreground=GetForegroundWindow();down();up();assert(selected==1&&inspected==0);
  down();wait_ui(600);assert(inspected==1);up();assert(selected==1);
  HWND popup=FindWindowW(L"BihuaStrokeInfoV1",nullptr);assert(popup&&IsWindowVisible(popup));
  assert(GetForegroundWindow()==foreground);
  panel.CancelPointer();pump();assert(!IsWindowVisible(popup));
  down();panel.SetView(false,-1,4);wait_ui(600);up();assert(inspected==1&&selected==1);
  panel.Update(true,true,style,context,1,{},9,0,2,false,-1,5,false);pump();
  down();wait_ui(600);up();assert(inspected==1&&selected==2);
  panel.Update(true,true,style,context,1,{},9,0,2,false,-1,6,true);pump();
  down();SendMessageW(panel.window,WM_MOUSEMOVE,1,MAKELPARAM(r.left-20,r.top-20));wait_ui(600);SendMessageW(panel.window,WM_CANCELMODE,0,0);up();assert(inspected==1);
  std::cout<<"{\"result\":\"PASS\",\"shift_caps_event_deduplication\":true,\"chords_never_toggle\":true,\"navigation_N1_N3_N9_boundaries\":true,\"navigation_confirmation_independent_of_paint\":true,\"canonical_hash_checked\":true,\"invalid_current_never_falls_back\":true,\"unicode_word_strokes\":true,\"long_press_does_not_select\":true,\"short_press_selects\":true,\"disabled_long_press_short_click_preserved\":true,\"view_change_cancels_hold\":true,\"movement_cancels_hold\":true,\"popup_no_activation\":true}";
}
