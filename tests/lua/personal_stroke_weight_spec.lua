local M={}
function M.run()
  local old_yield=yield
  local ok,error=pcall(function()
    local data={codes={['一']='hh',['中']='ss',['龘']='ps'},prefixes={
      h={{'一',90,0}},hh={{'一',90,1}},s={{'中',50,0}},ss={{'中',50,1}},
      p={{'龘',10,0}},ps={{'龘',10,1}}}}
    local alias={revision=1,by_char={['中']='hh',['龘']='hhh'},prefixes={h={'中','龘'},hh={'中','龘'},hhh={'龘'}}}
    local runtime=require('bihua_personal_stroke_runtime')
    local env={data=data,personal_runtime={refresh=function() return alias end,weight=runtime.weight},
      personal_strokes=alias,phrase_alias_revision=1,format_preedit=function(s) return s end,
      engine={context={set_property=function() end}}}
    local output={};yield=function(candidate) output[#output+1]=candidate end
    require('bihua_matcher').func('h',{start=0,_end=1},env)
    assert(#output==3 and output[1].text=='一' and output[2].text=='中' and output[3].text=='龘',
           'personal spellings must merge by original weights, never be pinned')
    alias.prefixes.h={'一','中','龘'} -- A redundant alias cannot move a normal candidate.
    output={};require('bihua_matcher').func('h',{start=0,_end=1},env)
    assert(#output==3 and output[1].text=='一' and output[2].text=='中' and output[3].text=='龘')
    output={};require('bihua_phrase_runtime').translate('h?',{start=0,_end=2},env)
    assert(#output==3 and output[1].text=='一' and output[2].text=='中' and output[3].text=='龘',
           'wildcards must not give aliases an artificial score')
    assert(runtime.weight(data,'中',1)==50 and runtime.weight(data,'龘',1)==10)
    assert(runtime.weight(data,'龘',20)==10 and runtime.weight(data,'未知',1)==0)
    local tails={codes={['一']='hh',['中']='ss'},tails={['一']={[1]={{'一',100,'hh'}}},['中']={[1]={{'一',100,'hh'}}}}}
    local phone=require('bihua_phone_phrases')
    local normal=phone.query('s|h',data,tails,120)
    local custom=phone.query('h|h',data,tails,120,alias)
    local found
    for _,row in ipairs(custom) do if row.text=='中一' then found=row end end
    assert(found and normal[1].text=='中一' and found.score==normal[1].score,
           'phrase scores must be identical through original and personal spellings')
    assert(custom[1].text=='一一','a personal head must not outrank a heavier ordinary head')
  end)
  yield=old_yield;assert(ok,error)
  return 'PASS: aliases preserve original weights in direct, wildcard and phrase queries'
end
return M
