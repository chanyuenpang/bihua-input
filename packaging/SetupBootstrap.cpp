#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <commctrl.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <stdexcept>

namespace fs=std::filesystem;
static HWND window{},status{},button{};
static std::wstring last_error;
static bool working=false,finished=false;
static std::wstring quote(const std::wstring& text) { return L"\""+text+L"\""; }
static std::wstring psquote(std::wstring text) {
  size_t pos=0;while((pos=text.find(L"'",pos))!=std::wstring::npos){text.insert(pos,L"'");pos+=2;}
  return L"'"+text+L"'";
}
static DWORD execute(const fs::path& exe,const std::wstring& parameters) {
  std::wstring command=quote(exe.wstring())+L" "+parameters;
  STARTUPINFOW start{sizeof(start)};start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=SW_HIDE;
  PROCESS_INFORMATION process{};
  if(!CreateProcessW(exe.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,exe.parent_path().c_str(),&start,&process))throw std::runtime_error("Cannot launch installer runtime");
  const auto waited=WaitForSingleObject(process.hProcess,240000);DWORD result=1;
  if(waited==WAIT_OBJECT_0)GetExitCodeProcess(process.hProcess,&result);
  CloseHandle(process.hProcess);CloseHandle(process.hThread);return result;
}
static fs::path own_directory() {wchar_t path[32768]{};GetModuleFileNameW(nullptr,path,32768);return fs::path(path).parent_path();}
static fs::path destination() {
  PWSTR local{};if(FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData,0,nullptr,&local)))throw std::runtime_error("Cannot find LocalAppData");
  fs::path result=fs::path(local)/L"BihuaWeasel"/L"0.6.31";CoTaskMemFree(local);return result;
}
static fs::path powershell() {wchar_t system[32768]{};GetSystemDirectoryW(system,32768);return fs::path(system)/L"WindowsPowerShell/v1.0/powershell.exe";}
static void cleanup_after_exit(const fs::path& app) {
  if(fs::weakly_canonical(app)!=fs::weakly_canonical(destination()))return;
  const auto script=L"$bihuaTarget=[IO.Path]::GetFullPath("+psquote(app.wstring())+L");$bihuaExpected=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'BihuaWeasel/0.6.31';if($bihuaTarget -ne [IO.Path]::GetFullPath($bihuaExpected)){exit};Wait-Process -Id "+std::to_wstring(GetCurrentProcessId())+L" -ErrorAction SilentlyContinue;$r=Get-Content -LiteralPath (Join-Path $bihuaTarget 'user-install.json') -Raw|ConvertFrom-Json;if($r.status -ne 'uninstalled'){exit};for($i=0;$i -lt 8;$i++){try{Remove-Item -LiteralPath $bihuaTarget -Recurse -Force -ErrorAction Stop;break}catch{Start-Sleep -Seconds 2}}";
  std::wstring cmd=quote(powershell().wstring())+L" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "+quote(script);
  STARTUPINFOW start{sizeof(start)};start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=SW_HIDE;PROCESS_INFORMATION process{};
  if(CreateProcessW(powershell().c_str(),cmd.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&start,&process)){CloseHandle(process.hThread);CloseHandle(process.hProcess);}
}
static void extract(const fs::path& target) {
#ifndef BIHUA_UNINSTALL
  if(fs::exists(target/L"release-manifest.json"))return;
  if(fs::exists(target)&&!fs::is_empty(target))throw std::runtime_error("Destination is not empty");
  fs::create_directories(target);
  auto resource=FindResourceW(nullptr,L"PAYLOAD",RT_RCDATA);
  if(!resource)throw std::runtime_error("Missing payload");
  auto bytes=LockResource(LoadResource(nullptr,resource));const DWORD length=SizeofResource(nullptr,resource);
  GUID id{};CoCreateGuid(&id);wchar_t name[48]{};StringFromGUID2(id,name,48);
  const auto zip=target.parent_path()/(std::wstring(L"bihua-payload-")+name+L".zip");
  {std::ofstream file(zip,std::ios::binary);file.write(static_cast<const char*>(bytes),length);if(!file)throw std::runtime_error("Cannot write payload");}
  const std::wstring script=L"$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';Expand-Archive -LiteralPath "+psquote(zip.wstring())+L" -DestinationPath "+psquote(target.wstring())+L" -Force";
  const DWORD result=execute(powershell(),L"-NoProfile -ExecutionPolicy Bypass -Command "+quote(script));
  fs::remove(zip);if(result)throw std::runtime_error("Cannot extract payload");
#endif
}
static DWORD install(const fs::path& target,bool validation) {
  extract(target);
  return execute(target/L"python/python.exe",L"-B "+quote((target/L"scripts/Install-Release.py").wstring())+(validation?L" validate":L" install"));
}
static LRESULT CALLBACK procedure(HWND hwnd,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND&&LOWORD(wp)==100) {
    if(finished){DestroyWindow(hwnd);return 0;}
    if(working)return 0;
    working=true;EnableWindow(button,FALSE);SetWindowTextW(status,L"正在安装，请稍候…");
    std::thread([hwnd]{DWORD result=1;try{result=install(destination(),false);}catch(...){last_error=L"安装文件未能解包或运行。";}PostMessageW(hwnd,WM_APP+1,result,0);}).detach();return 0;
  }
  if(message==WM_APP+1) {
    finished=true;working=false;EnableWindow(button,TRUE);SetWindowTextW(button,L"完成");
    if(wp==0)SetWindowTextW(status,L"安装完成。已打开的软件需重新打开后生效。\n也可保存工作后注销并重新登录 Windows。");
    else {SetWindowTextW(status,L"安装未完成。原有资料已保留。");MessageBoxW(hwnd,(L"请查看安装日志：\n"+(destination()/L"installation-error.log").wstring()+L"\n"+last_error).c_str(),L"笔画输入法安装",MB_ICONERROR);}
    return 0;
  }
  if(message==WM_CLOSE){if(!working)DestroyWindow(hwnd);return 0;}
  if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
  return DefWindowProcW(hwnd,message,wp,lp);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR,int) {
  SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  int argc=0;LPWSTR* argv=CommandLineToArgvW(GetCommandLineW(),&argc);
  try {
#ifdef BIHUA_UNINSTALL
    if(MessageBoxW(nullptr,L"卸载笔画输入法？\n\n个人词库和学习记录会保留。",L"卸载笔画输入法",MB_OKCANCEL|MB_ICONQUESTION)!=IDOK)return 0;
    auto app=own_directory();DWORD result=execute(app/L"python/python.exe",L"-B "+quote((app/L"scripts/Install-Release.py").wstring())+L" uninstall");
    if(!result){MessageBoxW(nullptr,L"已卸载。个人词库和共享输入法组件已保留。",L"笔画输入法",MB_OK);cleanup_after_exit(app);}
    else MessageBoxW(nullptr,L"卸载未完成，请查看安装目录中的 installation-error.log。",L"笔画输入法",MB_ICONERROR);
    return static_cast<int>(result);
#else
    if(argc==3&&!wcscmp(argv[1],L"/validate"))return static_cast<int>(install(fs::path(argv[2]),true));
    if(argc==3&&!wcscmp(argv[1],L"/extract-only")){extract(fs::path(argv[2]));return 0;}
    WNDCLASSW cls{};cls.lpfnWndProc=procedure;cls.hInstance=instance;cls.hCursor=LoadCursor(nullptr,IDC_ARROW);cls.hbrBackground=reinterpret_cast<HBRUSH>(COLOR_WINDOW+1);cls.lpszClassName=L"BihuaInstaller";RegisterClassW(&cls);
    const double scale=GetDpiForSystem()/96.0;
    window=CreateWindowW(cls.lpszClassName,L"安装笔画输入法 0.6.31 测试版",WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,100,100,static_cast<int>(610*scale),static_cast<int>(350*scale),nullptr,nullptr,instance,nullptr);
    HFONT font=CreateFontW(-static_cast<int>(17*scale),0,0,0,400,0,0,0,DEFAULT_CHARSET,0,0,ANTIALIASED_QUALITY,0,L"Microsoft YaHei UI");
    auto child=[&](LPCWSTR type,LPCWSTR text,int x,int y,int width,int height,int id,DWORD style){auto h=CreateWindowW(type,text,WS_CHILD|WS_VISIBLE|style,static_cast<int>(x*scale),static_cast<int>(y*scale),static_cast<int>(width*scale),static_cast<int>(height*scale),window,reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),instance,nullptr);SendMessageW(h,WM_SETFONT,reinterpret_cast<WPARAM>(font),TRUE);return h;};
    child(L"STATIC",L"笔画输入法",30,24,540,30,1,0);
    child(L"STATIC",L"五键输入 · 分词与通配 · 本地联想 · 自定义键位",30,72,540,30,2,0);
    child(L"STATIC",L"开源码表测试版。无需另装 Python 或小狼毫。\n首次安装可能需要管理员确认。个人词库不会被覆盖。",30,116,540,65,3,0);
    status=child(L"STATIC",L"准备安装到本机用户目录。",30,196,540,45,4,0);
    button=child(L"BUTTON",L"安装",420,254,145,38,100,WS_TABSTOP|BS_DEFPUSHBUTTON);
    ShowWindow(window,SW_SHOW);MSG msg{};while(GetMessageW(&msg,nullptr,0,0)>0){if(!IsDialogMessageW(window,&msg)){TranslateMessage(&msg);DispatchMessageW(&msg);}}
    DeleteObject(font);LocalFree(argv);return 0;
#endif
  }catch(...){if(argc<=1)MessageBoxW(nullptr,L"安装程序未能完成。请将安装包放在本机磁盘并重试。",L"笔画输入法",MB_ICONERROR);return 1;}
}
