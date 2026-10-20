// Bihua physical event v1
#pragma once
#include <WeaselIPC.h>
#include <WeaselUI.h>
#include <map>
#include <string>

#include <rime_api.h>
#include <BihuaMouseState.h>
#include <BihuaMousePanel.h>
#include <BihuaMouseView.h>
#include <BihuaStrokeInfo.h>
#include <BihuaNumLock.h>
#include <mutex>
#include <atomic>

struct CaseInsensitiveCompare {
  bool operator()(const std::string& str1, const std::string& str2) const {
    std::string str1Lower, str2Lower;
    std::transform(str1.begin(), str1.end(), std::back_inserter(str1Lower),
                   [](char c) { return std::tolower(c); });
    std::transform(str2.begin(), str2.end(), std::back_inserter(str2Lower),
                   [](char c) { return std::tolower(c); });
    return str1Lower < str2Lower;
  }
};

typedef std::map<std::string, bool> AppOptions;
typedef std::map<std::string, AppOptions, CaseInsensitiveCompare>
    AppOptionsByAppName;

struct SessionStatus {
  SessionStatus() : style(weasel::UIStyle()), __synced(false), session_id(0) {
    RIME_STRUCT(RimeStatus, status);
  }
  weasel::UIStyle style;
  RimeStatus status;
  bool __synced;
  RimeSessionId session_id;
};
typedef std::map<DWORD, SessionStatus> SessionStatusMap;
typedef DWORD WeaselSessionId;
class RimeWithWeaselHandler : public weasel::RequestHandler {
 public:
  RimeWithWeaselHandler(weasel::UI* ui);
  virtual ~RimeWithWeaselHandler();
  bool ActivateBihua();
  virtual void Initialize();
  virtual void Finalize();
  virtual DWORD FindSession(WeaselSessionId ipc_id);
  virtual DWORD AddSession(LPWSTR buffer, EatLine eat = 0);
  virtual DWORD RemoveSession(WeaselSessionId ipc_id);
  virtual BOOL ProcessKeyEvent(weasel::KeyEvent keyEvent,
                               WeaselSessionId ipc_id,
                               EatLine eat);
  virtual void CommitComposition(WeaselSessionId ipc_id);
  virtual void ClearComposition(WeaselSessionId ipc_id);
  virtual void SelectCandidateOnCurrentPage(size_t index,
                                            WeaselSessionId ipc_id);
  virtual bool HighlightCandidateOnCurrentPage(size_t index,
                                               WeaselSessionId ipc_id,
                                               EatLine eat);
  virtual bool ChangePage(bool backward, WeaselSessionId ipc_id, EatLine eat);
  virtual DWORD MouseCommand(WEASEL_IPC_COMMAND command,DWORD value,DWORD session,EatLine eat);
  virtual void FocusIn(DWORD param, WeaselSessionId ipc_id);
  virtual void FocusOut(DWORD param, WeaselSessionId ipc_id);
  virtual void UpdateInputPosition(RECT const& rc, WeaselSessionId ipc_id);
  virtual void StartMaintenance();
  virtual void EndMaintenance();
  virtual void SetOption(WeaselSessionId ipc_id,
                         const std::string& opt,
                         bool val);
  virtual void UpdateColorTheme(BOOL darkMode);

  void OnUpdateUI(std::function<void()> const& cb);

