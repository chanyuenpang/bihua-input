"""Give the derivative TSF frontend its own stable Windows identity."""
import json
from pathlib import Path
import re
import uuid

root=Path(__file__).resolve().parent.parent
source=root/'.verification/weasel-native/weasel-0.17.4'
identity=json.loads((root/'native/bihua-profile-identity.json').read_text())
globals=source/'WeaselTSF/Globals.cpp'
text=globals.read_text(encoding='utf-8-sig')
for name,key in [('c_clsidTextService','clsid'),('c_guidProfile','profile'),('c_guidLangBarItemButton','language_bar'),('c_guidDisplayAttributeInput','display_attribute')]:
    raw=uuid.UUID(identity[key]);fields=raw.fields
    tail=', '.join('0x%02x'%n for n in raw.bytes[8:])
    definition='static const GUID '+name+' = {0x%08x, 0x%04x, 0x%04x, {%s}};'%(fields[0],fields[1],fields[2],tail)
    text,count=re.subn(r'static const GUID '+name+r'\s*=\s*\{.*?\};',definition,text,flags=re.S)
    assert count==1,name
globals.write_text(text,encoding='utf-8')
register=source/'WeaselTSF/Register.cpp'
text=register.read_text(encoding='utf-8-sig').replace('const auto text_service_desc = get_weasel_ime_name();','const std::wstring text_service_desc = L"笔画输入法";')
text=text.replace('text_service_desc.size() * sizeof(wchar_t)','text_service_desc.size()')
text=text.replace('const auto hkl_hans = FindIME(TEXTSERVICE_LANGID_HANS);','const HKL hkl_hans = nullptr;')
register.write_text(text,encoding='utf-8')
bar=source/'WeaselTSF/LanguageBar.cpp'
text=bar.read_text(encoding='utf-8-sig')
if '#include <filesystem>' not in text:text=text.replace('#include <thread>','#include <thread>\n#include <filesystem>')
old='''std::wstring WeaselTSF::_GetRootDir() {
  std::wstring dir{};
  RegGetStringValue(HKEY_LOCAL_MACHINE, GetWeaselRegName(), L"WeaselRoot", dir);
  return dir;
}'''
new='''std::wstring WeaselTSF::_GetRootDir() {
  wchar_t module[32768]{};
  GetModuleFileNameW(g_hInst, module, 32768);
  return std::filesystem::path(module).parent_path().wstring();
}'''
assert old in text or new in text
bar.write_text(text.replace(old,new),encoding='utf-8')
frontend=source/'WeaselTSF/WeaselTSF.cpp'
text=frontend.read_text(encoding='utf-8-sig')
old='''ShellExecuteW(NULL, L"open", (dir + L"\\\\start_service.bat").c_str(),
                        NULL, dir.c_str(), SW_HIDE);'''
new='''wchar_t system[32768]{};
          GetSystemDirectoryW(system, 32768);
          const std::wstring scheduler = std::wstring(system) + L"\\\\schtasks.exe";
          ShellExecuteW(NULL, L"open", scheduler.c_str(),
                        L"/Run /TN \\"BihuaInputMethod\\"", NULL, SW_HIDE);'''
assert old in text or new in text
frontend.write_text(text.replace(old,new),encoding='utf-8')
print('Independent TSF class/profile identity patched; stock identity remains separate.')
