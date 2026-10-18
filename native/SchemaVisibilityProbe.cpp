#include <windows.h>
#include <rime_api.h>
#include <rime_levers_api.h>
#include <string>
#include <stdio.h>
std::string utf8(const wchar_t* text) {
  int length=WideCharToMultiByte(CP_UTF8,0,text,-1,nullptr,0,nullptr,nullptr);
  std::string out(length,'\0');WideCharToMultiByte(CP_UTF8,0,text,-1,out.data(),length,nullptr,nullptr);out.pop_back();return out;
}
int wmain(int count,wchar_t** args) {
  if(count!=3)return 2;
  auto shared=utf8(args[1]),user=utf8(args[2]);
  RIME_STRUCT(RimeTraits,traits);traits.shared_data_dir=shared.c_str();traits.user_data_dir=user.c_str();
  traits.prebuilt_data_dir=shared.c_str();traits.app_name="rime.bihua_catalog_probe";traits.log_dir="";traits.min_log_level=2;
  auto api=rime_get_api();api->setup(&traits);api->deployer_initialize(nullptr);
  auto module=api->find_module("levers");if(!module)return 3;
  auto levers=reinterpret_cast<RimeLeversApi*>(module->get_api());auto settings=levers->switcher_settings_init();
  if(!levers->load_settings(reinterpret_cast<RimeCustomSettings*>(settings)))return 4;
  RimeSchemaList available{},selected{};
  levers->get_available_schema_list(settings,&available);levers->get_selected_schema_list(settings,&selected);
  for(size_t i=0;i<available.size;i++)printf("available\t%s\t%s\n",available.list[i].schema_id,available.list[i].name);
  for(size_t i=0;i<selected.size;i++)printf("selected\t%s\t%s\n",selected.list[i].schema_id,selected.list[i].name);
  levers->schema_list_destroy(&available);levers->schema_list_destroy(&selected);
  levers->custom_settings_destroy(reinterpret_cast<RimeCustomSettings*>(settings));api->finalize();return 0;
}
