-- Deterministic local feedback. Exposure episodes belong to the Rime adapter.
local M, State = {}, {}
State.__index = State
local function chars(text)
  local out={}; for _, cp in utf8.codes(text) do out[#out+1]=utf8.char(cp) end; return out
end
local function han(text)
  if type(text)~="string" or utf8.len(text)~=1 then return false end
  local cp=utf8.codepoint(text)
  return (cp>=0x3400 and cp<=0x9fff) or (cp>=0xf900 and cp<=0xfaff) or (cp>=0x20000 and cp<=0x323af)
end
local function integer(x, minimum, maximum)
  return type(x)=="number" and x%1==0 and x>=minimum and x<math.huge and (not maximum or x<=maximum)
end
function M.new(capacity, options)
  capacity, options=capacity or 1000, options or {}
  assert(integer(capacity,1,5000), "Invalid history capacity")
  return setmetatable({capacity=capacity, clock=options.clock or os.time,
    window={}, segment=1, sequence=0, context={}, confirmed={}, confirmed_index={}, revision=0, offered={}}, State)
end
function State:invalidate() self.revision=self.revision+1; self.offered={} end
function State:boundary() self.segment=self.segment+1; self.context={}; self:invalidate() end
function State:observe(text, provenance)
  if provenance~="manual_stroke_char" or not han(text) then self:boundary(); return false end
  self.sequence=self.sequence+1
  self.window[#self.window+1]={text=text,segment=self.segment,sequence=self.sequence,observed_at=self.clock()}
  if #self.window>self.capacity then table.remove(self.window,1) end
  self.context[#self.context+1]=text
  if #self.context>3 then table.remove(self.context,1) end
  self:invalidate(); return true
end
function State:index_confirmed(phrase)
  local usage=self.confirmed[phrase]
  if usage.positive_count==0 then return end -- Negative-only feedback is not a confirmed vocabulary entry.
  local pieces=chars(phrase); local context=table.concat(pieces,"",1,#pieces-1)
  local bucket=self.confirmed_index[context] or {}; local found=false
  for _, existing in ipairs(bucket) do if existing==phrase then found=true; break end end
  if not found then bucket[#bucket+1]=phrase end
  table.sort(bucket,function(a,b)
    local x,y=self.confirmed[a],self.confirmed[b]
    if x.score~=y.score then return x.score>y.score end
    if x.recent~=y.recent then return x.recent>y.recent end
    return a<b
  end)
  if #bucket>200 then table.remove(bucket) end
  self.confirmed_index[context]=bucket
end
local function compare(a,b)
  if a.context_length~=b.context_length then return a.context_length>b.context_length end
  if a.score~=b.score then return a.score>b.score end
  if a.count~=b.count then return a.count>b.count end
  if a.recent~=b.recent then return a.recent>b.recent end
  return a.phrase<b.phrase
end
function State:query(limit, static_rows)
  limit=limit or 45; assert(integer(limit,1,90)); self:invalidate()
  if #self.context==0 then return {} end
  local temporary, personal, static, blocked={},{},{},{}
  for length=1,math.min(3,#self.context) do
    local context=table.concat(self.context,"",#self.context-length+1)
    local observed={}
    for start=1,#self.window-length do
      local good,pieces=true,{}; local segment=self.window[start].segment
      for offset=0,length-1 do
        local event=self.window[start+offset]
        if event.segment~=segment then good=false; break end
        pieces[#pieces+1]=event.text
      end
      local event=self.window[start+length]
      if good and table.concat(pieces)==context and event.segment==segment then
        local phrase=context..event.text
        local row=observed[phrase] or {source="provisional",context=context,context_length=length,
          suffix=event.text,phrase=phrase,count=0,recent=0}
        row.count=row.count+1; row.recent=math.max(row.recent,event.sequence); observed[phrase]=row
      end
    end
    for phrase,row in pairs(observed) do
      local usage=self.confirmed[phrase]
      row.score=usage and usage.score or 10
      if row.score==0 then
        if row.recent>(usage.hidden_sequence or usage.recent) then row.reactivation=true; row.score=10
        else blocked[row.suffix]=math.max(blocked[row.suffix] or 0,length) end
      end
      if row.score>0 then temporary[#temporary+1]=row end
    end
    for _,phrase in ipairs(self.confirmed_index[context] or {}) do
      local usage=self.confirmed[phrase]; local suffix=phrase:sub(#context+1)
      if usage.score==0 then blocked[suffix]=math.max(blocked[suffix] or 0,length)
      else personal[#personal+1]={source="personal",context=context,context_length=length,phrase=phrase,
        suffix=suffix,count=usage.positive_count,score=usage.score,recent=usage.recent} end
    end
  end
  for rank,row in ipairs(static_rows or {}) do
    if rank>200 then break end; assert(han(row.suffix))
    local context=self.context[#self.context]; local phrase=context..row.suffix; local usage=self.confirmed[phrase]
    local score=usage and usage.score or 10
    if score==0 then blocked[row.suffix]=math.max(blocked[row.suffix] or 0,1)
    else static[#static+1]={source="static",context=context,context_length=1,suffix=row.suffix,phrase=phrase,
      count=row.weight or 0,score=score,recent=usage and usage.recent or 0,rank=rank} end
  end
  table.sort(personal,compare); table.sort(temporary,compare)
  local preferred={}
  local priority={personal=3,provisional=2,static=1}
  for _,group in ipairs({personal,temporary,static}) do
    for _,row in ipairs(group) do
      local old=preferred[row.suffix]
      if not old or row.context_length>old.context_length or
        (row.context_length==old.context_length and (row.reactivation and 4 or priority[row.source])>
          (old.reactivation and 4 or priority[old.source])) then preferred[row.suffix]=row end
    end
  end
  local result,low,used={},{},{}
  local function add(row)
    if not row or used[row.suffix] or preferred[row.suffix]~=row then return false end
    if blocked[row.suffix] and row.context_length<=blocked[row.suffix] and not row.reactivation then return end
    -- Feedback identity survives cache eviction and negative-only records.
    -- A shorter static edge must not bypass the longest matching feedback.
    for length=row.context_length,math.min(3,#self.context) do
      local edge=table.concat(self.context,"",#self.context-length+1)..row.suffix
      local record=self.confirmed[edge]
      if record and record.score==0 and not (row.reactivation and row.phrase==edge) then return end
      if record and not row.reactivation then
        row.context=table.concat(self.context,"",#self.context-length+1)
        row.context_length=length;row.phrase=edge;row.score=record.score
        row.recent=record.recent
      end
    end
    used[row.suffix]=true
    if row.score<10 then low[#low+1]=row else result[#result+1]=row end
    return true
  end
  -- Stable normal-score order retains personal priority and one discovery slot.
  local first=0
  for _,row in ipairs(personal) do
    if row.score>=10 and first<math.min(limit,9)-(#temporary>0 and 1 or 0) and add(row) then first=first+1 end
  end
  for _,row in ipairs(temporary) do if row.score>=10 and add(row) then break end end
  for _,row in ipairs(personal) do add(row) end
  for _,row in ipairs(static) do add(row) end
  for _,row in ipairs(temporary) do add(row) end
  while #result>limit do table.remove(result) end
  table.sort(low,compare)
  -- Insert weaker edges progressively later; never create empty placeholders.
  for i=#low,1,-1 do
    local row=low[i]; local earliest=1+math.ceil((10-row.score)*(limit-1)/9)
    table.insert(result,math.min(earliest,#result+1),row)
    while #result>limit do table.remove(result) end
  end
  for _,row in ipairs(result) do
    row.revision=self.revision; row.id=row.source.."\t"..row.context.."\t"..row.suffix
    self.offered[row.id]=row
  end
  return result
end
function State:valid(row)
  return type(row)=="table" and row.revision==self.revision and self.offered[row.id]==row
end
function State:feedback(row, positive)
  local usage=self.confirmed[row.phrase] or {score=10,positive_count=0,negative_count=0,
    recent=0,last_feedback_at=0,hidden_sequence=0,origin=row.source}
  if positive then
    usage.score=row.reactivation and 10 or math.min(20,usage.score+1)
    usage.positive_count=usage.positive_count+1
  else
    usage.score=math.max(0,usage.score-1); usage.negative_count=usage.negative_count+1
  end
  usage.recent=self.sequence; usage.last_feedback_at=self.clock()
  if usage.score==0 then usage.hidden_sequence=self.sequence end
  self.confirmed[row.phrase]=usage; self:index_confirmed(row.phrase)
end
function State:ignore(visible)
  local changed,seen=false,{}
  for _,row in ipairs(visible or {}) do
    if self:valid(row) and not seen[row.phrase] then self:feedback(row,false);seen[row.phrase]=true;changed=true end
  end
  return changed
end
function State:select(row,explicit,visible)
  if not self:valid(row) then return false,"stale_candidate" end
  if explicit then
    self:feedback(row,true)
    local other={}; for _,candidate in ipairs(visible or {}) do if candidate.phrase~=row.phrase then other[#other+1]=candidate end end
    self:ignore(other)
  end
  local continuation={}; for i,char in ipairs(self.context) do continuation[i]=char end
  continuation[#continuation+1]=row.suffix
  if #continuation>3 then table.remove(continuation,1) end
  self:boundary();self.context=continuation
  return explicit,explicit and "confirmed" or "excluded_prediction"
end
function State:clear_window() self.window={};self:boundary() end
function State:delete_phrase(phrase)
  self.confirmed[phrase]=nil
  for _,bucket in pairs(self.confirmed_index) do
    for i,value in ipairs(bucket) do if value==phrase then table.remove(bucket,i);break end end
  end
  self:invalidate()
end
function State:snapshot()
  local out={version=2,policy="shown_choice_v1",capacity=self.capacity,sequence=self.sequence,
    segment=self.segment,window={},confirmed={}}
  for i,event in ipairs(self.window) do
    out.window[i]={text=event.text,segment=event.segment,sequence=event.sequence,observed_at=event.observed_at}
  end
  for phrase,usage in pairs(self.confirmed) do
    out.confirmed[phrase]={score=usage.score,positive_count=usage.positive_count,negative_count=usage.negative_count,
      recent=usage.recent,last_feedback_at=usage.last_feedback_at,hidden_sequence=usage.hidden_sequence,origin=usage.origin}
  end
  return out
end
function M.restore(snapshot,options)
  options=options or {}; assert(snapshot.version==1 or snapshot.version==2,"Unsupported association version")
  local state=M.new(snapshot.capacity,options)
  assert(integer(snapshot.sequence,0) and integer(snapshot.segment,1) and #snapshot.window<=state.capacity)
  state.sequence,state.segment=snapshot.sequence,snapshot.segment+1
  local previous=0
  for _,event in ipairs(snapshot.window) do
    assert(han(event.text) and integer(event.sequence,previous+1,state.sequence) and
      integer(event.segment,1,snapshot.segment) and event.observed_at>=0 and event.observed_at<math.huge)
    state.window[#state.window+1]={text=event.text,segment=event.segment,sequence=event.sequence,observed_at=event.observed_at}
    previous=event.sequence
  end
  local migration_now=options.migration_now or state.clock()
  if snapshot.version==1 then
    assert(snapshot.half_life>0 and snapshot.half_life<math.huge and snapshot.maximum_strength>=snapshot.minimum_weight and snapshot.minimum_weight>0)
    state.migration_required=true;state.migration_now=migration_now
  else assert(snapshot.policy=="shown_choice_v1") end
  for phrase,usage in pairs(snapshot.confirmed) do
    local pieces=chars(phrase);assert(#pieces>=2 and #pieces<=8)
    for _,char in ipairs(pieces) do assert(han(char)) end
    local record
    if snapshot.version==1 then
      assert(integer(usage.count,1) and usage.strength>=0 and usage.strength<=snapshot.maximum_strength and usage.last_used_at>=0 and usage.last_used_at<math.huge)
      local effective=usage.strength*2^(-math.max(0,migration_now-usage.last_used_at)/snapshot.half_life)
      -- Old records have no rejection history. Keep previously visible accepted
      -- edges in the normal 10..20 band rather than fabricating negative votes.
      local score=effective<snapshot.minimum_weight and 0 or
        math.min(20,10+math.floor(10*effective/snapshot.maximum_strength+0.5))
      record={score=score,positive_count=usage.count,negative_count=0,recent=usage.recent,
        last_feedback_at=usage.last_used_at,hidden_sequence=snapshot.sequence,origin="personal"}
    else
      assert(integer(usage.score,0,20) and integer(usage.positive_count,0) and integer(usage.negative_count,0) and
        integer(usage.hidden_sequence,0,snapshot.sequence) and usage.last_feedback_at>=0 and usage.last_feedback_at<math.huge and
        (usage.origin=="personal" or usage.origin=="provisional" or usage.origin=="static"))
      record={score=usage.score,positive_count=usage.positive_count,negative_count=usage.negative_count,
        recent=usage.recent,last_feedback_at=usage.last_feedback_at,hidden_sequence=usage.hidden_sequence,origin=usage.origin}
    end
    assert(integer(record.recent,0,state.sequence)); state.confirmed[phrase]=record;state:index_confirmed(phrase)
  end
  return state
end
return M
