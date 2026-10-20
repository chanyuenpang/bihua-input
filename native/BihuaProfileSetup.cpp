#define UNICODE
#define _UNICODE
#include <windows.h>
#include <msctf.h>
#include <atlbase.h>
#include <filesystem>
#include <fstream>
#include <string>
#include "BihuaLegacyStartup.h"

static const GUID BihuaClass={0x1d31bf35,0xf1b8,0x4352,{0x98,0x0e,0xb3,0x37,0x26,0x4d,0x82,0xfb}};
static const GUID BihuaProfile={0x49504670,0x200c,0x4a58,{0x9a,0x4f,0x72,0xb7,0xdc,0x6c,0xfb,0xa2}};
static const GUID StockClass={0xa3f4cded,0xb1e9,0x41ee,{0x9c,0xa6,0x7b,0x4d,0x0d,0xe6,0xcb,0x0a}};
static const GUID StockProfile={0x3d02cab6,0x2b8e,0x4781,{0xba,0x20,0x1c,0x92,0x67,0x52,0x94,0x67}};

int wmain(int argc,wchar_t** argv) {
  const bool machine=argc==4 && !wcscmp(argv[1],L"--machine");
  const bool activate=argc==4 && !wcscmp(argv[1],L"--activate");
  const bool inspect=argc==4 && !wcscmp(argv[1],L"--inspect");
  const bool restore=(argc==5||argc==7) && !wcscmp(argv[1],L"--restore-user");
  const bool option=machine||activate||inspect||restore;
  if(argc!=3 && !option)return 2;
  auto directory=std::filesystem::path(argv[option?2:1]);
  std::ofstream report{std::filesystem::path(argv[option?3:2])};
  BihuaLegacyStartup legacy;
  auto finish=[&](const char* phase,HRESULT hr){
    LONG recovery=FAILED(hr)?legacy.Rollback():ERROR_SUCCESS;
    report<<"{\"phase\":\""<<phase<<"\",\"hresult\":"<<static_cast<unsigned long>(hr)<<",\"legacy_run_removed\":"<<legacy.removed.size()<<",\"legacy_run_recovery\":"<<recovery<<"}";return FAILED(hr)?1:0;
  };
  HRESULT hr=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
  if(FAILED(hr))return finish("COM_initialize",hr);
  if(inspect||restore) {
    CComPtr<ITfInputProcessorProfiles> profiles;
    hr=profiles.CoCreateInstance(CLSID_TF_InputProcessorProfiles);
    if(FAILED(hr))return finish("profile_preferences",hr);
    BOOL own_enabled=FALSE,stock_enabled=FALSE;
    if(restore) {
      hr=profiles->EnableLanguageProfile(BihuaClass,0x0804,BihuaProfile,!wcscmp(argv[4],L"2")?TRUE:FALSE);
      if(FAILED(hr))return finish("own_profile_disable",hr);
      if(!wcscmp(argv[4],L"1")) {
        hr=profiles->EnableLanguageProfile(StockClass,0x0804,StockProfile,TRUE);
        if(FAILED(hr))return finish("previous_profile_enable",hr);
        hr=profiles->SetDefaultLanguageProfile(0x0804,StockClass,StockProfile);
        if(FAILED(hr))return finish("previous_default",hr);
      }
      if(argc==7) {
        GUID previous_class{},previous_profile{};
        if(FAILED(CLSIDFromString(argv[5],&previous_class))||FAILED(CLSIDFromString(argv[6],&previous_profile)))
          return finish("previous_default_parse",E_INVALIDARG);
        hr=profiles->SetDefaultLanguageProfile(0x0804,previous_class,previous_profile);
        if(FAILED(hr))return finish("previous_default_restore",hr);
      }
      return finish("user_profile_restored",S_OK);
    }
    hr=profiles->IsEnabledLanguageProfile(BihuaClass,0x0804,BihuaProfile,&own_enabled);
    if(FAILED(hr))return finish("own_profile_query",hr);
    profiles->IsEnabledLanguageProfile(StockClass,0x0804,StockProfile,&stock_enabled);
    CLSID current_class{};GUID current_profile{};
    hr=profiles->GetDefaultLanguageProfile(0x0804,GUID_TFCAT_TIP_KEYBOARD,&current_class,&current_profile);
    if(FAILED(hr))return finish("default_profile_query",hr);
    const bool own_default=IsEqualGUID(current_class,BihuaClass)&&IsEqualGUID(current_profile,BihuaProfile);
    wchar_t class_text[40]{},profile_text[40]{};
    StringFromGUID2(current_class,class_text,40);StringFromGUID2(current_profile,profile_text,40);
    const std::wstring wc(class_text),wp(profile_text);
    const std::string previous_class(wc.begin(),wc.end()),previous_profile(wp.begin(),wp.end());
    report<<"{\"phase\":\"inspected\",\"hresult\":0,\"own_enabled\":"<<(own_enabled?"true":"false")
          <<",\"stock_enabled\":"<<(stock_enabled?"true":"false")<<",\"own_default\":"<<(own_default?"true":"false")
          <<",\"default_class\":\""<<previous_class<<"\",\"default_profile\":\""<<previous_profile<<"\"}";
    return 0;
  }
  if(machine) {
    wchar_t program_files[32768]{};
    if(!GetEnvironmentVariableW(L"ProgramFiles",program_files,32768))return finish("program_directory",E_FAIL);
    const auto destination=std::filesystem::path(program_files)/L"BihuaInputMethod"/L"0.5.12";
    std::error_code error;
    std::filesystem::create_directories(destination,error);
    if(error)return finish("protected_directory",HRESULT_FROM_WIN32(error.value()));
    for(const auto* name:{L"bihua64.dll",L"bihua32.dll",L"LICENSE.txt"}) {
      const auto source=directory/name,target=destination/name;
      if(std::filesystem::exists(target)) {
        std::ifstream left(source,std::ios::binary),right(target,std::ios::binary);
        std::string a((std::istreambuf_iterator<char>(left)),{}),b((std::istreambuf_iterator<char>(right)),{});
        if(a!=b)return finish("existing_binary_conflict",E_UNEXPECTED);
      } else {
        std::filesystem::copy_file(source,target,std::filesystem::copy_options::none,error);
        if(error)return finish("frontend_copy",HRESULT_FROM_WIN32(error.value()));
      }
    }
    auto retired=legacy.Retire(destination/L"legacy-startup-backup",(std::filesystem::path(program_files)/L"Rime/weasel-0.17.4/WeaselServer.exe").wstring());
    if(retired)return finish("legacy_startup_retirement",HRESULT_FROM_WIN32(retired));
    directory=destination;
  }
  const std::wstring key=L"Software\\Classes\\CLSID\\{1D31BF35-F1B8-4352-980E-B337264D82FB}\\InprocServer32";
  if(!activate)for(auto view:{KEY_WOW64_64KEY,KEY_WOW64_32KEY}) {
    HKEY registry{};
    LONG result=RegCreateKeyExW(machine?HKEY_LOCAL_MACHINE:HKEY_CURRENT_USER,key.c_str(),0,nullptr,0,KEY_WRITE|view,nullptr,&registry,nullptr);
    if(result)return finish("class_registration",HRESULT_FROM_WIN32(result));
    const auto file=(directory/(view==KEY_WOW64_64KEY?L"bihua64.dll":L"bihua32.dll")).wstring();
    result=RegSetValueExW(registry,nullptr,0,REG_SZ,reinterpret_cast<const BYTE*>(file.c_str()),static_cast<DWORD>((file.size()+1)*sizeof(wchar_t)));
    if(!result)result=RegSetValueExW(registry,L"ThreadingModel",0,REG_SZ,reinterpret_cast<const BYTE*>(L"Apartment"),sizeof(L"Apartment"));
    RegCloseKey(registry);
    if(result)return finish("class_registration",HRESULT_FROM_WIN32(result));
  }
  auto module=LoadLibraryW((directory/L"bihua64.dll").c_str());
  if(!module)return finish("frontend_load",HRESULT_FROM_WIN32(GetLastError()));
  CComPtr<ITfInputProcessorProfileMgr> manager;
  hr=manager.CoCreateInstance(CLSID_TF_InputProcessorProfiles);
  if(FAILED(hr))return finish("profile_manager",hr);
  const auto icon=(directory/L"bihua64.dll").wstring();
  const std::wstring description=L"笔画输入法";
  if(!activate) {
    hr=manager->RegisterProfile(BihuaClass,0x0804,BihuaProfile,description.c_str(),static_cast<ULONG>(description.size()),
          icon.c_str(),static_cast<ULONG>(icon.size()),0,nullptr,0,machine?FALSE:TRUE,0);
    if(FAILED(hr))return finish("profile_registration",hr);
  }
  CComPtr<ITfCategoryMgr> categories;
  hr=categories.CoCreateInstance(CLSID_TF_CategoryMgr);
  if(FAILED(hr))return finish("category_manager",hr);
  const GUID supported[]={GUID_TFCAT_TIP_KEYBOARD,GUID_TFCAT_TIPCAP_SECUREMODE,GUID_TFCAT_TIPCAP_UIELEMENTENABLED,
       GUID_TFCAT_TIPCAP_INPUTMODECOMPARTMENT,GUID_TFCAT_TIPCAP_COMLESS,GUID_TFCAT_TIPCAP_IMMERSIVESUPPORT,
       GUID_TFCAT_TIPCAP_SYSTRAYSUPPORT,GUID_TFCAT_DISPLAYATTRIBUTEPROVIDER,GUID_TFCAT_DISPLAYATTRIBUTEPROPERTY};
  if(!activate)for(const auto& category:supported) {
    hr=categories->RegisterCategory(BihuaClass,category,BihuaClass);
    if(FAILED(hr))return finish("category_registration",hr);
  }
  if(machine)return finish("machine_registered",S_OK);
  CComPtr<ITfInputProcessorProfiles> profiles;
  hr=profiles.CoCreateInstance(CLSID_TF_InputProcessorProfiles);
  if(FAILED(hr))return finish("profile_preferences",hr);
  hr=profiles->ChangeCurrentLanguage(0x0804);
  if(FAILED(hr))return finish("input_language",hr);
  hr=profiles->SetDefaultLanguageProfile(0x0804,BihuaClass,BihuaProfile);
  if(FAILED(hr))return finish("default_profile",hr);
  hr=manager->ActivateProfile(TF_PROFILETYPE_INPUTPROCESSOR,0x0804,BihuaClass,BihuaProfile,nullptr,
       TF_IPPMF_FORSESSION|TF_IPPMF_ENABLEPROFILE|TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE);
  if(FAILED(hr))return finish("profile_activation",hr);
  // Enabling a previously disabled profile can rewrite language defaults.
  // Persist the default after activation has completed.
  hr=profiles->SetDefaultLanguageProfile(0x0804,BihuaClass,BihuaProfile);
  if(FAILED(hr))return finish("default_profile_after_activation",hr);
  BOOL stock_enabled=FALSE;
  const HRESULT stock_query=profiles->IsEnabledLanguageProfile(StockClass,0x0804,StockProfile,&stock_enabled);
  if(SUCCEEDED(stock_query)) {
    hr=profiles->EnableLanguageProfile(StockClass,0x0804,StockProfile,FALSE);
    if(FAILED(hr))return finish("stock_profile_disable",hr);
  }
  report<<"{\"phase\":\"activated\",\"hresult\":0,\"stock_enabled_before\":"<<(stock_enabled?"true":"false")<<"}";
  return 0;
}
