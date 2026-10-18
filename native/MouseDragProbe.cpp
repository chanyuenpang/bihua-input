#define UNICODE
#define _UNICODE
#include <windows.h>
#include "BihuaMousePanel.h"
#include <iostream>
#include <stdexcept>
#include <string>

static void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
static void pump(){MSG m;while(PeekMessageW(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
static void wait_ui(int ms){auto until=GetTickCount64()+ms;do{pump();Sleep(5);}while(GetTickCount64()<until);}
static RECT bounds(HWND h){RECT r{};check(!!GetWindowRect(h,&r),"window geometry");return r;}
static POINT center(BihuaMousePanel& panel,int id){auto r=panel.ButtonRect(id);check(!IsRectEmpty(&r),"test target exists");POINT p{(r.left+r.right)/2,(r.top+r.bottom)/2};ClientToScreen(panel.window,&p);return p;}
static void mouse(HWND h,UINT message,POINT screen){ScreenToClient(h,&screen);SendMessageW(h,message,message==WM_LBUTTONUP?0:MK_LBUTTON,MAKELPARAM(screen.x,screen.y));pump();}
static std::wstring caption(HWND h){std::wstring text(GetWindowTextLengthW(h)+1,L'\0');text.resize(GetWindowTextW(h,text.data(),static_cast<int>(text.size())));return text;}
struct RegistrySandbox {
  HKEY key=nullptr,failed_root=nullptr;std::wstring path;
  RegistrySandbox(){
    path=L"Software\\BihuaDragProbe20-"+std::to_wstring(GetCurrentProcessId());
    check(RegCreateKeyExW(HKEY_CURRENT_USER,path.c_str(),0,nullptr,0,KEY_ALL_ACCESS,nullptr,&key,nullptr)==ERROR_SUCCESS,"registry sandbox");
    check(RegOverridePredefKey(HKEY_CURRENT_USER,key)==ERROR_SUCCESS,"isolate position writes");
  }
  ~RegistrySandbox(){RegOverridePredefKey(HKEY_CURRENT_USER,nullptr);if(failed_root)RegCloseKey(failed_root);if(key)RegCloseKey(key);RegDeleteTreeW(HKEY_CURRENT_USER,path.c_str());}
  void fail_writes(){check(RegCreateKeyExW(key,L"VolatileRoot",0,nullptr,REG_OPTION_VOLATILE,KEY_ALL_ACCESS,nullptr,&failed_root,nullptr)==ERROR_SUCCESS,"failure sandbox");check(RegOverridePredefKey(HKEY_CURRENT_USER,failed_root)==ERROR_SUCCESS,"write failure mapping");}
  void restore_writes(){check(RegOverridePredefKey(HKEY_CURRENT_USER,key)==ERROR_SUCCESS,"restore sandbox mapping");}
  bool position(POINT* p=nullptr){DWORD x=0,y=0,size=4;bool ok=RegGetValueW(key,L"Software\\BihuaInputMethod\\MousePanel",L"X",RRF_RT_REG_DWORD,nullptr,&x,&size)==ERROR_SUCCESS;size=4;ok=ok&&RegGetValueW(key,L"Software\\BihuaInputMethod\\MousePanel",L"Y",RRF_RT_REG_DWORD,nullptr,&y,&size)==ERROR_SUCCESS;if(ok&&p)*p={static_cast<LONG>(x),static_cast<LONG>(y)};return ok;}
};
int main(){
 try {
  SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  RegistrySandbox registry;
  BihuaMousePanel panel;panel.Create();panel.SetProfileActive(true);panel.SetTargetActive(true);
  weasel::UIStyle style;style.font_point=14;style.candidate_spacing=4;
  weasel::Context context;int actions=0,inspections=0,cases=0;
  panel.clicked=[&](int action,int index,uint32_t generation,uint64_t semantic,uint64_t view){
    if(action==19){++inspections;panel.ShowInformation({{L"天","1134"}},generation,semantic,view);}
    else ++actions;
  };
  uint64_t semantic=1;
  auto update=[&](int count,bool opened=false,int n=9){
    context={};if(count){context.preedit.str=L"一";context.cinfo.candies.resize((std::min)(count,n));for(auto& t:context.cinfo.candies)t.str=L"天";}
    std::vector<std::wstring> rows(count,L"天");
    panel.Update(true,true,style,context,1,rows,n,n,++semantic,opened,-1,semantic,true,true);pump();
    SetWindowPos(panel.window,nullptr,100,100,0,0,SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE);
  };
  auto metric=[&](int id,int dpi){auto fn=reinterpret_cast<int(WINAPI*)(int,UINT)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetSystemMetricsForDpi"));return (std::max)(1,fn?fn(id,dpi):GetSystemMetrics(id));};
  HWND front=GetForegroundWindow();
  auto drag=[&](POINT start,int dx,int dy,bool back=false){
    auto before=bounds(panel.window);auto text=caption(panel.window);auto view=SendMessageW(panel.window,WM_APP+44,0,0);int a=actions,i=inspections;
    mouse(panel.window,WM_LBUTTONDOWN,start);
    POINT end{start.x+dx,start.y+dy};mouse(panel.window,WM_MOUSEMOVE,end);
    auto moved=bounds(panel.window);if(moved.left!=before.left+dx||moved.top!=before.top+dy)std::cerr<<"drag case="<<cases<<" actual="<<moved.left-before.left<<","<<moved.top-before.top<<" expected="<<dx<<","<<dy<<" capture="<<GetCapture()<<"\n";check(moved.left==before.left+dx&&moved.top==before.top+dy,"control press must become whole-panel drag");
    if(back){mouse(panel.window,WM_MOUSEMOVE,start);end=start;}
    mouse(panel.window,WM_LBUTTONUP,end);
    check(actions==a&&inspections==i,"drag release emitted input or inspection");
    check(caption(panel.window)==text&&SendMessageW(panel.window,WM_APP+44,0,0)==view,"drag changed projection or view");
    check(GetForegroundWindow()==front,"drag activated panel");
    ++cases;
  };
  update(0);check(!registry.position(),"position must initially be absent");
  auto p=center(panel,0);mouse(panel.window,WM_LBUTTONDOWN,p);mouse(panel.window,WM_LBUTTONUP,p);
  check(actions==1&&!registry.position(),"short click changed position");
  // This fails on 0.6.19: a stroke-key press never enters dragging.
  drag(center(panel,0),30,20);
  POINT saved;check(registry.position(&saved),"drag release did not persist geometry");
  auto r=bounds(panel.window);check(saved.x==r.left&&saved.y==r.top,"persisted geometry differs");
  for(int dpi:{96,144,192}){
    SendMessageW(panel.window,WM_DPICHANGED,MAKELONG(dpi,dpi),0);pump();
    for(int n:{1,3,9}){
      update(5*n,true,n);
      for(int id:{0,5,6,7,17,55,8,5*n-1<9?5*n-1+8:5*n-1+10}){
        auto point=center(panel,id);drag(point,metric(SM_CXDRAG,dpi)+15,metric(SM_CYDRAG,dpi)+10,true);
      }
      // The threshold edge is still a short press, not a drag.
      auto point=center(panel,8);auto before=bounds(panel.window);int a=actions;
      mouse(panel.window,WM_LBUTTONDOWN,point);
      mouse(panel.window,WM_MOUSEMOVE,{point.x+metric(SM_CXDRAG,dpi),point.y});
      check(bounds(panel.window).left==before.left,"at-threshold jitter moved panel");
      mouse(panel.window,WM_LBUTTONUP,point);check(actions==a+1,"at-threshold short click lost");
    }
  }
  update(9);
  auto candidate=center(panel,8);int a=actions,i=inspections;
  mouse(panel.window,WM_LBUTTONDOWN,candidate);
  auto jitter=bounds(panel.window);POINT no_button{candidate.x+40,candidate.y+20};ScreenToClient(panel.window,&no_button);
  SendMessageW(panel.window,WM_MOUSEMOVE,0,MAKELPARAM(no_button.x,no_button.y));
  check(bounds(panel.window).left==jitter.left,"unheld mouse move dragged panel");
  mouse(panel.window,WM_LBUTTONUP,candidate);check(actions==a+1,"unheld move broke pending short click");a=actions;
  mouse(panel.window,WM_LBUTTONDOWN,candidate);wait_ui(600);
  HWND popup=FindWindowW(L"BihuaStrokeInfoV1",nullptr);check(popup&&IsWindowVisible(popup)&&inspections==i+1,"stationary hold no longer shows strokes");
  auto before=bounds(panel.window);
  mouse(panel.window,WM_MOUSEMOVE,{candidate.x+30,candidate.y+20});
  check(!IsWindowVisible(popup)&&bounds(panel.window).left==before.left+30,"hold-to-drag did not hide popup and move");
  SendMessageW(panel.window,WM_APP+46,0,0);check(!IsWindowVisible(popup),"delayed hold popup reopened during drag");
  mouse(panel.window,WM_LBUTTONUP,{candidate.x+30,candidate.y+20});check(actions==a,"hold-to-drag selected candidate");
  update(9);candidate=center(panel,8);a=actions;i=inspections;
  auto dpi_origin=bounds(panel.window);
  mouse(panel.window,WM_LBUTTONDOWN,candidate);mouse(panel.window,WM_MOUSEMOVE,{candidate.x+30,candidate.y+20});wait_ui(600);
  check(inspections==i&&!IsWindowVisible(popup),"drag before threshold timer still opened info");
  SendMessageW(panel.window,WM_DPICHANGED,MAKELONG(144,144),0);pump();
  mouse(panel.window,WM_MOUSEMOVE,{candidate.x+60,candidate.y+30});
  check(bounds(panel.window).left==dpi_origin.left+60&&bounds(panel.window).top==dpi_origin.top+30,"DPI change interrupted drag");
  mouse(panel.window,WM_LBUTTONUP,{candidate.x+60,candidate.y+30});check(actions==a,"DPI change restored click during drag");
  for(UINT cancellation:{WM_CANCELMODE,WM_CAPTURECHANGED,WM_APP+47}){
    update(9);auto point=center(panel,8);mouse(panel.window,WM_LBUTTONDOWN,point);
    SendMessageW(panel.window,cancellation,0,0);auto origin=bounds(panel.window);a=actions;i=inspections;
    mouse(panel.window,WM_MOUSEMOVE,{point.x+40,point.y+20});wait_ui(550);mouse(panel.window,WM_LBUTTONUP,point);
    check(bounds(panel.window).left==origin.left&&actions==a&&inspections==i,"cancelled gesture resumed");
  }
  update(9);candidate=center(panel,8);mouse(panel.window,WM_LBUTTONDOWN,candidate);
  panel.SetTargetActive(false);pump();before=bounds(panel.window);a=actions;i=inspections;
  mouse(panel.window,WM_MOUSEMOVE,{candidate.x+40,candidate.y+20});mouse(panel.window,WM_LBUTTONUP,candidate);
  check(bounds(panel.window).left==before.left&&actions==a&&inspections==i,"hidden panel retained gesture");
  panel.SetTargetActive(true);update(9);candidate=center(panel,8);
  mouse(panel.window,WM_LBUTTONDOWN,candidate);panel.Update(true,true,style,context,1,{},9,0,++semantic);pump();
  before=bounds(panel.window);a=actions;mouse(panel.window,WM_MOUSEMOVE,{candidate.x+40,candidate.y+20});mouse(panel.window,WM_LBUTTONUP,candidate);
  check(bounds(panel.window).left==before.left&&actions==a,"stale projection retained gesture");
  update(9);auto back=panel.ButtonRect(17);auto panel_bounds=bounds(panel.window);
  POINT preview{back.right+(panel_bounds.right-panel_bounds.left-back.right)/2,(back.top+back.bottom)/2};ClientToScreen(panel.window,&preview);
  drag(preview,30,20,true);
  POINT blank{(panel_bounds.right-panel_bounds.left)/2,2};ClientToScreen(panel.window,&blank);drag(blank,30,20,true);
  panel.SetReady(false);pump();drag(center(panel,0),30,20,true);panel.SetReady(true);pump();
  update(9);registry.position(&saved);registry.fail_writes();
  drag(center(panel,8),30,20);
  POINT unchanged;check(registry.position(&unchanged)&&unchanged.x==saved.x&&unchanged.y==saved.y,"failed registry write changed saved geometry");
  registry.restore_writes();
  update(9);candidate=center(panel,8);registry.position(&saved);
  mouse(panel.window,WM_LBUTTONDOWN,candidate);mouse(panel.window,WM_MOUSEMOVE,{candidate.x+30,candidate.y+20});
  panel.SetTargetActive(false); // Up can arrive before the queued hide is processed.
  mouse(panel.window,WM_LBUTTONUP,{candidate.x+30,candidate.y+20});
  check(registry.position(&unchanged)&&unchanged.x==saved.x&&unchanged.y==saved.y,"stale drag release persisted position");
  panel.SetTargetActive(true);
  update(0);drag(center(panel,0),30,20);check(registry.position(&saved),"restored position persistence");
  {BihuaMousePanel reopened;reopened.Create();auto readback=bounds(reopened.window);check(readback.left==saved.x&&readback.top==saved.y,"new panel did not restore position");}
  check(GetForegroundWindow()==front,"interaction stole foreground");
  std::cout<<"{\"result\":\"PASS\",\"drag_cases\":"<<cases<<",\"DPI\":[96,144,192],\"page_sizes\":[1,3,9],\"short_click_and_stationary_hold_preserved\":true,\"hold_to_drag\":true,\"late_popup_suppressed\":true,\"unheld_move_ignored\":true,\"DPI_change_during_drag\":true,\"cancel_and_hidden_stale_gesture\":true,\"no_activation_input_or_view_changes\":true,\"isolated_position_persistence_and_failure\":true,\"new_panel_restores_position\":true}";
  return 0;
 }catch(const std::exception& e){std::cerr<<"{\"result\":\"FAIL\",\"error\":\""<<e.what()<<"\"}";return 1;}
}
