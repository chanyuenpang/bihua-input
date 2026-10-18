local Core=require("bihua_association_core")
local Episode=require("bihua_feedback_episode")
local M={}
local function input(state,text) for _,cp in utf8.codes(text) do assert(state:observe(utf8.char(cp),"manual_stroke_char")) end end
local function context(state,text) state:boundary();input(state,text) end
local function find(rows,suffix) for i,row in ipairs(rows) do if row.suffix==suffix then return row,i end end end
local function static()
 local rows={{suffix="乙",weight=100000}}
 for cp=0x4e00,0x4e50 do rows[#rows+1]={suffix=utf8.char(cp),weight=100000-cp} end
 return rows
end
function M.run()
 local now=1000;local clock=function() return now end
 local s=Core.new(1000,{clock=clock});input(s,"星河计划");context(s,"星")
 local manual=#s.window
 for _,char in ipairs({"河","计","划"}) do
  local row=assert(find(s:query(45),char));assert(s:select(row,true,{row}))
 end
 assert(#s.window==manual and s.confirmed["星河"].score==11 and s.confirmed["星河计"].positive_count==1)
 assert(s.confirmed["星河计划"].positive_count==1)
 local quota=Core.new(1000)
 for i=1,1008 do input(quota,"甲") end
 assert(#quota.window==1000 and quota.window[1].sequence==9)
 -- Predictions do not concatenate manual training sequences.
 local excluded=Core.new(1000);input(excluded,"甲")
 local row=excluded:query(45,{{suffix="乙",weight=1}})[1];assert(excluded:select(row,true,{row}));input(excluded,"丙")
 context(excluded,"甲");assert(not find(excluded:query(45),"丙"))
 -- A visible episode is deduplicated and closed once, untouched pages stay at their implicit initial score.
 local scores=Core.new(1000,{clock=clock});input(scores,"甲");local rows=scores:query(45,static())
 local ep=Episode.new(rows,9);ep:expose(0);ep:expose(0)
 assert(#ep.visible==9);ep:expose(1);ep:expose(0);assert(#ep.visible==18)
 local selected=rows[10];assert(scores:select(selected,true,ep:close()));assert(not ep:close())
 assert(scores.confirmed[selected.phrase].score==11 and scores.confirmed[selected.phrase].positive_count==1)
 assert(scores.confirmed[rows[1].phrase].score==9 and scores.confirmed[rows[1].phrase].positive_count==0)
 assert(not scores.confirmed[rows[19].phrase],"Unseen page received negative feedback")
 -- Cap and calendar invariance.
 local bounded=Core.new(1000,{clock=clock})
 for i=1,30 do context(bounded,"甲");local candidate=assert(find(bounded:query(45,static()),"乙"));assert(bounded:select(candidate,true,{})) end
 assert(bounded.confirmed["甲乙"].score==20)
 local timestamp=bounded.confirmed["甲乙"].last_feedback_at;now=now+100000000
 context(bounded,"甲");assert(find(bounded:query(45,static()),"乙").score==20)
 assert(bounded.confirmed["甲乙"].last_feedback_at==timestamp)
 -- 10 normal, 9 and 8 progressively lower; 0 is an absorbing tombstone, not a static fallback.
 for i=1,10 do context(bounded,"甲");assert(bounded:ignore({(assert(find(bounded:query(45,static()),"乙")))})) end
 assert(bounded.confirmed["甲乙"].score==10)
 context(bounded,"甲");bounded:ignore({(assert(find(bounded:query(45,static()),"乙")))})
 context(bounded,"甲");local weaker,rank9=find(bounded:query(45,static()),"乙");assert(weaker.score==9 and rank9>=6)
 bounded:ignore({weaker});context(bounded,"甲");local lower,rank8=find(bounded:query(45,static()),"乙");assert(lower.score==8 and rank8>rank9 and rank8>=11)
 for i=1,8 do context(bounded,"甲");bounded:ignore({(assert(find(bounded:query(45,static()),"乙")))}) end
 context(bounded,"甲");assert(bounded.confirmed["甲乙"].score==0 and not find(bounded:query(45,static()),"乙"))
 local reloaded=Core.restore(bounded:snapshot(),{clock=clock});input(reloaded,"甲")
 assert(not find(reloaded:query(45,static()),"乙"),"Restart resurrected a hidden edge")
 -- A fresh manual contiguous observation unlocks pending rediscovery, explicit acceptance restores score 10.
 context(reloaded,"甲乙");context(reloaded,"甲")
 local revived=assert(find(reloaded:query(45,static()),"乙"));assert(revived.reactivation)
 assert(reloaded.confirmed["甲乙"].score==0)
 assert(reloaded:select(revived,true,{revived}));assert(reloaded.confirmed["甲乙"].score==10)
 -- Neutral redraw/abandon does not mutate any scores.
 context(reloaded,"甲");local before=reloaded.confirmed["甲乙"].score
 local neutral=Episode.new(reloaded:query(45,static()),9);neutral:expose(0);neutral:abandon()
 assert(not neutral:close() and reloaded.confirmed["甲乙"].score==before)
 -- Long-context negative-only feedback cannot be washed out by a short static edge.
 local identity=Core.new(1000,{clock=clock});context(identity,"星河")
 identity.confirmed["星河计"]={score=2,positive_count=0,negative_count=8,recent=0,last_feedback_at=0,hidden_sequence=0,origin="static"}
 local inherited=assert(find(identity:query(45,{{suffix="计",weight=100}}),"计"))
 assert(inherited.score==2 and inherited.phrase=="星河计")
 identity.confirmed["星河计"].positive_count=1
 identity.confirmed_index["星河"]={} -- Ranking-cache eviction must not erase feedback.
 inherited=assert(find(identity:query(45,{{suffix="计",weight=100}}),"计"))
 assert(inherited.score==2 and inherited.phrase=="星河计")
 -- One-time v1 migration preserves old relative weights without continuing to age afterward.
 local legacy={version=1,capacity=1000,sequence=5,segment=1,half_life=10,minimum_weight=.2,maximum_strength=8,window={},
  confirmed={ ["甲乙"]={count=2,recent=1,strength=8,last_used_at=1000},
              ["甲丙"]={count=1,recent=2,strength=4,last_used_at=1000},
              ["甲丁"]={count=1,recent=3,strength=1,last_used_at=900}}}
 local migrated=Core.restore(legacy,{clock=function() return 1000 end})
 assert(migrated.migration_required and migrated.confirmed["甲乙"].score==20 and migrated.confirmed["甲丙"].score==15 and migrated.confirmed["甲丁"].score==0)
 local again=Core.restore(migrated:snapshot(),{clock=function() return 999999 end})
 assert(not again.migration_required and again.confirmed["甲乙"].score==20)
 return "PASS: 1000 manual slots, per-step feedback, visible-page once-only, cap20, rank below10, zero tombstone/reactivation, no time decay, v1 migration"
end
return M