 private:
  virtual DWORD PhysicalKeyEvent(const BihuaPhysicalEventV1& event,DWORD session,EatLine eat,bool query) override;
  std::map<DWORD,std::array<bool,1024>> m_physical_keys;
  bool _KeyboardTargetValid();
  void _Setup();
  void _QueueMouseAction(int action,int index,DWORD displayed_generation,uint64_t revision,uint64_t view);
  void _MouseDisplayed(DWORD generation,uint64_t revision,int first,int count);
  void _BeforeMouseMutation(DWORD session);
  void _UpdateNumLock();
  bool _KeypadNavigate(const weasel::KeyEvent& key,DWORD session,EatLine eat);
  bool m_keypad_previous=true,m_keypad_next=true;
  BihuaNumLockGuard m_numlock;
  BihuaPersonalKeyMap m_keyboard_bindings;
  bool _QueueKeyboardAction(int action,uint32_t generation);
  void _NumLockPressed(const KBDLLHOOKSTRUCT& key,uint64_t generation);
  void _UpdateMouse(DWORD session);
  bool _MouseHeartbeat();
  bool _MouseTargetValid();
  bool _MouseProfileVisible();
  DWORD _MouseProfileSession();
  std::unique_ptr<BihuaMousePanel> m_mouse_panel;
  std::recursive_mutex m_mouse_mutex;
  std::atomic<bool> m_mouse_enabled{false};
  bool m_mouse_ascii=false;
  BihuaMouseState m_mouse_state;
  BihuaMouseView m_mouse_view;
  BihuaStrokeInfo m_mouse_strokes;
  bool m_mouse_info=true,m_mouse_arrows=true,m_mouse_copy=true,m_mouse_selection=false;
  uint64_t m_mouse_pending_view=0;
  DWORD m_mouse_mode_session=0,m_mouse_mode_serial=0,m_mouse_mode_token=0,m_mouse_mode_owner=0;
  ULONGLONG m_mouse_mode_at=0;
  std::vector<std::wstring> m_mouse_candidates;
  int m_mouse_page_size=9,m_mouse_base=0;
  bool m_mouse_more=false;
  struct MouseExposure {DWORD session=0,generation=0;uint64_t revision=0;int first=0,count=0;};
  MouseExposure m_mouse_exposure;
  std::map<DWORD,HWND> m_mouse_targets;
  struct MouseProfile {DWORD pid=0,thread=0;bool active=false;int mode=-1;};
  std::map<DWORD,MouseProfile> m_mouse_profiles;
  bool _IsDeployerRunning();
  void _UpdateUI(WeaselSessionId ipc_id);
  void _LoadSchemaSpecificSettings(WeaselSessionId ipc_id,
                                   const std::string& schema_id);
  void _LoadAppInlinePreeditSet(WeaselSessionId ipc_id,
                                bool ignore_app_name = false);
  bool _ShowMessage(weasel::Context& ctx, weasel::Status& status);
  bool _Respond(WeaselSessionId ipc_id, EatLine eat);
  void _ReadClientInfo(WeaselSessionId ipc_id, LPWSTR buffer);
  void _GetCandidateInfo(weasel::CandidateInfo& cinfo, RimeContext& ctx);
  void _GetStatus(weasel::Status& stat,
                  WeaselSessionId ipc_id,
                  weasel::Context& ctx);
  void _GetContext(weasel::Context& ctx, RimeSessionId session_id);
  void _UpdateShowNotifications(RimeConfig* config, bool initialize = false);

  bool _IsSessionTSF(RimeSessionId session_id);
  void _UpdateInlinePreeditStatus(WeaselSessionId ipc_id);

  RimeSessionId to_session_id(WeaselSessionId ipc_id) {
    return m_session_status_map[ipc_id].session_id;
  }
  SessionStatus& get_session_status(WeaselSessionId ipc_id) {
    return m_session_status_map[ipc_id];
  }
  SessionStatus& new_session_status(WeaselSessionId ipc_id) {
    return m_session_status_map[ipc_id] = SessionStatus();
  }

  AppOptionsByAppName m_app_options;
  weasel::UI* m_ui;  // reference
  DWORD m_active_session;
  bool m_disabled;
  std::string m_last_schema_id;
  std::string m_last_app_name;
  weasel::UIStyle m_base_style;
  std::map<std::string, bool> m_show_notifications;
  std::map<std::string, bool> m_show_notifications_base;
  std::function<void()> _UpdateUICallback;

  static void OnNotify(void* context_object,
                       uintptr_t session_id,
                       const char* message_type,
                       const char* message_value);
  static std::string m_message_type;
  static std::string m_message_value;
  static std::string m_message_label;
  static std::string m_option_name;
  SessionStatusMap m_session_status_map;
  bool m_current_dark_mode;
  bool m_global_ascii_mode;
  int m_show_notifications_time;
  DWORD m_pid;
};
