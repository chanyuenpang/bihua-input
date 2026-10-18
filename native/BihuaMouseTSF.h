#pragma once
#include "EditSession.h"
#include <inputscope.h>

class CBihuaSelectionSession : public CEditSession {
 public:
  CBihuaSelectionSession(WeaselTSF* service,com_ptr<ITfContext> context):CEditSession(service,context){}
  ~CBihuaSelectionSession(){_pTextService->_FinishMouseSelection();}
  STDMETHODIMP DoEditSession(TfEditCookie ec) override{return _pTextService->_ReadMouseSelection(_pContext,ec);}
};

class CBihuaMouseEditSession : public CEditSession {
 public:
  CBihuaMouseEditSession(WeaselTSF* service,com_ptr<ITfContext> context,DWORD token)
      :CEditSession(service,context),token(token){}
  ~CBihuaMouseEditSession(){if(!ran)_pTextService->_FinishMouseAction(token);}
  STDMETHODIMP DoEditSession(TfEditCookie ec) override {
    ran=true;return _pTextService->_RunMouseAction(token,_pContext,ec);
  }
 private:DWORD token;bool ran=false;
};

static LRESULT CALLBACK BihuaMouseTargetProc(HWND hwnd,UINT message,WPARAM wp,LPARAM lp){
  auto service=reinterpret_cast<WeaselTSF*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
  if(message==WM_NCCREATE){service=static_cast<WeaselTSF*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(service));}
  if(service&&message==RegisterWindowMessageW(L"Bihua.MouseAction.V1")){service->_WakeMouseAction();return 0;}
  if(service&&message==RegisterWindowMessageW(L"Bihua.MouseMode.V1")){service->_WakeMouseMode();return 0;}
  if(service&&message==WM_APP+82){service->_RefreshMouseFocus();return 0;}
  if(service&&message==WM_TIMER&&wp==82&&service->MousePanelEnabled()){
    service->_RefreshMouseFocus();return 0;
  }
  return DefWindowProcW(hwnd,message,wp,lp);
}
void WeaselTSF::_InitMouseTarget(){
  WNDCLASSW wc{};wc.lpfnWndProc=BihuaMouseTargetProc;wc.hInstance=g_hInst;wc.lpszClassName=L"BihuaMouseTargetV1";
  RegisterClassW(&wc);
  _mouseWindow=CreateWindowExW(0,wc.lpszClassName,L"",0,0,0,0,0,HWND_MESSAGE,nullptr,g_hInst,this);
  if(_mouseWindow)ChangeWindowMessageFilterEx(_mouseWindow,RegisterWindowMessageW(L"Bihua.MouseAction.V1"),MSGFLT_ALLOW,nullptr);
  if(_mouseWindow)ChangeWindowMessageFilterEx(_mouseWindow,RegisterWindowMessageW(L"Bihua.MouseMode.V1"),MSGFLT_ALLOW,nullptr);
  // Dynamic readonly flags need not generate a TSF focus event. Poll only on
  // the owning UI thread, and send IPC only when the writable context changes.
  if(_mouseWindow)SetTimer(_mouseWindow,82,150,nullptr);
}
com_ptr<ITfContext> WeaselTSF::_MouseContext(){
  com_ptr<ITfContext> context;com_ptr<ITfDocumentMgr> document;
  DWORD pid=0;GetWindowThreadProcessId(GetForegroundWindow(),&pid);
  if(!_mouseOwnActive||!_pThreadMgr||pid!=GetCurrentProcessId()||_IsKeyboardDisabled()||!_IsKeyboardOpen())return context;
  GUITHREADINFO info{sizeof(info)};
  if(!GetGUIThreadInfo(GetCurrentThreadId(),&info)||!info.hwndFocus)return context;
  if(FAILED(_pThreadMgr->GetFocus(&document))||!document||FAILED(document->GetTop(&context))||!context)return nullptr;
  TF_STATUS status{};
  if(FAILED(context->GetStatus(&status))||(status.dwDynamicFlags&TF_SD_READONLY))return nullptr;
  return context;
}
void WeaselTSF::_RefreshMouseFocus(){
  if(!_mouseWindow||!_pThreadMgr)return;
  if(GetCurrentThreadId()!=GetWindowThreadProcessId(_mouseWindow,nullptr)){PostMessageW(_mouseWindow,WM_APP+82,0,0);return;}
  _ObserveMouseSelection();
  auto context=_MouseContext();
  if(!context){_mouseKeyboard.CancelGesture();if(_mouseContext)m_client.FocusOut();_mouseContext=nullptr;_SyncMouseMode();return;}
  if(context!=_mouseContext){m_client.FocusOut();_mouseContext=context;m_client.FocusIn();_mouseModeDirty=true;}
  _SyncMouseMode();
}
void WeaselTSF::_ObserveMouseSelection(){
  if(!_mousePanelEnabled||!_mouseSelectionEnabled||!_mouseOwnActive||_mouseSelectionPending||_IsKeyboardDisabled())return;
  DWORD pid=0;GetWindowThreadProcessId(GetForegroundWindow(),&pid);if(pid!=GetCurrentProcessId())return;
  com_ptr<ITfDocumentMgr> document;com_ptr<ITfContext> context;
  if(FAILED(_pThreadMgr->GetFocus(&document))||!document||FAILED(document->GetTop(&context))||!context)return;
  _mouseSelectionPending=true;
  com_ptr<CBihuaSelectionSession> edit;edit.Attach(new CBihuaSelectionSession(this,context));
  HRESULT result=E_FAIL;
  if(FAILED(context->RequestEditSession(_tfClientId,edit,TF_ES_ASYNCDONTCARE|TF_ES_READ,&result))||FAILED(result))_mouseSelectionPending=false;
}
HRESULT WeaselTSF::_ReadMouseSelection(com_ptr<ITfContext> context,TfEditCookie ec){
  if(!_mouseOwnActive||!_mouseSelectionEnabled||_IsKeyboardDisabled())return S_OK;
  DWORD pid=0;GetWindowThreadProcessId(GetForegroundWindow(),&pid);if(pid!=GetCurrentProcessId())return S_OK;
  com_ptr<ITfDocumentMgr> document;com_ptr<ITfContext> current;
  if(FAILED(_pThreadMgr->GetFocus(&document))||!document||FAILED(document->GetTop(&current))||current!=context)return S_OK;
  TF_SELECTION selection{};ULONG fetched=0;
  if(FAILED(context->GetSelection(ec,TF_DEFAULT_SELECTION,1,&selection,&fetched))||!fetched)return S_OK;
  com_ptr<ITfRange> range;range.Attach(selection.range);
  com_ptr<ITfProperty> property;
  static const GUID input_scope={0x1713dd5a,0x68e7,0x4a5b,{0x9a,0xf6,0x59,0x2a,0x59,0x5c,0x77,0x8d}};
  if(SUCCEEDED(context->GetProperty(input_scope,&property))&&property){
    VARIANT value;VariantInit(&value);HRESULT result=property->GetValue(ec,range,&value);
    if(FAILED(result)){VariantClear(&value);return S_OK;}
    bool password=false;
    if(value.vt==VT_UNKNOWN&&value.punkVal){
      com_ptr<ITfInputScope> scope;
      if(SUCCEEDED(value.punkVal->QueryInterface(IID_ITfInputScope,reinterpret_cast<void**>(&scope)))&&scope){
        InputScope* items=nullptr;UINT count=0;
        if(SUCCEEDED(scope->GetInputScopes(&items,&count))){for(UINT i=0;i<count;++i)if(items[i]==IS_PASSWORD)password=true;CoTaskMemFree(items);}
      }
    }
    VariantClear(&value);if(password)return S_OK;
  }
  wchar_t text[3]{};ULONG count=0;
  if(FAILED(range->GetText(ec,0,text,3,&count)))return S_OK;
  uint32_t cp=0;
  if(count==1)cp=text[0];
  else if(count==2&&text[0]>=0xd800&&text[0]<=0xdbff&&text[1]>=0xdc00&&text[1]<=0xdfff)cp=0x10000+((text[0]-0xd800)<<10)+(text[1]-0xdc00);
  if(!((cp>=0x3400&&cp<=0x9fff)||(cp>=0xf900&&cp<=0xfaff)||(cp>=0x20000&&cp<=0x323af)))cp=0;
  if(cp!=_mouseSelectedScalar){_mouseSelectedScalar=cp;if(cp)m_client.MouseSelectedScalar(cp);}
  return S_OK;
}
void WeaselTSF::_SyncMouseMode(){
  if(_mouseKeyboard.Caps((GetKeyState(VK_CAPITAL)&1)!=0))_mouseModeDirty=true;
  if(_mouseModeDirty&&_mousePanelEnabled&&_mouseOwnActive&&
     m_client.MouseKeyboardMode(static_cast<DWORD>(_mouseKeyboard.mode)))_mouseModeDirty=false;
}
void WeaselTSF::_WakeMouseMode(){
  if(!_mousePanelEnabled||!_mouseOwnActive||!m_client.TakeMouseModeToggle())return;
  _mouseKeyboard.Toggle((GetKeyState(VK_CAPITAL)&1)!=0);_mouseKeyboard.CancelGesture();_mouseModeDirty=true;_SyncMouseMode();
}
bool WeaselTSF::_RouteMouseKey(WPARAM key,LPARAM info,BOOL* eaten,int phase){
  if(!_mousePanelEnabled||!_mouseOwnActive){_mouseKeyboard.Reset();return false;}
  if(key==VK_RETURN){*eaten=FALSE;return true;}
  _RefreshMouseFocus();
  const bool down=phase<2;
  const bool ctrl=(GetKeyState(VK_CONTROL)&0x8000)!=0;
  const bool alt=(GetKeyState(VK_MENU)&0x8000)!=0;
  const bool win=(GetKeyState(VK_LWIN)&0x8000)||(GetKeyState(VK_RWIN)&0x8000);
  const bool shifted=(GetKeyState(VK_SHIFT)&0x8000)!=0;
  if(phase==0||phase==1)m_client.MouseView(0);
  if(key==VK_SHIFT||key==VK_LSHIFT||key==VK_RSHIFT){
    uint32_t side=key==VK_SHIFT?(((info>>16)&255)==0x36?VK_RSHIFT:VK_LSHIFT):static_cast<uint32_t>(key);
    if(_mouseKeyboard.Shift(side,down,ctrl||alt||win,(GetKeyState(VK_CAPITAL)&1)!=0)){_mouseModeDirty=true;_SyncMouseMode();}
    _fTestKeyDownPending=_fTestKeyUpPending=FALSE;
    *eaten=FALSE;return true;
  }
  if(down)_mouseKeyboard.OtherDown();
  if(key==VK_TAB){
    _fTestKeyDownPending=_fTestKeyUpPending=FALSE;
    *eaten=FALSE;return true;
  }
  if(key==VK_CAPITAL){_SyncMouseMode();*eaten=FALSE;return true;}
  if(_mouseKeyboard.English()){
    if(key<256&&!down)_mouseViewKeys[key]=false;
    _fTestKeyDownPending=_fTestKeyUpPending=FALSE;
    *eaten=FALSE;return true;
  }
  if(ctrl||alt||win||shifted||_mouseKeyboard.shift||key==VK_CONTROL||key==VK_MENU||key==VK_LWIN||key==VK_RWIN){
    *eaten=FALSE;return true;
  }
  if(key<256&&!down&&_mouseViewKeys[key]){
    if(phase==3)_mouseViewKeys[key]=false;
    *eaten=TRUE;return true;
  }
  bool direction=key>=VK_LEFT&&key<=VK_DOWN;
  bool confirmation=key==VK_SPACE||key==VK_NUMPAD0;
  if(down&&!ctrl&&!alt&&!win&&!shifted&&(direction||confirmation)){
    DWORD flags=m_client.MouseView(6);
    if((flags&1)&&((direction&&(flags&2))||(confirmation&&(flags&4)))){
      _mouseViewKeys[key]=true;
      if(phase==1){
        DWORD command=key==VK_LEFT?1:key==VK_RIGHT?2:key==VK_UP?3:key==VK_DOWN?4:5;
        m_client.MouseView(command);
      }
      _fTestKeyDownPending=_fTestKeyUpPending=FALSE;
      *eaten=TRUE;return true;
    }
  }
  return false;
}
void WeaselTSF::_WakeMouseAction(){
  auto context=_MouseContext();
  if(!context){m_client.FocusOut();return;}
  DWORD token=m_client.TakeMouseAction();if(!token)return;
  com_ptr<CBihuaMouseEditSession> edit;
  edit.Attach(new CBihuaMouseEditSession(this,context,token));
  HRESULT result=E_FAIL;
  HRESULT request=context->RequestEditSession(_tfClientId,edit,TF_ES_ASYNCDONTCARE|TF_ES_READWRITE,&result);
  if(FAILED(request)||FAILED(result))m_client.FinishMouseAction(token);
}
void WeaselTSF::_FinishMouseAction(DWORD token){m_client.FinishMouseAction(token);}
HRESULT WeaselTSF::_RunMouseAction(DWORD token,com_ptr<ITfContext> context,TfEditCookie ec){
  auto current=_MouseContext();
  if(!current||current!=context){m_client.FinishMouseAction(token);m_client.FocusOut();return TF_E_DISCONNECTED;}
  com_ptr<ITfRange> range;
  com_ptr<ITfInsertAtSelection> insert;
  HRESULT result=context->QueryInterface(IID_ITfInsertAtSelection,reinterpret_cast<void**>(&insert));
  if(SUCCEEDED(result))result=insert->InsertTextAtSelection(ec,TF_IAS_QUERYONLY,L"",0,&range);
  if(SUCCEEDED(result)&&_pComposition){
    if(_pEditSessionContext!=context)result=TF_E_DISCONNECTED;
    else result=_pComposition->GetRange(&range);
  }
  if(FAILED(result)||!range){m_client.FinishMouseAction(token);return FAILED(result)?result:E_FAIL;}
  if(!m_client.ExecuteMouseAction(token)){m_client.FinishMouseAction(token);return E_FAIL;}
  std::wstring commit;weasel::Context projection;weasel::Config config;
  weasel::ResponseParser parser(&commit,&projection,&_status,&config,&_cand->style());
  if(!m_client.GetResponseData(std::ref(parser))){m_client.FinishMouseAction(token);m_client.FocusOut();return E_FAIL;}
  _mousePanelEnabled=config.mouse_panel_enabled;
  _mouseSelectionEnabled=config.mouse_selection_enabled;
  if(!commit.empty()||(!_status.composing&&_pComposition)){
    result=range->SetText(ec,0,commit.c_str(),static_cast<LONG>(commit.size()));
    if(SUCCEEDED(result)){
      range->Collapse(ec,TF_ANCHOR_END);
      TF_SELECTION selection{};selection.range=range;selection.style.ase=TF_AE_NONE;
      result=context->SetSelection(ec,1,&selection);
    }
    if(SUCCEEDED(result)&&_pComposition){
      _endingMouseComposition=true;
      _ClearCompositionDisplayAttributes(ec,context);
      result=_pComposition->EndComposition(ec);
      _FinalizeComposition();_endingMouseComposition=false;
      _cand->EndUI();
    }
    _committed=!commit.empty();
  }
  _UpdateLanguageBar(_status);_UpdateUI(projection,_status);
  m_client.FinishMouseAction(token);
  if(FAILED(result)){OutputDebugStringW(L"Bihua mouse text write failed; action will not replay.\n");m_client.FocusOut();}
  return result;
}
