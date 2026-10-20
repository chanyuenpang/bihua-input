// Included in the handler translation unit, within the existing API serial region.
DWORD RimeWithWeaselHandler::PhysicalKeyEvent(const BihuaPhysicalEventV1& event,DWORD session,EatLine eat,bool query){
  std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
  if(!event.Valid()||m_disabled||m_session_status_map.find(session)==m_session_status_map.end())return 0;
  weasel::KeyEvent legacy(event.rime);
  auto fallback=[&](){if(legacy.keycode)return static_cast<DWORD>(ProcessKeyEvent(legacy,session,eat));_Respond(session,eat);return DWORD(0);};
  auto& held=m_physical_keys[session];
  auto id=(event.scan?event.scan:512+event.vk)+((event.flags&1)?256:0);
  if(!query&&(event.flags&BihuaPhysicalEventV1::Up)&&held[id]){held[id]=false;_Respond(session,eat);return 1;}
  auto profile=m_mouse_profiles.find(session);
  bool eligible=_KeyboardTargetValid()&&m_mouse_state.session==session&&
      profile!=m_mouse_profiles.end()&&profile->second.mode<=0&&
      !rime_api->get_option(to_session_id(session),"ascii_mode")&&
      !(legacy.mask&~(ibus::LOCK_MASK|ibus::RELEASE_MASK));
  int action=eligible?m_keyboard_bindings.Resolve(event,query):-1;
  char symbols[8]{};rime_api->get_property(to_session_id(session),"bihua_symbol_active",symbols,sizeof(symbols));
  if(symbols[0]=='1'&&action!=7){if(query)return 0;return fallback();}
  if(query)return action>=0?1:0;
  if(action<0)return fallback();
  if(event.flags&BihuaPhysicalEventV1::Up){_Respond(session,eat);return 0;}
  bool repeated=held[id];held[id]=true;
  if(action==7&&repeated){_Respond(session,eat);return 1;}
  _BeforeMouseMutation(session);
  const char* names[]={"h","s","p","n","z","wildcard","separator","symbol_toggle"};
  auto rime=to_session_id(session);
  rime_api->set_property(rime,"bihua_mouse_action",names[action]);
  rime_api->process_key(rime,0xffd5,0);
  rime_api->set_property(rime,"bihua_mouse_action","");
  _Respond(session,eat);_UpdateUI(session);m_active_session=session;return 1;
}
