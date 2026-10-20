// Included after RimeWithWeasel.cpp's implementation. All Rime calls use the
// existing API serial region; UI callbacks only queue intent/exposure metadata.
DWORD RimeWithWeaselHandler::_MouseProfileSession() {
  HDESK desktop=OpenInputDesktop(0,FALSE,DESKTOP_READOBJECTS);
  if(!desktop)return 0;
  wchar_t name[80]{};DWORD bytes=0;
  bool normal=GetUserObjectInformationW(desktop,UOI_NAME,name,sizeof(name),&bytes)&&!wcscmp(name,L"Default");
  CloseDesktop(desktop);if(!normal)return 0;
  DWORD pid=0;DWORD thread=GetWindowThreadProcessId(GetForegroundWindow(),&pid);
  GUITHREADINFO info{sizeof(info)};
  if(thread&&GetGUIThreadInfo(thread,&info)&&info.hwndFocus){
    DWORD focus_pid=0;auto focus_thread=GetWindowThreadProcessId(info.hwndFocus,&focus_pid);
    if(focus_pid==pid)thread=focus_thread;
  }
  for(auto it=m_mouse_profiles.rbegin();it!=m_mouse_profiles.rend();++it)
    if(it->second.pid==pid&&it->second.thread==thread){
      if(!it->second.active)return 0;
      m_mouse_mode_session=it->first;return it->first;
    }
  for(auto it=m_mouse_profiles.rbegin();it!=m_mouse_profiles.rend();++it)
    if(it->second.pid==pid&&it->second.active){m_mouse_mode_session=it->first;return it->first;}
  // A toolbar, read-only document or desktop has no writable context. Keep
  // the last live active profile, rather than confusing absence with deactivation.
  auto last=m_mouse_profiles.find(m_mouse_mode_session);
  auto window=m_mouse_targets.find(m_mouse_mode_session);
  return last!=m_mouse_profiles.end()&&last->second.active&&window!=m_mouse_targets.end()&&IsWindow(window->second)?m_mouse_mode_session:0;
}
bool RimeWithWeaselHandler::_MouseProfileVisible(){return _MouseProfileSession()!=0;}
bool RimeWithWeaselHandler::_KeyboardTargetValid() {
  if(m_disabled||!m_mouse_state.session)return false;
  auto target=m_mouse_targets.find(m_mouse_state.session);
  if(target==m_mouse_targets.end()||!IsWindow(target->second))return false;
  DWORD pid=0,front=0;
  GetWindowThreadProcessId(target->second,&pid);
  GetWindowThreadProcessId(GetForegroundWindow(),&front);
  auto profile=m_mouse_profiles.find(m_mouse_state.session);
  GUITHREADINFO info{sizeof(info)};auto thread=GetWindowThreadProcessId(GetForegroundWindow(),nullptr);
  return pid&&pid==front&&profile!=m_mouse_profiles.end()&&profile->second.active&&
      GetGUIThreadInfo(thread,&info)&&info.hwndFocus&&
      GetWindowThreadProcessId(info.hwndFocus,nullptr)==profile->second.thread&&
      BihuaPersonalKeyCapture::SafeForeground(GetForegroundWindow());
}
bool RimeWithWeaselHandler::_MouseTargetValid(){return m_mouse_enabled&&_KeyboardTargetValid();}
bool RimeWithWeaselHandler::_MouseHeartbeat() {
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(!m_mouse_panel)return false;
  _UpdateNumLock();
  m_mouse_panel->SetProfileActive(_MouseProfileVisible());
  auto mode_session=_MouseProfileSession();auto mode=m_mouse_profiles.find(mode_session);
  m_mouse_panel->SetModeAvailable(mode_session!=0);
  if(mode!=m_mouse_profiles.end())m_mouse_panel->SetKeyboardMode(mode->second.mode);
  if(!m_mouse_enabled){m_mouse_panel->SetTargetActive(false);return false;}
  if(m_mouse_state.session&&(!_MouseTargetValid()||
       (m_mouse_state.token&&GetTickCount64()-m_mouse_state.queued_at>3000))){
    m_mouse_state.Focus(0);m_mouse_exposure={};
    m_mouse_view.Sync(m_mouse_state.generation,m_mouse_state.projection,0,9,0,0);
    m_mouse_candidates.clear();m_mouse_base=0;m_mouse_more=false;
    m_mouse_panel->Update(true,false,m_base_style,weasel::Context{});
  }
  bool target=_MouseTargetValid()&&!m_mouse_ascii;
  m_mouse_panel->SetTargetActive(target);
  return target;
}
void RimeWithWeaselHandler::_UpdateMouse(DWORD session) {
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  _UpdateNumLock();
  if(!m_mouse_panel)return;
  m_mouse_panel->SetProfileActive(_MouseProfileVisible());
  weasel::Context context;auto style=m_base_style;
  bool ready=_MouseTargetValid();
  if(session!=0&&session!=m_mouse_state.session)return;
  m_mouse_candidates.clear();m_mouse_base=0;m_mouse_page_size=9;m_mouse_more=false;
  if(ready){
    session=m_mouse_state.session;
    auto found=m_session_status_map.find(session);
    if(found!=m_session_status_map.end()){
      style=found->second.style;
      weasel::Status status;_GetStatus(status,session,context);
      m_mouse_ascii=status.ascii_mode;
      if(!m_mouse_ascii){
        _GetContext(context,found->second.session_id);
        RIME_STRUCT(RimeContext,raw);
        if(rime_api->get_context(found->second.session_id,&raw)){
          m_mouse_page_size=std::clamp(raw.menu.page_size,1,9);
          m_mouse_base=raw.menu.page_no*m_mouse_page_size;
          rime_api->free_context(&raw);
          RimeCandidateListIterator it{};
          if(rime_api->candidate_list_from_index(found->second.session_id,&it,m_mouse_base)){
            while(m_mouse_candidates.size()<=static_cast<size_t>(5*m_mouse_page_size)&&rime_api->candidate_list_next(&it)){
              if(it.index!=m_mouse_base+static_cast<int>(m_mouse_candidates.size()))break;
              if(m_mouse_candidates.size()==static_cast<size_t>(5*m_mouse_page_size)){m_mouse_more=true;break;}
              m_mouse_candidates.push_back(u8tow(it.candidate.text?it.candidate.text:""));
            }
            rime_api->candidate_list_end(&it);
          }
        }
      }
    }else ready=false;
  }
  m_mouse_panel->SetTargetActive(ready&&!m_mouse_ascii);
  m_mouse_view.Sync(m_mouse_state.generation,m_mouse_state.projection,m_mouse_base,m_mouse_page_size,
      static_cast<int>(m_mouse_candidates.size()),context.cinfo.highlighted,m_mouse_more);
  if(!m_mouse_arrows)m_mouse_view.DisableNavigation();
  m_mouse_panel->Update(m_mouse_enabled,ready&&!m_mouse_ascii&&!m_mouse_state.token,
      style,context,m_mouse_state.generation,m_mouse_candidates,m_mouse_page_size,
      m_mouse_base,m_mouse_state.projection,m_mouse_view.expanded,m_mouse_view.navigation,
      m_mouse_view.revision,m_mouse_info,m_mouse_more);
  auto mode_session=_MouseProfileSession();auto profile=m_mouse_profiles.find(mode_session);
  m_mouse_panel->SetModeAvailable(mode_session!=0);
  m_mouse_panel->SetKeyboardMode(profile==m_mouse_profiles.end()?-1:profile->second.mode);
}
bool RimeWithWeaselHandler::_KeypadNavigate(const weasel::KeyEvent& key,DWORD session,EatLine eat){
  bool previous=key.keycode==ibus::KP_Divide&&m_keypad_previous;
  bool next=key.keycode==ibus::KP_Multiply&&m_keypad_next;
  if((!previous&&!next)||(key.mask&~(ibus::RELEASE_MASK|ibus::LOCK_MASK)))return false;
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(!m_mouse_arrows||!_MouseTargetValid()||m_mouse_ascii||session!=m_mouse_state.session||!m_mouse_view.count)return false;
  if(!(key.mask&ibus::RELEASE_MASK))MouseCommand(WEASEL_IPC_MOUSE_VIEW,previous?1:2,session,eat);
  _Respond(session,eat);
  return true;
}
void RimeWithWeaselHandler::_UpdateNumLock(){
  auto session=_MouseProfileSession();auto profile=m_mouse_profiles.find(session);
  HWND front=GetForegroundWindow();DWORD pid=0;auto thread=GetWindowThreadProcessId(front,&pid);
  GUITHREADINFO info{sizeof(info)};
  bool valid=!m_disabled&&session&&session==m_mouse_state.session&&
      profile!=m_mouse_profiles.end()&&profile->second.active&&profile->second.pid==pid&&
      GetGUIThreadInfo(thread,&info)&&info.hwndFocus;
  DWORD focus_pid=0;auto focus_thread=info.hwndFocus?GetWindowThreadProcessId(info.hwndFocus,&focus_pid):0;
  valid=valid&&focus_pid==pid&&focus_thread==profile->second.thread;
  valid=valid&&BihuaPersonalKeyCapture::SafeForeground(front);
  m_numlock.Publish(valid?front:nullptr,valid?info.hwndFocus:nullptr,m_mouse_state.generation);
}
bool RimeWithWeaselHandler::_QueueKeyboardAction(int action,uint32_t generation){
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(!_KeyboardTargetValid()||m_mouse_ascii||(generation&&generation!=m_mouse_state.generation))return false;
  auto profile=m_mouse_profiles.find(m_mouse_state.session);
  if(action!=BihuaMouseState::SymbolCancel&&
     (profile==m_mouse_profiles.end()||profile->second.mode>0||m_mouse_panel&&m_mouse_panel->PersonalDraft()))return false;
  auto token=m_mouse_state.Queue(action,GetTickCount64(),m_mouse_state.generation,m_mouse_state.projection);
  if(!token)return false;
  m_mouse_pending_view=0;
  auto target=m_mouse_targets.find(m_mouse_state.session);
  if(target==m_mouse_targets.end()||!PostMessageW(target->second,RegisterWindowMessageW(L"Bihua.MouseAction.V1"),0,0)){
    m_mouse_state.Reset();return false;
  }
  if(m_mouse_enabled&&m_mouse_panel)m_mouse_panel->SetReady(false);
  return true;
}
void RimeWithWeaselHandler::_NumLockPressed(const KBDLLHOOKSTRUCT& key,uint64_t generation){
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  BihuaPhysicalEventV1 event;event.vk=key.vkCode;event.scan=key.scanCode;
  event.flags=(key.flags&LLKHF_EXTENDED)?1:0;event.rime=0xff7f;
  int action=m_keyboard_bindings.Resolve(event);
  if(action<0)return;
  _QueueKeyboardAction(action<6?action:action==6?BihuaMouseState::Separator:BihuaMouseState::SymbolToggle,static_cast<uint32_t>(generation));
}
void RimeWithWeaselHandler::_MouseDisplayed(DWORD generation,uint64_t revision,int first,int count){
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(!_MouseTargetValid()||m_mouse_ascii||generation!=m_mouse_state.generation||
     revision!=m_mouse_state.projection||first!=m_mouse_base||count<1||
     count>static_cast<int>(m_mouse_candidates.size()))return;
  // A later collapse never erases already exposed rows in this projection.
  if(m_mouse_exposure.session==m_mouse_state.session&&m_mouse_exposure.revision==revision)
    count=(std::max)(count,m_mouse_exposure.count);
  m_mouse_exposure={m_mouse_state.session,generation,revision,first,count};
}
void RimeWithWeaselHandler::_BeforeMouseMutation(DWORD session){
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  auto exposure=m_mouse_exposure;
  if(session==m_mouse_state.session){
    m_mouse_exposure={};
    if(exposure.session==session&&exposure.generation==m_mouse_state.generation&&
       exposure.revision==m_mouse_state.projection&&_MouseTargetValid()&&!m_mouse_ascii){
      auto rime=to_session_id(session);
      rime_api->set_property(rime,"bihua_mouse_expose_first",std::to_string(exposure.first).c_str());
      rime_api->set_property(rime,"bihua_mouse_expose_count",std::to_string(exposure.count).c_str());
      rime_api->set_property(rime,"bihua_mouse_action","expose");
      rime_api->process_key(rime,0xffd5,0);
      rime_api->set_property(rime,"bihua_mouse_action","");
    }
    m_mouse_state.InvalidateProjection();
  }
}
void RimeWithWeaselHandler::_QueueMouseAction(int action,int index,DWORD displayed_generation,uint64_t revision,uint64_t view) {
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(action==21){
    DWORD owner=_MouseProfileSession();auto target=m_mouse_targets.find(owner);
    if(!m_mouse_enabled||!owner||target==m_mouse_targets.end()||
       displayed_generation!=m_mouse_state.generation||revision!=m_mouse_state.projection||view!=m_mouse_view.revision)return;
    m_mouse_mode_token=++m_mouse_mode_serial;if(!m_mouse_mode_token)m_mouse_mode_token=++m_mouse_mode_serial;
    m_mouse_mode_owner=owner;m_mouse_mode_at=GetTickCount64();
    if(!PostMessageW(target->second,RegisterWindowMessageW(L"Bihua.MouseMode.V1"),0,0))m_mouse_mode_token=0;
    return;
  }
  if(!_MouseTargetValid()||m_mouse_ascii||displayed_generation!=m_mouse_state.generation||
     revision!=m_mouse_state.projection||view!=m_mouse_view.revision)return;
  if(action==20){
    if(m_mouse_state.token&&!m_mouse_state.executed)m_mouse_state.Reset();
    m_mouse_view.Toggle();m_mouse_panel->SetReady(!m_mouse_state.token);
    m_mouse_panel->SetView(m_mouse_view.expanded,m_mouse_view.navigation,m_mouse_view.revision);return;
  }
  if((action==BihuaMouseState::Candidate||action==19)&&(index<m_mouse_base||index>=m_mouse_base+static_cast<int>(m_mouse_candidates.size())))return;
  if(action==19){
    if(m_mouse_info)m_mouse_panel->ShowInformation(m_mouse_strokes.Describe(m_mouse_candidates[index-m_mouse_base]),
        displayed_generation,revision,view);
    return;
  }
  if((action==6&&m_mouse_base==0)||(action==7&&!m_mouse_more))return;
  DWORD token=m_mouse_state.Queue(action,GetTickCount64(),displayed_generation,revision,index);
  if(!token)return;
  m_mouse_pending_view=view;
  HWND target=m_mouse_targets[m_mouse_state.session];
  if(!PostMessageW(target,RegisterWindowMessageW(L"Bihua.MouseAction.V1"),0,0)){
    m_mouse_state.Focus(0);m_mouse_exposure={};m_mouse_panel->SetTargetActive(false);
  }else m_mouse_panel->SetReady(false);
}
DWORD RimeWithWeaselHandler::MouseCommand(WEASEL_IPC_COMMAND command,DWORD value,DWORD session,EatLine eat) {
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(m_disabled||m_session_status_map.find(session)==m_session_status_map.end())return 0;
  if(command==WEASEL_IPC_MOUSE_SELECTION){
    if(!m_mouse_selection||session!=_MouseProfileSession()||!BihuaPersonalRecorder::SingleHan(BihuaPersonalRecorder::FromScalar(value)))return 0;
    m_mouse_panel->ObserveSelection(value);return 1;
  }
  if(command==WEASEL_IPC_MOUSE_MODE_TAKE){
    if(!m_mouse_mode_token||session!=m_mouse_mode_owner||session!=_MouseProfileSession()||GetTickCount64()-m_mouse_mode_at>1500){m_mouse_mode_token=0;return 0;}
    auto token=m_mouse_mode_token;m_mouse_mode_token=0;return token;
  }
  if(command==WEASEL_IPC_MOUSE_KEYBOARD_MODE){
    auto profile=m_mouse_profiles.find(session);
    if(value>2||profile==m_mouse_profiles.end())return 0;
    profile->second.mode=static_cast<int>(value);
    if(value>0){
      m_physical_keys.erase(session);
      rime_api->set_property(to_session_id(session),"bihua_mouse_action","symbol_cancel");
      rime_api->process_key(to_session_id(session),0xffd5,0);
      rime_api->set_property(to_session_id(session),"bihua_mouse_action","");
      _UpdateMouse(session);
    }
    if(session==_MouseProfileSession())m_mouse_panel->SetKeyboardMode(static_cast<int>(value));
    return 1;
  }
  if(command==WEASEL_IPC_MOUSE_VIEW){
    if(!_MouseTargetValid()||m_mouse_ascii||session!=m_mouse_state.session)return 0;
    if(value==0){m_mouse_panel->CancelPointer();}
    if(value>=1&&value<=4&&m_mouse_arrows&&m_mouse_view.count){
      if(m_mouse_state.token&&!m_mouse_state.executed)m_mouse_state.Reset();
      auto move=m_mouse_view.Navigate(value-1);
      if(move==BihuaMouseView::PageUp||move==BihuaMouseView::PageDown){
        _QueueMouseAction(move==BihuaMouseView::PageUp?6:7,m_mouse_view.navigation,
            m_mouse_state.generation,m_mouse_state.projection,m_mouse_view.revision);
        return m_mouse_state.token?1:0;
      }
      m_mouse_panel->SetReady(!m_mouse_state.token);
      m_mouse_panel->SetView(m_mouse_view.expanded,m_mouse_view.navigation,m_mouse_view.revision);return 1;
    }
    if(value==5&&m_mouse_arrows&&m_mouse_view.navigation>=m_mouse_base){
      _QueueMouseAction(BihuaMouseState::Candidate,m_mouse_view.navigation,m_mouse_state.generation,
                        m_mouse_state.projection,m_mouse_view.revision);return m_mouse_state.token?1:0;
    }
    return (m_mouse_arrows?1:0)|(m_mouse_view.count?2:0)|
           (m_mouse_arrows&&m_mouse_view.navigation>=m_mouse_base?4:0);
  }
  if(command==WEASEL_IPC_MOUSE_PROFILE){
    auto item=m_mouse_profiles.find(session);
    if(item==m_mouse_profiles.end())return 0;
    item->second.active=!!value;
    if(!value){m_mouse_state.Blur(session);m_mouse_exposure={};}
    _UpdateMouse(0);return 1;
  }
  if(command==WEASEL_IPC_MOUSE_REGISTER){
    m_mouse_state.Blur(session);m_mouse_exposure={};
    if(value){
      auto target=reinterpret_cast<HWND>(static_cast<UINT_PTR>(value));m_mouse_targets[session]=target;
      DWORD pid=0;DWORD thread=GetWindowThreadProcessId(target,&pid);m_mouse_profiles[session]={pid,thread,true};
    }else{m_mouse_targets.erase(session);m_mouse_profiles.erase(session);}
    _UpdateMouse(0);return 1;
  }
  if(command==WEASEL_IPC_MOUSE_TAKE)return (m_mouse_pending_view?_MouseTargetValid():_KeyboardTargetValid())?m_mouse_state.Take(session):0;
  if(command==WEASEL_IPC_MOUSE_FINISH){
    bool ok=m_mouse_state.Finish(session,value);_UpdateMouse(0);return ok;
  }
  if(command!=WEASEL_IPC_MOUSE_EXECUTE||!(m_mouse_pending_view?_MouseTargetValid():_KeyboardTargetValid()))return 0;
  if(m_mouse_pending_view&&m_mouse_pending_view!=m_mouse_view.revision)return 0;
  int action=m_mouse_state.Execute(session,value,GetTickCount64());
  if(action<0)return 0;
  const int index=m_mouse_state.candidate_index;
  if(action==6||action==7)m_mouse_view.PreparePage(action==7?1:-1,index>=0);
  _BeforeMouseMutation(session);
  auto rime=to_session_id(session);
  if(action<6){
    const char* names[]={"h","s","p","n","z","wildcard"};
    rime_api->set_property(rime,"bihua_mouse_action",names[action]);
    rime_api->process_key(rime,0xffd5,0);
    rime_api->set_property(rime,"bihua_mouse_action","");
  }else if(action==BihuaMouseState::Separator||action==BihuaMouseState::SymbolToggle||action==BihuaMouseState::SymbolCancel){
    const char* name=action==BihuaMouseState::Separator?"separator":action==BihuaMouseState::SymbolToggle?"symbol_toggle":"symbol_cancel";
    rime_api->set_property(rime,"bihua_mouse_action",name);rime_api->process_key(rime,0xffd5,0);rime_api->set_property(rime,"bihua_mouse_action","");
  }else if(action<8)rime_api->process_key(rime,action==6?ibus::Page_Up:ibus::Page_Down,0);
  else if(action==17){
    RIME_STRUCT(RimeContext,ctx);bool pending=false;
    if(rime_api->get_context(rime,&ctx)){pending=ctx.composition.length>0||ctx.menu.num_candidates>0;rime_api->free_context(&ctx);}
    if(pending)rime_api->process_key(rime,ibus::BackSpace,0);
  }else if(action==BihuaMouseState::Candidate){
    std::string input=rime_api->get_input(rime)?rime_api->get_input(rime):"";
    rime_api->set_property(rime,"bihua_explicit_selection","1");
    rime_api->set_property(rime,"bihua_selection_input",input.c_str());
    rime_api->set_property(rime,"bihua_close_after_commit","");
    rime_api->set_property(rime,"bihua_mouse_absolute_selection","1");
    bool selected=rime_api->select_candidate(rime,index);
    rime_api->set_property(rime,"bihua_mouse_absolute_selection","");
    rime_api->set_property(rime,"bihua_explicit_selection","");
    rime_api->set_property(rime,"bihua_selection_input","");
    if(!selected)return 0;
  }
  _Respond(session,eat);_UpdateMouse(session);return 1;
}
