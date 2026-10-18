#pragma once
#include <WeaselIPCData.h>
#include <gdiplus.h>
#include <windows.h>
#include <windowsx.h>

#include <algorithm>
#include <array>
#include <functional>
#include <mutex>
#include <vector>
#include "BihuaPersonalRecorder.h"
#include "BihuaPersonalKeys.h"
#pragma comment(lib, "gdiplus.lib")

// HWND and drawing stay on the UI thread; profile activity arrives via IPC.
class BihuaMousePanel {
 public:
  HWND window = nullptr;
  // Geometry IDs stay local. Candidate identity is an absolute Rime index.
  std::function<void(int, int, uint32_t, uint64_t, uint64_t)> clicked;
  std::function<void(uint32_t, uint64_t, int, int)> displayed;
  std::function<bool()> target_valid;
  void ConfigurePersonalKeys(const BihuaPersonalKeyMap& map){
    capture.Pause();std::lock_guard<std::mutex> lock(mutex);personal_keys=map;
  }
  void ConfigurePersonal(const std::filesystem::path& user,const std::filesystem::path& app,bool copy=true,bool selected=false){
    std::lock_guard<std::mutex> lock(mutex);recorder.user=std::filesystem::absolute(user);recorder.app=std::filesystem::absolute(app);recorder.clipboard=copy;recorder.selection=selected;
  }
  void ObserveSelection(uint32_t scalar){
    {std::lock_guard<std::mutex> lock(mutex);if(!recorder.selection||!enabled||!profileVisible||!ctx.preedit.str.empty()||(targetVisible&&!usable))return;
      if(!recorder.Observe(BihuaPersonalRecorder::FromScalar(scalar),0x100000000ull+ ++selection_generation))return;
      ++revision;}
    if(window)PostMessageW(window,WM_APP+42,0,0);
  }
  ~BihuaMousePanel() {
    capture.Stop();
    if (window) DestroyWindow(window);
    if (graphicsToken) Gdiplus::GdiplusShutdown(graphicsToken);
  }
  void Create() {
    WNDCLASSW wc{};
    wc.lpfnWndProc = Proc;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.lpszClassName = L"BihuaMousePanelV1";
    wc.style = CS_DROPSHADOW;
    RegisterClassW(&wc);
    window =
        CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST,
                        wc.lpszClassName, L"笔画鼠标输入", WS_POPUP, 0, 0, 0, 0,
                        nullptr, nullptr, wc.hInstance, this);
    auto dpi = reinterpret_cast<UINT(WINAPI*)(HWND)>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow"));
    scale = (dpi ? dpi(window) : 96) / 96.0;
    Gdiplus::GdiplusStartupInput graphicsInput;
    Gdiplus::GdiplusStartup(&graphicsToken, &graphicsInput, nullptr);
    Layout();
    RECT work = WorkArea();
    int x = work.left + (work.right - work.left - px(width)) / 2,
        y = work.bottom - px(height + 16);
    DWORD size = 4;
    RegGetValueW(HKEY_CURRENT_USER, L"Software\\BihuaInputMethod\\MousePanel",
                 L"X", RRF_RT_REG_DWORD, nullptr, &x, &size);
    size = 4;
    RegGetValueW(HKEY_CURRENT_USER, L"Software\\BihuaInputMethod\\MousePanel",
                 L"Y", RRF_RT_REG_DWORD, nullptr, &y, &size);
    SetWindowPos(window, HWND_TOPMOST, x, y, px(width), px(height),
                 SWP_NOACTIVATE);
    Resize();
    SetTimer(window, 1, 150, nullptr);
    AddClipboardFormatListener(window);
  }
  void Update(bool show, bool ready, const weasel::UIStyle& sty,
              const weasel::Context& context, uint32_t lease = 0,
              const std::vector<std::wstring>& projection = {}, int pageSize = 9,
              int first = 0, uint64_t semantic = 0, bool opened = false,
              int cursor = -1, uint64_t view = 0, bool stroke_info = true,
              bool hasMore = false) {
    {
      std::lock_guard<std::mutex> lock(mutex);
      enabled = show;
      if(!show)capture.Pause();
      usable = ready;
      style = sty;
      ctx = context;
      candidates = projection;
      if (candidates.empty())
        for (auto& candidate : ctx.cinfo.candies) candidates.push_back(candidate.str);
      if(recorder.view==BihuaPersonalRecorder::Offer&&!ctx.preedit.str.empty())recorder.Cancel();
      columns = std::clamp(pageSize, 1, 9);
      expanded = opened;
      navigation = cursor;
      info_enabled = stroke_info;
      more = hasMore;
      view_revision = view;
      base = first;
      projection_revision = semantic;
      // The legacy candidate preedit includes a textual cursor marker. This
      // compact read-only chip displays strokes, not an editable caret.
      ctx.preedit.str.erase(
          std::remove(ctx.preedit.str.begin(), ctx.preedit.str.end(), L'‸'),
          ctx.preedit.str.end());
      generation = lease;
      ++revision;
    }
    if (window) PostMessageW(window, WM_APP + 42, 0, 0);
  }
  void SetReady(bool ready) {
    {
      std::lock_guard<std::mutex> lock(mutex);
      usable = ready;
    }
    if (window) PostMessageW(window, WM_APP + 42, 0, 0);
  }
  void SetKeyboardMode(int mode){
    {std::lock_guard<std::mutex> lock(mutex);
      mode=mode>=0&&mode<=2?mode:-1;
      if(keyboard_mode==mode)return;
      keyboard_mode=mode;++revision;}
    if(window)PostMessageW(window,WM_APP+42,0,0);
  }
  void SetModeAvailable(bool available){
    {std::lock_guard<std::mutex> lock(mutex);if(mode_available==available)return;mode_available=available;++revision;}
    if(window)PostMessageW(window,WM_APP+42,0,0);
  }
  void SetProfileActive(bool active) {
    {
      std::lock_guard<std::mutex> lock(mutex);
      if (profileVisible == active) return;
      profileVisible = active;
      if(!active)capture.Pause();
      ++revision;
      pressed = -1;
    }
    if (window) PostMessageW(window, WM_APP + 42, 0, 0);
  }
  RECT ButtonRect(int id) {
    std::lock_guard<std::mutex> lock(mutex);
    return id >= 0 && id < static_cast<int>(buttons.size()) ? buttons[id] : RECT{};
  }
  void SetTargetActive(bool active) {
    {
      std::lock_guard<std::mutex> lock(mutex);
      if (targetVisible == active) return;
      targetVisible = active;
      ++revision;
      pressed = hovered = -1;
    }
    if (window) PostMessageW(window, WM_APP + 42, 0, 0);
  }
  void SetView(bool opened,int cursor,uint64_t view){
    {std::lock_guard<std::mutex> lock(mutex);
      expanded=opened;navigation=cursor;view_revision=view;++revision;pressed=-1;}
    if(window)PostMessageW(window,WM_APP+42,0,0);
  }
  void CancelPointer(){
    {std::lock_guard<std::mutex> lock(mutex);++revision;pressed=-1;}
    if(window)PostMessageW(window,WM_APP+47,0,0);
  }
  void ShowInformation(const std::vector<std::pair<std::wstring,std::string>>& rows,
                       uint32_t lease,uint64_t semantic,uint64_t view){
    {std::lock_guard<std::mutex> lock(mutex);
      if(lease!=generation||semantic!=projection_revision||view!=view_revision||!info_enabled||!hold_info_allowed)return;
      info_rows=rows;info_lease=lease;info_semantic=semantic;info_view=view;}
    if(window)PostMessageW(window,WM_APP+46,0,0);
  }

 private:
  static constexpr int strokeInset = 8;
  std::mutex mutex;
  BihuaPersonalKeyMap personal_keys;
  BihuaPersonalKeyCapture capture;
  uint64_t capture_serial=0;
  HWND capture_front=nullptr;
  void ArmPersonalKeys(){
    bool can;
    {std::lock_guard<std::mutex> lock(mutex);can=enabled&&profileVisible&&recorder.view==BihuaPersonalRecorder::Draft&&!recorder.busy;}
    if(!can)return;
    auto front=GetForegroundWindow();
    if(capture.active&&capture.allowed&&front==capture_front)return;
    bool ok=capture.Arm(window,front,personal_keys,++capture_serial);capture_front=front;
    if(!ok){std::lock_guard<std::mutex> lock(mutex);recorder.error=L"键盘录入不可用，可用鼠标";}
    InvalidateRect(window,nullptr,FALSE);
  }
  ULONG_PTR graphicsToken = 0;
  bool enabled = false, usable = false, profileVisible = false, targetVisible = false;
  enum class PointerGesture { Idle, PendingPress, Dragging };
  PointerGesture gesture = PointerGesture::Idle;
  double scale = 1;
  int hovered = -1, pressed = -1, width = 340, height = 76, points = 14,
      pad = 8, gap = 4, rowHeight = 30, radius = 12;
  POINT drag{}, origin{};
  SIZE drag_threshold{1,1};
  static constexpr int statusId=55;
  enum class HitKind { None, Status, Stroke, Candidate, Backspace, Expand, PageUp, PageDown, RecordOffer, RecordCancel, RecordSave };
  struct HitTarget {HitKind kind;int index=-1;};
  static HitTarget Target(int id){
    if(id==statusId)return {HitKind::Status};
    if(id==56)return {HitKind::RecordOffer};
    if(id==57)return {HitKind::RecordCancel};
    if(id==58)return {HitKind::RecordSave};
    if(id>=0&&id<6)return {HitKind::Stroke,id};
    if(id==6)return {HitKind::PageUp};
    if(id==7)return {HitKind::PageDown};
    if(id==17)return {HitKind::Backspace};
    if(id==18)return {HitKind::Expand};
    if(id>=8&&id<55)return {HitKind::Candidate,CandidateIndex(id)};
    return {HitKind::None};
  }
  std::array<RECT, 59> buttons{};
  BihuaPersonalRecorder recorder;
  uint64_t selection_generation=0;
  DWORD clipboard_sequence=0;
  int clipboard_retry=0;
  std::vector<std::wstring> candidates;
  bool expanded = false,more=false;
  int keyboard_mode=-1;
  bool mode_available=false;
  bool info_enabled=true,hold_consumed=false,releasing_capture=false,hold_info_allowed=false;
  HWND info_window=nullptr;
  int navigation=-1;
  uint64_t view_revision=0,pressed_view=0;
  std::vector<std::pair<std::wstring,std::string>> info_rows;
  uint32_t info_lease=0;
  uint64_t info_semantic=0,info_view=0;
  int columns = 9, base = 0;
  uint64_t projection_revision = 0;
  RECT preedit{};
  uint32_t generation = 0, pressed_generation = 0;
  uint64_t revision = 0, pressed_revision = 0;
  weasel::UIStyle style;
  weasel::Context ctx;
  static int CandidateId(int index) { return index < 9 ? index + 8 : index + 10; }
  static int CandidateIndex(int id) { return id < 17 ? id - 8 : id - 10; }
  int VisibleCount() const { return recorder.view==BihuaPersonalRecorder::Normal?(std::min)(static_cast<int>(candidates.size()), columns * (expanded ? 5 : 1)):0; }
  int px(int value) const { return static_cast<int>(value * scale + .5); }
  SIZE DragThreshold() const {
    auto metrics = reinterpret_cast<int(WINAPI*)(int,UINT)>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetSystemMetricsForDpi"));
    UINT dpi=static_cast<UINT>(96*scale+.5);
    return {(std::max)(1,metrics?metrics(SM_CXDRAG,dpi):GetSystemMetrics(SM_CXDRAG)),
            (std::max)(1,metrics?metrics(SM_CYDRAG,dpi):GetSystemMetrics(SM_CYDRAG))};
  }
  void CancelGesture(bool release=true,bool hide_info=true) {
    KillTimer(window,2);
    {std::lock_guard<std::mutex> lock(mutex);
      gesture=PointerGesture::Idle;pressed=hovered=-1;hold_consumed=true;
      if(hide_info)hold_info_allowed=false;}
    if(hide_info&&info_window)ShowWindow(info_window,SW_HIDE);
    if(release&&GetCapture()==window){
      releasing_capture=true;ReleaseCapture();releasing_capture=false;
    }
    InvalidateRect(window,nullptr,FALSE);
  }
  RECT WorkArea() const {
    MONITORINFO m{sizeof(m)};
    if (window && GetMonitorInfoW(
                      MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST), &m))
      return m.rcWork;
    RECT r{};
    SystemParametersInfoW(SPI_GETWORKAREA, 0, &r, 0);
    return r;
  }
  HFONT Font(int size) const {
    return CreateFontW(-MulDiv(size, static_cast<int>(96 * scale), 72), 0, 0, 0,
                       FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                       CLEARTYPE_QUALITY, 0,
                       style.font_face.empty() ? L"Microsoft YaHei UI"
                                               : style.font_face.c_str());
  }
  void Layout() {
    buttons.fill(RECT{});
    points = std::clamp(style.font_point ? style.font_point : 14, 8, 72);
    gap = std::clamp(style.candidate_spacing, 0, 40) + 3;
    pad = std::clamp(points / 3 + 4, 6, 14);
    radius = std::clamp(style.round_corner + 8, 16, 24);
    HDC dc = GetDC(window);
    HFONT font = Font(points);
    auto old = SelectObject(dc, font);
    TEXTMETRICW tm{};
    GetTextMetricsW(dc, &tm);
    rowHeight = (std::max)(24, static_cast<int>(tm.tmHeight / scale) + 8);
    // Candidate spacing must not stretch the stroke toolbar or row gutter.
    const int toolGap = 2;
    // A shared size for ordinary controls; Backspace has twice the hit width.
    // A 4-DIP grid stays pixel-aligned
    // at the usual Windows display scales.
    int buttonWidth = ((std::max)(20, points * 4 / 3 + 8) + 3) / 4 * 4,
        x = pad + buttonWidth + toolGap*2 + strokeInset;
    if(recorder.view==BihuaPersonalRecorder::Offer){
      width=(std::max)(300,points*19);height=pad*2+rowHeight;preedit={};
      buttons[56]={px(pad),px(pad),px(width-pad-buttonWidth-toolGap),px(pad+rowHeight)};
      buttons[57]={px(width-pad-buttonWidth),px(pad),px(width-pad),px(pad+rowHeight)};
      SelectObject(dc,old);DeleteObject(font);ReleaseDC(window,dc);return;
    }
    if(recorder.view==BihuaPersonalRecorder::Draft){
      x=pad+strokeInset;
      for(int id=0;id<5;++id){buttons[id]={px(x),px(pad),px(x+buttonWidth),px(pad+rowHeight)};x+=buttonWidth+toolGap;}
      buttons[0].left-=px(strokeInset);buttons[4].right+=px(strokeInset);x+=strokeInset+toolGap;
      buttons[17]={px(x),px(pad),px(x+buttonWidth*2),px(pad+rowHeight)};x+=buttonWidth*2+toolGap*2;
      buttons[58]={px(x),px(pad),px(x+buttonWidth*3),px(pad+rowHeight)};x+=buttonWidth*3+toolGap;
      buttons[57]={px(x),px(pad),px(x+buttonWidth),px(pad+rowHeight)};x+=buttonWidth;
      width=x+pad;height=pad*2+rowHeight*2+4;
      preedit={px(pad),px(pad+rowHeight+4),px(width-pad),px(pad+rowHeight*2+4)};
      SelectObject(dc,old);DeleteObject(font);ReleaseDC(window,dc);return;
    }
    const bool compact = ctx.preedit.str.empty() && candidates.empty();
    buttons[statusId]={px(pad),px(pad),px(pad+buttonWidth),px(pad+rowHeight)};
    for (int slot = 0; slot < (compact ? 6 : 7); ++slot) {
      if (slot == 6) x += strokeInset;
      if (slot == 6) x += toolGap;
      int id = slot == 6 ? 17 : slot;
      int cellWidth = id == 17 ? buttonWidth * 2 : buttonWidth;
      buttons[id] = {px(x), px(pad), px(x + cellWidth), px(pad + rowHeight)};
      x += cellWidth + toolGap;
    }
    // Only the two outside edges grow. Keep every core key and icon center
    // unchanged; the extra space also belongs to that end key's hover/hit box.
    buttons[0].left -= px(strokeInset);
    buttons[5].right += px(strokeInset);
    if (compact) {
      // An idle panel is just the six stroke keys. No invisible hit targets,
      // reserved candidate row, paging, Backspace, or expand control remain.
      width = x - toolGap + strokeInset + pad;
      height = pad * 2 + rowHeight;
      preedit = {};
      SelectObject(dc, old);
      DeleteObject(font);
      ReleaseDC(window, dc);
      return;
    }
    int toolsRight = x - toolGap,
        previewWidth = ctx.preedit.str.empty() ? 0 : (std::max)(72, points * 8);
    int y = pad + rowHeight + 4;
    x = pad;
    SIZE minimum{};
    GetTextExtentPoint32W(dc, L"9 天", 3, &minimum);
    RECT work = WorkArea();
    int available =
            static_cast<int>((work.right - work.left) / scale) - pad * 2 - 16,
        desired[9]{}, total = 0;
    for (int i = 0; i < columns; ++i) {
      SIZE s = minimum;
      for (int index = i; index < VisibleCount(); index += columns) {
        auto v = index < columns ? std::to_wstring(i + 1) + L" " + candidates[index] : candidates[index];
        SIZE measured{};
        GetTextExtentPoint32W(dc, v.c_str(), static_cast<int>(v.size()), &measured);
        s.cx = (std::max)(s.cx, measured.cx);
      }
      desired[i] = std::clamp(static_cast<int>(s.cx / scale) + pad * 2,
                              static_cast<int>(minimum.cx / scale) + pad,
                              points * 6 + pad * 2);
      total += desired[i];
    }
    double fit = (std::min)(
        1.0, static_cast<double>((std::max)(columns * 10, available - gap * (columns-1) - buttonWidth - toolGap)) / total);
    for (int i = 0; i < columns; ++i) {
      int cell = (std::max)(10, static_cast<int>(desired[i] * fit));
      for (int row = 0; row < (expanded ? 5 : 1); ++row) {
        int index = row * columns + i;
        if (index < VisibleCount())
          buttons[CandidateId(index)] = {px(x), px(y + row*(rowHeight+4)), px(x + cell), px(y + row*(rowHeight+4) + rowHeight)};
      }
      x += cell + gap;
    }
    int candidateRight = x - gap;
    width = (std::max)(
        toolsRight + pad + (previewWidth ? toolGap * 2 + previewWidth : 0),
        candidateRight + toolGap + buttonWidth + pad);
    int edgeId=expanded&&base>0?6:18;
    if(expanded||candidates.size()>static_cast<size_t>(columns))
      buttons[edgeId] = {px(width-pad-buttonWidth),px(y),px(width-pad),px(y+rowHeight)};
    if(expanded&&more)
      buttons[7]={px(width-pad-buttonWidth),px(y+4*(rowHeight+4)),px(width-pad),px(y+4*(rowHeight+4)+rowHeight)};
    // Use all space left by the candidate row rather than a narrow fixed chip.
    preedit = {px(toolsRight + toolGap * 2), px(pad), px(width - pad),
               px(pad + rowHeight)};
    height = y + rowHeight * (expanded ? 5 : 1) + (expanded ? 16 : 0) + pad;
    SelectObject(dc, old);
    DeleteObject(font);
    ReleaseDC(window, dc);
  }
  void Resize() {
    RECT r;
    GetWindowRect(window, &r);
    RECT work = WorkArea();
    int x = std::clamp<int>(r.left, work.left,
                            (std::max)(work.left, work.right - px(width))),
        y = std::clamp<int>(r.top, work.top,
                            (std::max)(work.top, work.bottom - px(height)));
    SetWindowPos(window, nullptr, x, y, px(width), px(height),
                 SWP_NOACTIVATE | SWP_NOZORDER);
    HRGN region = CreateRoundRectRgn(0, 0, px(width) + 1, px(height) + 1,
                                     px(radius * 2), px(radius * 2));
    if (!SetWindowRgn(window, region, TRUE)) DeleteObject(region);
  }
  int Hit(POINT p) const {
    for (int i = 0; i < static_cast<int>(buttons.size()); ++i)
      if (PtInRect(&buttons[i], p)) return i;
    return -1;
  }
  bool Valid(int id) const {
    if (!enabled || !profileVisible || id < 0) return false;
    if (id >= static_cast<int>(buttons.size()) || IsRectEmpty(&buttons[id])) return false;
    if(recorder.view!=BihuaPersonalRecorder::Normal){
      if(recorder.busy)return false;
      if(id==56||id==57)return true;
      if(id==58||id==17)return !recorder.code.empty();
      return recorder.view==BihuaPersonalRecorder::Draft&&id>=0&&id<5&&recorder.code.size()<52;
    }
    if (id == statusId) return mode_available;
    if (!targetVisible || !usable) return false;
    if (id == 6) return expanded&&base>0;
    if (id == 7) return expanded&&more;
    if (id == 17) return !ctx.preedit.str.empty() || !ctx.cinfo.candies.empty();
    if (id == 18) return expanded || candidates.size() > static_cast<size_t>(columns);
    return id < 6 || (CandidateIndex(id) >= 0 && CandidateIndex(id) < VisibleCount());
  }
  static LRESULT CALLBACK Proc(HWND hwnd, UINT message, WPARAM wp, LPARAM lp) {
    auto self = reinterpret_cast<BihuaMousePanel*>(
        GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (message == WM_NCCREATE) {
      self = static_cast<BihuaMousePanel*>(
          reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
      SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
    }
    if (!self) return DefWindowProcW(hwnd, message, wp, lp);
    if (message == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
    if(hwnd==self->info_window){
      if(message==WM_PAINT){self->PaintInformation(hwnd);return 0;}
      if(message==WM_LBUTTONDOWN){ShowWindow(hwnd,SW_HIDE);return 0;}
      return DefWindowProcW(hwnd,message,wp,lp);
    }
    if (message == WM_CLOSE) return 0;
    if (message == WM_APP + 42) {
      bool show,cancel;
      std::wstring caption = L"笔画鼠标输入\n";
      {
        std::lock_guard<std::mutex> lock(self->mutex);
        self->Layout();
        show = self->enabled && self->profileVisible;
        cancel=!show||(self->gesture!=PointerGesture::Idle&&self->pressed_revision!=self->revision);
        caption += self->ctx.preedit.str + L"\n";
        if(self->recorder.view!=BihuaPersonalRecorder::Normal){
          caption+=L"个人笔顺 "+self->recorder.character+L" ";
          for(char c:self->recorder.code)caption+=L"12345"[std::string("hspnz").find(c)];
        }
        for (int i = 0; i < self->VisibleCount(); ++i) {
          if (i) caption += L"\t";
          caption += self->candidates[i];
        }
      }
      if(cancel)self->CancelGesture();
      self->Resize();
      KillTimer(hwnd,2);
      if(self->info_window)ShowWindow(self->info_window,SW_HIDE);
      SetWindowTextW(hwnd, caption.c_str());
      ShowWindow(hwnd, show ? SW_SHOWNOACTIVATE : SW_HIDE);
      if(!show||self->recorder.view!=BihuaPersonalRecorder::Draft)self->capture.Pause();
      InvalidateRect(hwnd, nullptr, FALSE);
      // Clipboard changes while hidden/composing remain pending. Reconsider
      // the current sequence only when this event makes the panel available.
      if(show)PostMessageW(hwnd,WM_CLIPBOARDUPDATE,0,0);
      return 0;
    }
    if(message==WM_APP+44){
      std::lock_guard<std::mutex> lock(self->mutex);
      return MAKELRESULT(self->navigation<0?0:self->navigation-self->base+1,self->expanded?1:0);
    }
    if(message==WM_APP+45){std::lock_guard<std::mutex> lock(self->mutex);return self->keyboard_mode+1;}
    if(message==WM_APP+49){std::lock_guard<std::mutex> lock(self->mutex);return MAKELRESULT(self->recorder.view,self->recorder.busy?1:0);}
    if(message==WM_APP+51)return self->capture.active?1:0;
    if(message==WM_APP+52)return static_cast<LRESULT>(self->capture_serial);
    if(message==WM_APP+53)return self->personal_keys.valid?1:0;
    if(message==BihuaPersonalKeyCapture::ActionMessage){
      if(wp!=self->capture_serial)return 0;
      {
        std::lock_guard<std::mutex> lock(self->mutex);
        if(self->recorder.view!=BihuaPersonalRecorder::Draft)return 0;
        int action=static_cast<int>(lp);
        if(action==BihuaPersonalKeyCapture::Paused)return 0;
        else if(action==BihuaPersonalKeyCapture::Unavailable)self->recorder.error=L"键盘录入不可用，可用鼠标";
        else if(self->enabled&&self->profileVisible&&!self->recorder.busy){
          if(action>=0&&action<5){if(self->recorder.code.size()>=52)self->recorder.error=L"最多录入 52 笔";else self->recorder.Stroke(action);}
          else if(action==5)self->recorder.Backspace();
          else if(action==6){if(self->recorder.code.empty())self->recorder.error=L"请先输入笔画";else self->recorder.Save();}
          else if(action==7){self->recorder.Cancel();self->capture.Pause();}
          else if(action==8)self->recorder.error=L"个人笔顺只支持五种笔画";
          else if(action==9)self->recorder.error=L"该键未绑定笔画";
          ++self->revision;
        }
      }
      PostMessageW(hwnd,WM_APP+42,0,0);return 0;
    }
    if(message==WM_APP+47){self->CancelGesture();return 0;}
    if(message==WM_APP+46){self->OpenInformation();return 0;}
    // Read-only geometry exposes no action and keeps drawing and hit tests
    // aligned.
    if (message == WM_APP + 43) {
      if (wp >= self->buttons.size()) return 0;
      auto r = self->ButtonRect(static_cast<int>(wp));
      return MAKELRESULT((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    }
    if (message == WM_TIMER) {
      if(wp==3){KillTimer(hwnd,3);self->ObserveClipboard();return 0;}
      if(wp==2){
        KillTimer(hwnd,2);
        int index=-1;uint32_t lease=0;uint64_t semantic=0,view=0;
        {std::lock_guard<std::mutex> lock(self->mutex);
          int id=self->pressed;
          if(self->gesture==PointerGesture::PendingPress&&GetCapture()==hwnd&&self->info_enabled&&Target(id).kind==HitKind::Candidate&&self->Valid(id)&&
             self->pressed_revision==self->revision&&self->pressed_view==self->view_revision){
            self->hold_consumed=true;
            self->hold_info_allowed=true;
            index=self->base+CandidateIndex(id);lease=self->generation;
            semantic=self->projection_revision;view=self->view_revision;
          }
        }
        if(index>=0&&self->clicked)self->clicked(19,index,lease,semantic,view);
        return 0;
      }
      if (self->target_valid) self->target_valid();
      bool changed=false;{std::lock_guard<std::mutex> lock(self->mutex);changed=self->recorder.Poll();if(changed)++self->revision;}
      if(changed)PostMessageW(hwnd,WM_APP+42,0,0);
      return 0;
    }
    if(message==WM_CLIPBOARDUPDATE){self->clipboard_retry=0;self->ObserveClipboard();return 0;}
    if (message == WM_ERASEBKGND) return 1;
    if (message == WM_PAINT) {
      self->Paint(hwnd);
      return 0;
    }
    if (message == WM_DPICHANGED) {
      self->scale = HIWORD(wp) / 96.0;
      bool preserve;
      {
        std::lock_guard<std::mutex> lock(self->mutex);
        preserve=self->gesture==PointerGesture::Dragging&&self->pressed_revision==self->revision;
        ++self->revision;
        self->pressed = -1;
        if(preserve)self->pressed_revision=self->revision;
        self->Layout();
      }
      if(!preserve)self->CancelGesture();
      self->Resize();
      return 0;
    }
    if (message == WM_CAPTURECHANGED || message == WM_CANCELMODE) {
      self->CancelGesture(message==WM_CANCELMODE,!self->releasing_capture);
      return 0;
    }
    if (message == WM_LBUTTONDOWN) {
      self->CancelGesture();
      POINT p{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)};
      POINT screen=p;
      if(!ClientToScreen(hwnd,&screen))return 0;
      RECT r{};if(!GetWindowRect(hwnd,&r))return 0;
      {
        std::lock_guard<std::mutex> lock(self->mutex);
        if(!self->enabled||!self->profileVisible||!IsWindowVisible(hwnd))return 0;
        self->pressed = self->Hit(p);
        self->pressed_generation = self->generation;
        self->pressed_revision = self->revision;
        self->pressed_view = self->view_revision;
        self->hold_consumed=false;
        self->gesture=PointerGesture::PendingPress;
        self->drag=screen;
        self->origin = {r.left, r.top};
        self->drag_threshold=self->DragThreshold();
      }
      SetCapture(hwnd);
      if(GetCapture()!=hwnd){self->CancelGesture();return 0;}
      if(Target(self->pressed).kind==HitKind::Candidate&&self->info_enabled)
        SetTimer(hwnd,2,500,nullptr);
      InvalidateRect(hwnd, nullptr, FALSE);
      return 0;
    }
    if (message == WM_MOUSEMOVE) {
      POINT current{GET_X_LPARAM(lp),GET_Y_LPARAM(lp)};
      if(self->gesture!=PointerGesture::Idle){
        if(!(wp&MK_LBUTTON))return 0;
        POINT screen=current;
        bool valid;
        {std::lock_guard<std::mutex> lock(self->mutex);
          valid=self->enabled&&self->profileVisible&&
                self->pressed_revision==self->revision&&self->pressed_view==self->view_revision;}
        if(!valid||GetCapture()!=hwnd||!ClientToScreen(hwnd,&screen)){self->CancelGesture();return 0;}
        if(self->gesture==PointerGesture::PendingPress&&
           (abs(screen.x-self->drag.x)>self->drag_threshold.cx||abs(screen.y-self->drag.y)>self->drag_threshold.cy)){
          KillTimer(hwnd,2);
          {std::lock_guard<std::mutex> lock(self->mutex);
            self->gesture=PointerGesture::Dragging;self->pressed=self->hovered=-1;
            self->hold_consumed=true;self->hold_info_allowed=false;}
          if(self->info_window)ShowWindow(self->info_window,SW_HIDE);
          InvalidateRect(hwnd,nullptr,FALSE);
        }
        if(self->gesture==PointerGesture::Dragging){
          SetWindowPos(hwnd,nullptr,self->origin.x+screen.x-self->drag.x,
                       self->origin.y+screen.y-self->drag.y,0,0,
                       SWP_NOSIZE|SWP_NOACTIVATE|SWP_NOZORDER);
          return 0;
        }
      }
      {
        POINT p{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)};
        int hit = self->Hit(p);
        if (hit != self->hovered) {
          if(self->info_window)ShowWindow(self->info_window,SW_HIDE);
          self->hovered = hit;
          InvalidateRect(hwnd, nullptr, FALSE);
          TRACKMOUSEEVENT t{sizeof(t), TME_LEAVE, hwnd, 0};
          TrackMouseEvent(&t);
        }
      }
      return 0;
    }
    if (message == WM_MOUSELEAVE) {
      KillTimer(hwnd,2);
      if(self->info_window)ShowWindow(self->info_window,SW_HIDE);
      self->hovered = -1;
      InvalidateRect(hwnd, nullptr, FALSE);
      return 0;
    }
    if (message == WM_LBUTTONUP) {
      KillTimer(hwnd,2);
      auto phase=self->gesture;
      bool moving = phase==PointerGesture::Dragging;
      self->gesture = PointerGesture::Idle;
      int pressed = self->pressed;
      self->pressed = -1;
      POINT p{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)};
      int id = self->Hit(p);
      bool ok;
      int action = -1, absolute_index = -1;
      uint32_t click_generation = 0;
      uint64_t click_revision = 0;
      uint64_t click_view = 0;
      {
        std::lock_guard<std::mutex> lock(self->mutex);
        moving=moving&&self->enabled&&self->profileVisible&&
               self->pressed_generation==self->generation&&self->pressed_revision==self->revision&&
               self->pressed_view==self->view_revision&&GetCapture()==hwnd;
        ok = phase==PointerGesture::PendingPress&&!self->hold_consumed&&id == pressed && self->Valid(id) &&
             self->pressed_generation == self->generation &&
             self->pressed_revision == self->revision&&self->pressed_view==self->view_revision;
        if (ok) {
          bool candidate = Target(id).kind==HitKind::Candidate;
          action = Target(id).kind==HitKind::Status ? 21 : candidate ? 18 : id;
          absolute_index = candidate ? self->base + CandidateIndex(id) : -1;
          click_generation = self->generation;
          click_revision = self->projection_revision;
          click_view = self->view_revision;
        }
      }
      self->releasing_capture=true;
      ReleaseCapture();
      self->releasing_capture=false;
      InvalidateRect(hwnd, nullptr, FALSE);
      if (moving) {
        self->Resize();
        RECT r;
        GetWindowRect(hwnd, &r);
        HKEY key;
        if (RegCreateKeyExW(HKEY_CURRENT_USER,
                            L"Software\\BihuaInputMethod\\MousePanel", 0,
                            nullptr, 0, KEY_SET_VALUE, nullptr, &key,
                            nullptr) == ERROR_SUCCESS) {
          RegSetValueExW(key, L"X", 0, REG_DWORD,
                         reinterpret_cast<BYTE*>(&r.left), 4);
          RegSetValueExW(key, L"Y", 0, REG_DWORD,
                         reinterpret_cast<BYTE*>(&r.top), 4);
          RegCloseKey(key);
        }
        return 0;
      }
      if (ok && id == 18) {
        if(self->clicked)self->clicked(20,-1,click_generation,click_revision,click_view);
      } else if(ok&&self->recorder.view!=BihuaPersonalRecorder::Normal){
        {std::lock_guard<std::mutex> lock(self->mutex);
          if(id==56)self->recorder.Begin();else if(id==57)self->recorder.Cancel();
          else if(id==58)self->recorder.Save();else if(id==17)self->recorder.Backspace();else if(id>=0&&id<5)self->recorder.Stroke(id);
          ++self->revision;}
        if(id!=57&&id!=58)self->ArmPersonalKeys();
        PostMessageW(hwnd,WM_APP+42,0,0);
      } else if (ok && action>=0 && self->clicked) {
        self->clicked(action,absolute_index,click_generation,click_revision,click_view);
      } else if(self->recorder.view==BihuaPersonalRecorder::Draft){
        POINT point{GET_X_LPARAM(lp),GET_Y_LPARAM(lp)};
        if(PtInRect(&self->preedit,point))self->ArmPersonalKeys();
      }
      return 0;
    }
    if (message == WM_DESTROY) {
      self->capture.Stop();
      RemoveClipboardFormatListener(hwnd);KillTimer(hwnd,3);
      KillTimer(hwnd, 1);
      KillTimer(hwnd, 2);
      if(self->info_window){DestroyWindow(self->info_window);self->info_window=nullptr;}
      self->window = nullptr;
      return 0;
    }
    return DefWindowProcW(hwnd, message, wp, lp);
  }
  static COLORREF Blend(COLORREF back, COLORREF ink, int a) {
    return RGB((GetRValue(back) * (100 - a) + GetRValue(ink) * a) / 100,
               (GetGValue(back) * (100 - a) + GetGValue(ink) * a) / 100,
               (GetBValue(back) * (100 - a) + GetBValue(ink) * a) / 100);
  }
  void ObserveClipboard(){
    auto sequence=GetClipboardSequenceNumber();
    if(!sequence||sequence==clipboard_sequence)return;
    {std::lock_guard<std::mutex> lock(mutex);
      if(!enabled||!profileVisible||!recorder.clipboard||!ctx.preedit.str.empty()||(targetVisible&&!usable))return;
      if(recorder.view==BihuaPersonalRecorder::Draft){clipboard_sequence=sequence;return;}}
    if(!OpenClipboard(window)){
      if(clipboard_retry<3){const UINT waits[]={50,100,200};SetTimer(window,3,waits[clipboard_retry++],nullptr);}return;
    }
    std::wstring text;
    if(IsClipboardFormatAvailable(CF_UNICODETEXT)){
      HANDLE data=GetClipboardData(CF_UNICODETEXT);SIZE_T bytes=data?GlobalSize(data):0;
      if(bytes>=sizeof(wchar_t)*2){
        auto value=static_cast<const wchar_t*>(GlobalLock(data));
        if(value){size_t count=0;while(count<(std::min)(SIZE_T(3),bytes/sizeof(wchar_t))&&value[count])++count;
          if(count<bytes/sizeof(wchar_t)&&count<=2)text.assign(value,count);GlobalUnlock(data);}
      }
    }
    CloseClipboard();
    if(sequence!=GetClipboardSequenceNumber())return;
    clipboard_sequence=sequence;
    bool changed=false;{std::lock_guard<std::mutex> lock(mutex);
      changed=recorder.Observe(text,sequence);if(changed)++revision;}
    if(changed)PostMessageW(window,WM_APP+42,0,0);
  }
  void DrawStatusIcon(HDC dc,const RECT& bounds,COLORREF fallback){
    const float side=static_cast<float>((std::min<int>)(px(points+8),
        (std::min)(bounds.right-bounds.left,bounds.bottom-bounds.top)-px(4)));
    if(!graphicsToken){
      RECT r=bounds;SetTextColor(dc,fallback);
      DrawTextW(dc,keyboard_mode==1?L"a":keyboard_mode==2?L"A":keyboard_mode==0?L"𠃌":L"·",
          -1,&r,DT_CENTER|DT_VCENTER|DT_SINGLELINE);return;
    }
    Gdiplus::Graphics g(dc);g.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);
    Gdiplus::Matrix transform(side/24,0,0,side/24,
        (bounds.left+bounds.right-side)*.5f,(bounds.top+bounds.bottom-side)*.5f);
    g.SetTransform(&transform);
    Gdiplus::GraphicsPath tile;
    for(auto arc:std::array<std::array<float,3>,4>{{{0,0,180},{12,0,270},{12,12,0},{0,12,90}}})
      tile.AddArc(arc[0],arc[1],12.0f,12.0f,arc[2],90.0f);
    tile.CloseFigure();
    Gdiplus::SolidBrush green(Gdiplus::Color(255,18,168,112)),white(Gdiplus::Color(255,255,255,255));
    g.FillPath(&green,&tile);
    Gdiplus::GraphicsPath mark;
    if(keyboard_mode==0){
      mark.AddLine(6.5f,7.5f,17.5f,7.5f);
      mark.AddLine(17.5f,7.5f,16.0f,15.3f);
      mark.AddLine(16.0f,15.3f,12.5f,17.2f);
      Gdiplus::Pen pen(Gdiplus::Color(255,255,255,255),2.3f);
      pen.SetStartCap(Gdiplus::LineCapRound);pen.SetEndCap(Gdiplus::LineCapRound);
      pen.SetLineJoin(Gdiplus::LineJoinRound);g.DrawPath(&pen,&mark);
    }else if(keyboard_mode==1||keyboard_mode==2){
      Gdiplus::FontFamily family(L"Segoe UI");
      mark.AddString(keyboard_mode==1?L"a":L"A",1,&family,Gdiplus::FontStyleBold,19,
          Gdiplus::PointF(0,0),Gdiplus::StringFormat::GenericTypographic());
      Gdiplus::RectF box;mark.GetBounds(&box);
      Gdiplus::Matrix center;center.Translate(12-box.X-box.Width/2,12-box.Y-box.Height/2);
      mark.Transform(&center);g.FillPath(&white,&mark);
    }else g.FillEllipse(&white,10.7f,10.7f,2.6f,2.6f);
  }
  void DrawToolIcon(HDC dc, int id, const RECT& bounds, COLORREF color) {
    if (!graphicsToken) {
      RECT r = bounds;
      SetTextColor(dc, color);
      const wchar_t* glyphs[] = {L"一", L"丨", L"丿", L"丶",
                                 L"𠃌", L"?",  L"‹",  L"›"};
      DrawTextW(dc, id == 17 ? L"←" : id == 18 ? (expanded ? L"⌃" : L"⌄") : glyphs[id], -1, &r,
                DT_CENTER | DT_VCENTER | DT_SINGLELINE);
      return;
    }
    // A shared optical canvas avoids full-width punctuation side bearings and
    // keeps both controls proportional at small fonts and every DPI scale.
    const float iconScale = id < 6 ? .84f : 1.0f;
    const float side =
        iconScale * static_cast<float>(
                        (std::min<int>)(px(points + 8),
                                        (std::min)(bounds.right - bounds.left,
                                                   bounds.bottom - bounds.top) -
                                            px(4)));
    const float unit = side / 24.0f;
    Gdiplus::Matrix transform(unit, 0, 0, unit,
                              (bounds.left + bounds.right - side) * .5f,
                              (bounds.top + bounds.bottom - side) * .5f);
    Gdiplus::Graphics graphics(dc);
    graphics.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);
    graphics.SetTransform(&transform);
    Gdiplus::Color ink(255, GetRValue(color), GetGValue(color),
                       GetBValue(color));
    Gdiplus::Pen pen(ink, 1.7f / iconScale);
    pen.SetStartCap(Gdiplus::LineCapRound);
    pen.SetEndCap(Gdiplus::LineCapRound);
    pen.SetLineJoin(Gdiplus::LineJoinRound);
    Gdiplus::GraphicsPath path;
    if (id < 5) {
      if (id == 0) {
        path.AddLine(3.0f, 12.0f, 21.0f, 12.0f);
      } else if (id == 1) {
        path.AddLine(12.0f, 3.0f, 12.0f, 21.0f);
      } else if (id == 2) {
        path.AddBezier(17.5f, 3.0f, 17.8f, 11.0f, 13.2f, 17.2f, 6.5f, 21.0f);
      } else if (id == 3) {
        path.AddBezier(8.5f, 8.0f, 11.1f, 9.0f, 13.8f, 12.1f, 15.6f, 16.0f);
      } else {
        path.AddLine(4.0f, 4.0f, 19.5f, 4.0f);
        path.AddBezier(19.5f, 4.0f, 20.2f, 4.0f, 20.5f, 4.4f, 20.4f, 5.2f);
        path.AddBezier(20.4f, 5.2f, 20.0f, 10.5f, 19.1f, 16.0f, 18.1f, 18.5f);
        path.AddBezier(18.1f, 18.5f, 17.4f, 20.5f, 16.5f, 21.0f, 14.8f, 20.1f);
        path.AddLine(14.8f, 20.1f, 12.0f, 18.5f);
      }
      graphics.DrawPath(&pen, &path);
    } else if (id == 5) {
      path.AddBezier(7.0f, 8.0f, 7.0f, 5.2f, 9.1f, 3.5f, 12.0f, 3.5f);
      path.AddBezier(12.0f, 3.5f, 14.9f, 3.5f, 17.0f, 5.4f, 17.0f, 8.0f);
      path.AddBezier(17.0f, 8.0f, 17.0f, 10.2f, 15.5f, 11.2f, 13.5f, 12.5f);
      path.AddBezier(13.5f, 12.5f, 12.4f, 13.2f, 12.0f, 14.0f, 12.0f, 15.5f);
      graphics.DrawPath(&pen, &path);
      Gdiplus::SolidBrush dot(ink);
      const float dotSide = 2.1f / iconScale;
      graphics.FillEllipse(&dot, 12.0f - dotSide / 2, 20.0f - dotSide / 2,
                           dotSide, dotSide);
    } else if (id == 6 || id == 7) {
      const float tip = id==6?9.0f:15.0f,edge=id==6?14.0f:10.0f;
      path.AddLine(7.5f,edge,12.0f,tip);
      path.AddLine(12.0f,tip,16.5f,edge);
      graphics.DrawPath(&pen, &path);
    } else if (id == 18) {
      float tip = expanded ? 9.5f : 14.5f, edge = expanded ? 14.5f : 9.5f;
      path.AddLine(8.0f,edge,12.0f,tip);
      path.AddLine(12.0f,tip,16.0f,edge);
      graphics.DrawPath(&pen,&path);
      if(expanded){
        graphics.DrawLine(&pen,8.0f,18.0f,12.0f,13.0f);
        graphics.DrawLine(&pen,12.0f,13.0f,16.0f,18.0f);
      }
    } else if(id==57){
      graphics.DrawLine(&pen,8.0f,8.0f,16.0f,16.0f);
      graphics.DrawLine(&pen,16.0f,8.0f,8.0f,16.0f);
    } else {
      path.AddLine(9, 5, 20, 5);
      path.AddBezier(20.0f, 5.0f, 21.1f, 5.0f, 22.0f, 5.9f, 22.0f, 7.0f);
      path.AddLine(22, 7, 22, 17);
      path.AddBezier(22.0f, 17.0f, 22.0f, 18.1f, 21.1f, 19.0f, 20.0f, 19.0f);
      path.AddLine(20, 19, 9, 19);
      path.AddBezier(9.0f, 19.0f, 8.5f, 19.0f, 8.0f, 18.75f, 7.7f, 18.4f);
      path.AddLine(7.7f, 18.4f, 2.3f, 12.7f);
      path.AddBezier(2.3f, 12.7f, 1.9f, 12.3f, 1.9f, 11.7f, 2.3f, 11.3f);
      path.AddLine(2.3f, 11.3f, 7.7f, 5.6f);
      path.AddBezier(7.7f, 5.6f, 8.0f, 5.2f, 8.5f, 5.0f, 9.0f, 5.0f);
      path.CloseFigure();
      graphics.DrawPath(&pen, &path);
      graphics.DrawLine(&pen, 12.0f, 9.0f, 18.0f, 15.0f);
      graphics.DrawLine(&pen, 18.0f, 9.0f, 12.0f, 15.0f);
    }
  }
  int InformationWidth() const {
    size_t longest=0;for(auto& row:info_rows)longest=(std::max)(longest,row.second.size());
    return (std::max)(260,64+static_cast<int>((std::min)(size_t(16),longest))*20);
  }
  int InformationHeight() const {
    int height=16;for(auto& row:info_rows)height+=((std::max)(1,static_cast<int>((row.second.size()+15)/16)))*26+8;
    return height;
  }
  void OpenInformation(){
    int w=0,h=0;std::wstring caption;
    {std::lock_guard<std::mutex> lock(mutex);
      if(!info_enabled||!hold_info_allowed||!targetVisible||!profileVisible||!enabled||info_rows.empty()||
         generation!=info_lease||projection_revision!=info_semantic||view_revision!=info_view)return;
      w=px(InformationWidth());h=px(InformationHeight());
      for(auto& row:info_rows){if(!caption.empty())caption+=L"\n";caption+=row.first+L" ";
        const wchar_t* symbols[]={L"一",L"丨",L"丿",L"丶",L"𠃌"};
        for(char stroke:row.second)if(stroke>='1'&&stroke<='5')caption+=symbols[stroke-'1'];
      }
    }
    if(!info_window){
      WNDCLASSW wc{};wc.hInstance=GetModuleHandleW(nullptr);wc.lpfnWndProc=Proc;
      wc.lpszClassName=L"BihuaStrokeInfoV1";wc.hCursor=LoadCursor(nullptr,IDC_ARROW);wc.style=CS_DROPSHADOW;
      RegisterClassW(&wc);
      info_window=CreateWindowExW(WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW|WS_EX_TOPMOST,wc.lpszClassName,L"",
          WS_POPUP,0,0,w,h,window,nullptr,wc.hInstance,this);
    }
    if(!info_window)return;
    RECT panel{},work=WorkArea();GetWindowRect(window,&panel);
    int x=std::clamp<int>(panel.left,work.left,(std::max)(work.left,work.right-w));
    int y=panel.top-h-px(6);if(y<work.top)y=panel.bottom+px(6);
    y=std::clamp<int>(y,work.top,(std::max)(work.top,work.bottom-h));
    HRGN region=CreateRoundRectRgn(0,0,w+1,h+1,px(20),px(20));
    if(!SetWindowRgn(info_window,region,TRUE))DeleteObject(region);
    SetWindowTextW(info_window,caption.c_str());
    SetWindowPos(info_window,HWND_TOPMOST,x,y,w,h,SWP_NOACTIVATE|SWP_SHOWWINDOW);
    InvalidateRect(info_window,nullptr,FALSE);
  }
  void PaintInformation(HWND hwnd){
    PAINTSTRUCT paint{};HDC dc=BeginPaint(hwnd,&paint);
    std::lock_guard<std::mutex> lock(mutex);
    RECT area{};GetClientRect(hwnd,&area);
    COLORREF background=style.back_color&0xffffff;
    bool dark=GetRValue(background)*299+GetGValue(background)*587+GetBValue(background)*114<128000;
    COLORREF ink=dark?RGB(255,255,255):RGB(0,0,0);
    HBRUSH brush=CreateSolidBrush(background);FillRect(dc,&area,brush);DeleteObject(brush);
    HPEN pen=CreatePen(PS_SOLID,1,Blend(background,ink,16));auto oldPen=SelectObject(dc,pen);
    auto oldBrush=SelectObject(dc,GetStockObject(NULL_BRUSH));
    RoundRect(dc,0,0,area.right,area.bottom,px(20),px(20));SelectObject(dc,oldPen);SelectObject(dc,oldBrush);DeleteObject(pen);
    HFONT font=Font((std::max)(10,(std::min)(points,16)));auto oldFont=SelectObject(dc,font);
    SetBkMode(dc,TRANSPARENT);SetTextColor(dc,Blend(background,ink,90));
    int y=8;
    for(auto& row:info_rows){
      RECT character{px(12),px(y),px(54),px(y+26)};
      if(row.second.empty()){
        RECT line{px(12),px(y),area.right-px(12),px(y+26)};
        auto text=row.first.size()>2?row.first:row.first+L"  未收录默认笔画";
        DrawTextW(dc,text.c_str(),-1,&line,DT_LEFT|DT_VCENTER|DT_SINGLELINE|DT_END_ELLIPSIS);
      }else{
        DrawTextW(dc,row.first.c_str(),-1,&character,DT_LEFT|DT_VCENTER|DT_SINGLELINE);
        for(size_t i=0;i<row.second.size();++i){
          RECT cell{px(56+static_cast<int>(i%16)*20),px(y+static_cast<int>(i/16)*26),
                    px(76+static_cast<int>(i%16)*20),px(y+static_cast<int>(i/16)*26+26)};
          DrawToolIcon(dc,row.second[i]-'1',cell,Blend(background,ink,90));
        }
      }
      y+=((std::max)(1,static_cast<int>((row.second.size()+15)/16)))*26+8;
    }
    SelectObject(dc,oldFont);DeleteObject(font);EndPaint(hwnd,&paint);
  }
  void Paint(HWND hwnd) {
    PAINTSTRUCT paint;
    HDC target = BeginPaint(hwnd, &paint);
    RECT area;
    GetClientRect(hwnd, &area);
    HDC dc = CreateCompatibleDC(target);
    HBITMAP bitmap = CreateCompatibleBitmap(target, area.right, area.bottom);
    auto oldBitmap = SelectObject(dc, bitmap);
    std::unique_lock<std::mutex> lock(mutex);
    COLORREF background = style.back_color & 0xffffff;
    bool dark = GetRValue(background) * 299 + GetGValue(background) * 587 +
                    GetBValue(background) * 114 <
                128000;
    COLORREF ink = dark ? RGB(255, 255, 255) : RGB(0, 0, 0),
             text = style.candidate_text_color & 0xffffff,
             selected = style.hilited_candidate_back_color & 0xffffff,
             selectedText = style.hilited_candidate_text_color & 0xffffff;
    if (selected == background) {
      selected = Blend(background, ink, 12);
      selectedText = Blend(background, ink, 92);
    }
    HBRUSH back = CreateSolidBrush(background);
    FillRect(dc, &area, back);
    DeleteObject(back);
    SetBkMode(dc, TRANSPARENT);
    auto surface = [&](RECT r, COLORREF fill, int edge, int corner) {
      if (graphicsToken) {
        Gdiplus::Graphics graphics(dc);
        graphics.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);
        auto color = [](COLORREF v) {
          return Gdiplus::Color(255, GetRValue(v), GetGValue(v), GetBValue(v));
        };
        Gdiplus::REAL left = r.left + .5f, top = r.top + .5f,
                      w = static_cast<float>(r.right - r.left) - 1,
                      h = static_cast<float>(r.bottom - r.top) - 1;
        Gdiplus::REAL diameter =
            (std::min)(static_cast<float>(px(corner * 2)), (std::min)(w, h));
        Gdiplus::GraphicsPath path;
        path.AddArc(left, top, diameter, diameter, 180, 90);
        path.AddArc(left + w - diameter, top, diameter, diameter, 270, 90);
        path.AddArc(left + w - diameter, top + h - diameter, diameter, diameter,
                    0, 90);
        path.AddArc(left, top + h - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        Gdiplus::SolidBrush brush(color(fill));
        Gdiplus::Pen outline(color(Blend(background, ink, edge)), 1.0f);
        graphics.FillPath(&brush, &path);
        graphics.DrawPath(&outline, &path);
        return;
      }
      HBRUSH b = CreateSolidBrush(fill);
      HPEN pen = CreatePen(PS_SOLID, (std::max)(1, px(1)),
                           Blend(background, ink, edge));
      auto ob = SelectObject(dc, b), op = SelectObject(dc, pen);
      RoundRect(dc, r.left, r.top, r.right, r.bottom, px(corner * 2),
                px(corner * 2));
      SelectObject(dc, ob);
      SelectObject(dc, op);
      DeleteObject(b);
      DeleteObject(pen);
    };
    RECT outer{0, 0, area.right, area.bottom};
    surface(outer, background, 12, radius);
    HFONT font = Font(points);
    auto oldFont = SelectObject(dc, font);
    auto draw = [&](const std::wstring& value, RECT r, COLORREF color,
                    UINT flags = DT_CENTER | DT_VCENTER | DT_SINGLELINE |
                                 DT_END_ELLIPSIS) {
      SetTextColor(dc, color);
      DrawTextW(dc, value.c_str(), static_cast<int>(value.size()), &r, flags);
    };
    RECT strokeGroup = buttons[0];
    strokeGroup.right = buttons[recorder.view==BihuaPersonalRecorder::Draft?4:5].right;
    if(!IsRectEmpty(&strokeGroup))surface(strokeGroup, Blend(background, ink, 3), 12, 10);
    if (!IsRectEmpty(&buttons[17])) surface(buttons[17], Blend(background, ink, 3), 12, 10);
    for (int id = 0; id < static_cast<int>(buttons.size()); ++id) {
      if (IsRectEmpty(&buttons[id])) continue;
      auto target=Target(id);
      bool tool = target.kind!=HitKind::Candidate;
      int index = target.index;
      if (!tool && (index < 0 || index >= VisibleCount()))
        continue;
      bool active = Valid(id), over = active && hovered == id,
           down = active && pressed == id,
           chosen = !tool && active &&
                    index == (navigation>=base?navigation-base:ctx.cinfo.highlighted);
      RECT r = buttons[id];
      COLORREF color = tool ? Blend(background, ink, active ? 90 : 35) : text;
      if (over || down || chosen) {
        RECT highlight = r;
        if (tool) InflateRect(&highlight, -px(2), -px(2));
        surface(highlight,
                chosen ? selected
                       : Blend(background, ink,
                               down   ? 15
                               : over ? 9
                               : tool ? 3
                                      : 0),
                chosen ? 0
                : down ? 22
                : over ? 18
                       : 12,
                tool && (id == 6 || id == 7) ? rowHeight / 2
                                             : (std::min)(8, rowHeight / 3));
        if (chosen) color = selectedText;
      }
      if (tool) {
        RECT iconBounds = r;
        if (id == 0) iconBounds.left += px(strokeInset);
        if (id == (recorder.view==BihuaPersonalRecorder::Draft?4:5)) iconBounds.right -= px(strokeInset);
        if(id==statusId)DrawStatusIcon(dc,iconBounds,color);
        else if(id==56||id==58){
          if(id==56||active||recorder.busy){
            surface(r,over||down?Blend(selected,ink,down?12:6):selected,0,10);
            color=selectedText;
          }else if(!over&&!down)surface(r,Blend(background,ink,7),12,10);
          draw(id==56?L"自定义「"+recorder.character+L"」的笔顺":recorder.busy?L"保存中…":recorder.replaced?L"覆盖保存":L"保存",r,color);
        }
        else DrawToolIcon(dc, id, iconBounds, color);
      } else {
        auto value = (index < columns ? std::to_wstring(index + 1) + L" " : L"") + candidates[index];
        r.left += px(3);
        r.right -= px(3);
        draw(value, r, active ? color : Blend(background, ink, 35));
      }
    }
    if (recorder.view==BihuaPersonalRecorder::Draft){
      surface(preedit,Blend(background,ink,2),10,8);
      RECT label=preedit;label.left+=px(8);label.right=label.left+px(points*2);
      draw(recorder.character,label,Blend(background,ink,90));
      auto guide=recorder.Guide();
      if(!recorder.error.empty()||guide.empty()){
        RECT hint=preedit;hint.left=label.right+px(8);
        draw(recorder.error.empty()?L"暂无系统笔顺":recorder.error,hint,Blend(background,ink,55),DT_LEFT|DT_VCENTER|DT_SINGLELINE|DT_END_ELLIPSIS);
      }else{
        int cell=px(points+10),available=(std::max<int>)(1,(preedit.right-label.right-px(12))/cell);
        size_t first=recorder.code.size()>static_cast<size_t>(available)?recorder.code.size()-available:0;
        for(size_t i=first;i<guide.size()&&i-first<static_cast<size_t>(available);++i){
          RECT box{label.right+px(8)+static_cast<LONG>((i-first)*cell),preedit.top,label.right+px(8)+static_cast<LONG>((i-first+1)*cell),preedit.bottom};
          auto role=guide[i].role;
          COLORREF color=role==BihuaPersonalRecorder::GuideRole::Changed?selected:
                         Blend(background,ink,role==BihuaPersonalRecorder::GuideRole::Reference?35:90);
          DrawToolIcon(dc,guide[i].index,box,color);
        }
      }
    } else if (!ctx.preedit.str.empty()) {
      surface(preedit, Blend(background, ink, 2), 10, 8);
      HFONT previewFont = Font((std::max)(8, points - 2));
      SelectObject(dc, previewFont);
      RECT r = preedit;
      r.left += px(8);
      r.right -= px(8);
      auto value = ctx.preedit.str;
      SIZE textSize{}, ellipsis{};
      GetTextExtentPoint32W(dc, value.c_str(), static_cast<int>(value.size()),
                            &textSize);
      if (textSize.cx > r.right - r.left) {
        GetTextExtentPoint32W(dc, L"…", 1, &ellipsis);
        size_t begin = 0;
        do {
          ++begin;
          if (begin < value.size() && value[begin] >= 0xdc00 &&
              value[begin] <= 0xdfff)
            ++begin;
          GetTextExtentPoint32W(dc, value.c_str() + begin,
                                static_cast<int>(value.size() - begin),
                                &textSize);
        } while (begin < value.size() &&
                 textSize.cx + ellipsis.cx > r.right - r.left);
        value = L"…" + value.substr(begin);
      }
      draw(value, r, Blend(background, ink, 55),
           DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
      SelectObject(dc, font);
      DeleteObject(previewFont);
    }
    BitBlt(target, 0, 0, area.right, area.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, oldFont);
    DeleteObject(font);
    SelectObject(dc, oldBitmap);
    DeleteObject(bitmap);
    DeleteDC(dc);
    EndPaint(hwnd, &paint);
    auto visible_generation = generation;
    auto visible_revision = projection_revision;
    auto visible_base = base;
    auto count = enabled && profileVisible && targetVisible && IsWindowVisible(hwnd) ? VisibleCount() : 0;
    lock.unlock();
    // No Rime calls on the UI thread and no backend lock while holding mutex.
    if (count && displayed) displayed(visible_generation,visible_revision,visible_base,count);
  }
};
