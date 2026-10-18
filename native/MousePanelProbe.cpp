#define UNICODE
#define _UNICODE
#include <windows.h>
#include "BihuaMousePanel.h"
#include <cassert>
#include <iostream>
static void pump(){MSG m;while(PeekMessageW(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
int main(){
  BihuaMousePanel panel;panel.Create();panel.SetProfileActive(true);panel.SetTargetActive(true);int clicks=0,last_action=-1;uint32_t generation=0;
  panel.clicked=[&](int action,int index,uint32_t gen,uint64_t semantic,uint64_t view){last_action=action;++clicks;generation=gen;};
  weasel::Context context;weasel::UIStyle style;
  panel.Update(true,true,style,context,1);pump();
  RECT idleBounds;GetWindowRect(panel.window,&idleBounds);
  auto hidden=[&](int id){auto r=panel.ButtonRect(id);return IsRectEmpty(&r);};
  for(int id:{6,7,8,17,18})assert(hidden(id));
  for(int id=0;id<6;++id)assert(!hidden(id));
  auto button=panel.ButtonRect(0);
  LPARAM point=MAKELPARAM((button.left+button.right)/2,(button.top+button.bottom)/2);
  auto down=[&]{SendMessageW(panel.window,WM_LBUTTONDOWN,MK_LBUTTON,point);};
  auto up=[&]{SendMessageW(panel.window,WM_LBUTTONUP,0,point);};
  HWND foreground=GetForegroundWindow();down();up();assert(clicks==1&&generation==1&&last_action==0);
  down();panel.Update(true,true,style,context,2);up();assert(clicks==1);
  down();context.preedit.str=L"一";panel.Update(true,true,style,context,2);up();assert(clicks==1);
  panel.Update(true,false,style,context,2);down();up();assert(clicks==1);
  assert(GetForegroundWindow()==foreground);pump();
  assert(IsWindowVisible(panel.window)); // pending is disabled, never hidden
  panel.SetTargetActive(false);pump();assert(IsWindowVisible(panel.window));
  down();up();assert(clicks==1);
  panel.SetTargetActive(true);panel.Update(true,true,style,context,2);pump();
  assert(IsWindowVisible(panel.window));
  RECT queryBounds;GetWindowRect(panel.window,&queryBounds);
  assert(queryBounds.right-queryBounds.left>idleBounds.right-idleBounds.left);
  assert(queryBounds.bottom-queryBounds.top>idleBounds.bottom-idleBounds.top);
  assert(hidden(6)&&hidden(7)&&!hidden(17)&&!hidden(55));
  SendMessageW(panel.window,WM_MOUSELEAVE,0,0);assert(IsWindowVisible(panel.window));
  panel.Update(true,true,style,context,2);pump();
  button=panel.ButtonRect(17);point=MAKELPARAM((button.left+button.right)/2,(button.top+button.bottom)/2);
  down();up();assert(last_action==17&&clicks==2);
  context={};style.font_point=8;style.candidate_spacing=0;context.preedit.str=L"一";panel.Update(true,true,style,context,3);pump();
  auto equal_keys=[&]{
    auto first=panel.ButtonRect(1);
    for(int id:{2,3,4}){
      auto r=panel.ButtonRect(id);
      assert(r.right-r.left==first.right-first.left&&r.bottom-r.top==first.bottom-first.top);
    }
    auto left=panel.ButtonRect(0),right=panel.ButtonRect(5);
    assert(left.right-left.left==right.right-right.left);
    assert(left.right-left.left>first.right-first.left);
    auto inner=panel.ButtonRect(2),lastInner=panel.ButtonRect(4);
    assert(first.left-left.right==inner.left-first.right);
    assert(right.left-lastInner.right==inner.left-first.right);
    auto back=panel.ButtonRect(17);
    assert(back.right-back.left==2*(first.right-first.left));
    assert(back.bottom-back.top==first.bottom-first.top);
  };
  equal_keys();
  RECT compactBounds;GetWindowRect(panel.window,&compactBounds);
  HRGN region=CreateRectRgn(0,0,0,0);assert(GetWindowRgn(panel.window,region)!=ERROR&&!PtInRegion(region,0,0));DeleteObject(region);
  style.font_point=18;style.candidate_spacing=12;panel.Update(true,true,style,context,4);pump();
  equal_keys();
  RECT expandedBounds;GetWindowRect(panel.window,&expandedBounds);assert(expandedBounds.right-expandedBounds.left>compactBounds.right-compactBounds.left&&expandedBounds.bottom-expandedBounds.top>compactBounds.bottom-compactBounds.top);
  int chosen_index=-1,exposed=0;uint64_t observed_revision=0,viewRevision=1;bool viewOpened=false;
  panel.clicked=[&](int action,int index,uint32_t gen,uint64_t semantic,uint64_t view){if(action==20){viewOpened=!viewOpened;panel.SetView(viewOpened,-1,++viewRevision);return;}last_action=action;chosen_index=index;++clicks;observed_revision=semantic;};
  panel.displayed=[&](uint32_t gen,uint64_t semantic,int first,int count){exposed=count;};
  auto hit=[&](int id){auto r=panel.ButtonRect(id);auto p=MAKELPARAM((r.left+r.right)/2,(r.top+r.bottom)/2);SendMessageW(panel.window,WM_LBUTTONDOWN,MK_LBUTTON,p);SendMessageW(panel.window,WM_LBUTTONUP,0,p);pump();};
  for(int n:{1,3,9})for(int count:{0,n,n+1,5*n,5*n+2}){
    viewOpened=false;std::vector<std::wstring> rows(count,L"天");
    context={};for(int i=0;i<(std::min)(count,n);++i){weasel::Text t;t.str=L"天";context.cinfo.candies.push_back(t);}
    panel.Update(true,true,style,context,10+n+count,rows,n,2*n,71);pump();
    RedrawWindow(panel.window,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);
    assert(!count||exposed==(std::min)(count,n));
    RECT collapsed;GetWindowRect(panel.window,&collapsed);
    hit(18);RedrawWindow(panel.window,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);
    RECT opened;GetWindowRect(panel.window,&opened);
    if(count<=n){assert(opened.bottom-opened.top==collapsed.bottom-collapsed.top);continue;}
    assert(exposed==(std::min)(count,5*n));
    assert(opened.bottom-opened.top>collapsed.bottom-collapsed.top);
    int last=(std::min)(count,5*n)-1,id=last<9?last+8:last+10;
    hit(id);assert(last_action==18&&chosen_index==2*n+last&&observed_revision==71);
    hit(6); // PageUp is now the top control on a later Rime page.
    panel.SetView(false,-1,++viewRevision);pump();GetWindowRect(panel.window,&opened);assert(opened.bottom-opened.top==collapsed.bottom-collapsed.top);
    viewOpened=false;hit(18);panel.SetTargetActive(false);pump();assert(IsWindowVisible(panel.window));
    viewOpened=false;panel.SetView(false,-1,++viewRevision);panel.SetTargetActive(true);pump();GetWindowRect(panel.window,&opened);assert(opened.bottom-opened.top==collapsed.bottom-collapsed.top);
  }
  for(int dpi:{96,144,192})for(int size:{8,14,18})for(bool dark:{false,true}){
    SendMessageW(panel.window,WM_DPICHANGED,MAKELONG(dpi,dpi),0);
    style.font_point=size;style.back_color=dark?RGB(30,30,30):RGB(255,255,255);
    context={};panel.Update(true,true,style,context,100);pump();
    RECT idle;GetWindowRect(panel.window,&idle);
    for(int id:{6,7,8,17,18})assert(hidden(id));
    for(int id=0;id<6;++id)assert(!hidden(id));
    context.preedit.str=L"一";panel.Update(true,true,style,context,101);pump();
    RECT active;GetWindowRect(panel.window,&active);
    assert(active.right-active.left>idle.right-idle.left&&active.bottom-active.top>idle.bottom-idle.top);
    assert(hidden(6)&&hidden(7)&&!hidden(17)&&!hidden(55));
    context={};panel.Update(true,true,style,context,102,{L"天"});pump();
    GetWindowRect(panel.window,&active);
    assert(!hidden(8)&&active.bottom-active.top>idle.bottom-idle.top);
    panel.Update(true,true,style,context,103);pump();
    RECT cleared;GetWindowRect(panel.window,&cleared);
    assert(cleared.right-cleared.left==idle.right-idle.left&&cleared.bottom-cleared.top==idle.bottom-idle.top);
    RedrawWindow(panel.window,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);
  }
  assert(GetForegroundWindow()==foreground);
  std::cout<<"{\"result\":\"PASS\",\"idle_six_keys_only\":true,\"query_expands_prediction_stays_full_clear_compacts\":true,\"idle_dpi_font_theme_cases\":18,\"click_uses_displayed_lease\":true,\"changed_target_cancels_press\":true,\"changed_candidates_cancels_press\":true,\"disabled_noop\":true,\"no_activation\":true,\"backspace_button\":true,\"rounded_window_region\":true,\"font_spacing_shrink_geometry\":true,\"ordinary_keys_equal_backspace_double\":true,\"five_rows_N1_N3_N9\":true,\"exposure_only_visible_rows\":true,\"absolute_candidate_identity\":true,\"focus_restores_collapsed\":true}";
}
