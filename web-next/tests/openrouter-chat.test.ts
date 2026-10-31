import assert from "node:assert/strict";
import {afterEach, test} from "node:test";
import {allowsOpenRouterChat, isGuardedChatRuntime} from "../lib/remote-chat";
import {moneyText, pendingOpenRouterCost, readOpenRouterCost, readOpenRouterQuote, readOpenRouterMetadata, readOpenRouterUsage} from "../lib/openrouter-chat";
import {vastChatHistoryKey} from "../lib/vast-chat-history";
import {isCockpitRuntimeDisabled, resolveCockpitActiveRuntimeInfo} from "../lib/cockpit-runtime-selection";
import {resolveEffectiveChatModelSelection, syncTargetServerIfNeeded} from "../components/cockpit/cockpit-chat-send";
import {buildSimpleStreamRequestPayload, handleSimpleTaskSend} from "../components/cockpit/chat-send-helpers";
import {cancelSimpleChatStream, sendSimpleChatStream, quoteOpenRouterChat} from "../hooks/use-api";

const fetchBefore = globalThis.fetch;
afterEach(() => {globalThis.fetch = fetchBefore; cancelSimpleChatStream();});

test("OpenRouter gets an immutable identity and isolated conversation namespace", () => {
  const runtime = "openrouter@catalog-hash:revision";
  assert.equal(isGuardedChatRuntime(runtime), true);
  assert.equal(isGuardedChatRuntime("openrouter-impersonation"), false);
  const args = [runtime, "provider/model", "session", "config"] as const;
  const key = vastChatHistoryKey(...args);
  assert.ok(key);
  for (const alternative of [
    ["openrouter@other", args[1], args[2], args[3]],
    [args[0], "another/model", args[2], args[3]],
    [args[0], args[1], "another-session", args[3]],
    [args[0], args[1], args[2], "another-hash"],
    ["ollama@vast:p:i:g", args[1], args[2], args[3]],
  ]) assert.notEqual(vastChatHistoryKey(alternative[0],alternative[1],alternative[2],alternative[3]),key);
  const payload = buildSimpleStreamRequestPayload("q",args[1],null,args[2],{runtime_id:runtime,config_hash:args[3]});
  assert.equal(payload.expectedRuntimeId,runtime);
  assert.equal(payload.expectedConfigHash,args[3]);
  assert.equal(resolveEffectiveChatModelSelection("","local","openrouter","ollama"),"");
  const active=resolveCockpitActiveRuntimeInfo({active:{runtime_id:runtime,active_model:args[1]}},{runtime_id:runtime,active_server:"openrouter"});
  assert.equal(active?.runtime_id,runtime);
});

test("OpenRouter activation uses the cloud endpoint and never falls back to a local server", async () => {
  const calls:string[]=[];
  const result=await syncTargetServerIfNeeded({selectedLlmServer:"openrouter",selectedLlmModel:"provider/model",
    activeServerInfo:{active_server:"ollama"},
    setActiveLlmRuntime:async(provider,model)=>{calls.push(provider+"/"+model);return {runtime_id:"openrouter@revision"};},
    setActiveLlmServer:async()=>{throw new Error("must not use local activation");},
    refreshActiveServer:()=>{},setMessage:()=>{},t:key=>key});
  assert.deepEqual(calls,["openrouter/provider/model"]);
  assert.equal(result&&result.runtime_id,"openrouter@revision");
  assert.equal(allowsOpenRouterChat("openrouter",false),false);
  assert.equal(allowsOpenRouterChat("openrouter@revision",true),true);
  assert.equal(allowsOpenRouterChat("ollama",false),true);
});

test("unknown or malformed money never becomes a free request or a settled result",()=>{
  for(const unknown of [undefined,null,0,false,"NaN","Infinity","-1","not-a-price"]) assert.equal(moneyText(unknown),null);
  assert.equal(moneyText("0"),"0");
  assert.equal(moneyText("0.00000001"),"0.00000001");
  assert.equal(readOpenRouterCost({currency:"USD",state:"settled",reported_usd:null})?.state,"pending");
  assert.equal(readOpenRouterCost({currency:"USD",state:"settled",reported_usd:"0"})?.state,"settled");
  assert.equal(pendingOpenRouterCost().reported_usd,null);
});

test("a failed paid POST is attempted once",async()=>{
  let count=0;
  globalThis.fetch=async()=>{count++;throw new Error("ambiguous network failure");};
  await assert.rejects(sendSimpleChatStream({content:"q",model:"provider/model",expectedRuntimeId:"openrouter@revision",expectedConfigHash:"hash"}));
  assert.equal(count,1);
});

test("an interrupted remote stream never accepts its partial turn and preserves pending accounting",async()=>{
  let completed=false;
  let detail:Record<string,unknown>={};
  const setters:Parameters<typeof handleSimpleTaskSend>[0]={
    clientId:"id",trimmed:"q",resolvedSession:"s",generationParams:null,selectedLlmModel:"provider/model",
    activeServerInfo:{active_server:"openrouter",runtime_id:"openrouter@revision",config_hash:"hash"},
    onCompleted:()=>{completed=true;},t:key=>key,
    sendSimpleChatStream:async()=>new Response('event: content\ndata: {"text":"partial"}\n\n'),
    linkOptimisticRequest:()=>{},setLocalSessionHistory:()=>{},updateSimpleStream:()=>{},recordUiTiming:()=>{},uiTimingsRef:{current:new Map()},
    setSimpleRequestDetails:update=>{if(typeof update==="function")detail=update({});},ingestMemoryEntry:async()=>{},
    setLastResponseDurationMs:()=>{},setResponseDurations:()=>{},dropOptimisticRequest:()=>{},clearSimpleStream:()=>{},setMessage:()=>{},setSending:()=>{},
  };
  await handleSimpleTaskSend(setters);
  assert.equal(completed,false);
  const value=Object.values(detail)[0] as {openrouter_cost:{state:string;reported_usd:null}};
  assert.equal(value.openrouter_cost.state,"pending");
  assert.equal(value.openrouter_cost.reported_usd,null);
});


test("quote and execution bind the same history, parameters and immutable hash",async()=>{
  const calls:Array<{url:string;body:Record<string,unknown>}>=[];
  const quote={estimated_usd:"0.002",currency:"USD",max_output_tokens:128,input_token_upper_bound:1000,context_length:8192,config_hash:"same",quote_hash:"a".repeat(64)};
  globalThis.fetch=async(url,init)=>{
    calls.push({url:String(url),body:JSON.parse(String(init?.body))});
    return String(url).endsWith("/quote") ? new Response(JSON.stringify(quote)) : new Response('event: done\ndata: {}\n\n');
  };
  const request={content:"next",model:"provider/model",maxTokens:128,expectedRuntimeId:"openrouter@revision",expectedConfigHash:"same",history:[{role:"assistant" as const,content:"prior"}]};
  const checked=await quoteOpenRouterChat(request);
  await sendSimpleChatStream({...request,expectedQuoteHash:checked.quote_hash});
  assert.equal(calls.length,2);
  assert.equal(calls[0].url.endsWith("/openrouter/quote"),true);
  assert.equal(calls[0].body.expected_quote_hash,undefined);
  const {expected_quote_hash,...execution}=calls[1].body;
  assert.equal(expected_quote_hash,quote.quote_hash);
  assert.deepEqual(execution,calls[0].body);
  assert.throws(()=>readOpenRouterQuote({...quote,config_hash:"changed"},"same"),/invalid_quote/);
});

test("STOP during quote cancels preflight before a paid request exists",async()=>{
  let calls=0;
  globalThis.fetch=async(_url,init)=>{
    calls++;
    return new Promise((_resolve,reject)=>{init?.signal?.addEventListener("abort",()=>reject(new DOMException("Aborted","AbortError")));});
  };
  const preflight=quoteOpenRouterChat({content:"next",expectedRuntimeId:"openrouter@revision",expectedConfigHash:"same"});
  cancelSimpleChatStream();
  await assert.rejects(preflight,/Aborted/);
  assert.equal(calls,1);
});


test("an unavailable cloud OpenRouter entry cannot be activated from the selector",()=>{
  const runtime={runtime_id:"openrouter",source_type:"remote" as const,configured:true,available:false,models:[{id:"provider/model",name:"provider/model",provider:"openrouter",runtime_id:"openrouter",source_type:"remote" as const,active:false}],status:"offline",reason:"cloud_policy"};
  assert.equal(isCockpitRuntimeDisabled(runtime),true);
  assert.equal(isCockpitRuntimeDisabled({...runtime,available:true,status:"running",reason:undefined}),false);
  assert.equal(isCockpitRuntimeDisabled({...runtime,available:true,models:[]}),true);
});


test("conversation charges come from reported ledger values, never estimates",()=>{
  const cost=readOpenRouterCost({currency:"USD",state:"settled",estimated_usd:"1",reported_usd:"0.002",
    conversation_reported_usd:"0.007",conversation_reserved_usd:"0.003",conversation_state:"pending"});
  assert.equal(cost?.conversation_reported_usd,"0.007");
  assert.equal(cost?.conversation_reserved_usd,"0.003");
  assert.equal(cost?.conversation_state,"pending");
  const unknown=readOpenRouterCost({currency:"USD",state:"pending",estimated_usd:"1",conversation_state:"settled"});
  assert.equal(unknown?.conversation_reported_usd,null);
  assert.equal(unknown?.conversation_state,"unknown");
});


test("upstream telemetry preserves zero counts and drops unapproved fields and estimated usage",()=>{
  assert.deepEqual(readOpenRouterUsage({prompt_tokens:0,completion_tokens:0,total_tokens:0,raw:"discard"},"upstream"),{prompt_tokens:0,completion_tokens:0,total_tokens:0});
  assert.equal(readOpenRouterUsage({total_tokens:100},"estimated"),null);
  assert.equal(readOpenRouterUsage({total_tokens:false,prompt_tokens:-1,completion_tokens:"0"},"upstream"),null);
  const metadata=readOpenRouterMetadata({requested_model:"provider/model",confirmed_model:"provider/model",confirmed_provider:"provider",generation_id:"gen-r",raw_secret:"discard"});
  assert.deepEqual(Object.keys(metadata),["requested_model","confirmed_model","confirmed_provider","generation_id"]);
  assert.equal(readOpenRouterMetadata({confirmed_provider:"Bearer private-token"}).confirmed_provider,null);
});

test("completed request details retain actual usage and identity without a raw provider payload",async()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,"window");
  Object.defineProperty(globalThis,"window",{value:{setTimeout:()=>0},configurable:true});
  let details:Record<string,import("../lib/types").HistoryRequestDetail>={};
  const charge={currency:"USD",state:"settled",estimated_usd:"0.002",reserved_usd:"0.002",reported_usd:"0",
    conversation_reported_usd:"0.007",conversation_reserved_usd:"0",conversation_state:"settled"};
  const done={cost:charge,usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0},usage_source:"upstream",
    requested_model:"provider/model",confirmed_model:"provider/model",confirmed_provider:"reported-provider",generation_id:"gen-r",raw_secret:"must-not-persist"};
  try{
    await handleSimpleTaskSend({
      clientId:"id",trimmed:"q",resolvedSession:"s",generationParams:null,selectedLlmModel:"provider/model",
      activeServerInfo:{active_server:"openrouter",runtime_id:"openrouter@revision",config_hash:"hash"},
      sendSimpleChatStream:async()=>new Response('event: content\ndata: {"text":"answer"}\n\nevent: done\ndata: '+JSON.stringify(done)+'\n\n'),
      linkOptimisticRequest:()=>{},setLocalSessionHistory:()=>{},updateSimpleStream:()=>{},recordUiTiming:()=>{},uiTimingsRef:{current:new Map()},
      setSimpleRequestDetails:update=>{details=typeof update==="function"?update(details):update;},ingestMemoryEntry:async()=>{},
      setLastResponseDurationMs:()=>{},setResponseDurations:()=>{},dropOptimisticRequest:()=>{},clearSimpleStream:()=>{},setMessage:()=>{},setSending:()=>{},
    });
    assert.deepEqual(details["simple-id"].openrouter_usage,{prompt_tokens:0,completion_tokens:0,total_tokens:0});
    assert.equal(details["simple-id"].openrouter_metadata?.generation_id,"gen-r");
    assert.equal(details["simple-id"].openrouter_cost?.conversation_reported_usd,"0.007");
    assert.equal(details["simple-id"].openrouter_cost?.reported_usd,"0");
    assert.equal(JSON.stringify(details).includes("must-not-persist"),false);
  }finally{
    if(previous)Object.defineProperty(globalThis,"window",previous);else Reflect.deleteProperty(globalThis,"window");
  }
});


test("refresh keeps full OpenRouter identity or reattaches selector-only and stale snapshots before quote",async()=>{
  const model="vendor/model";
  const catalog={active:{runtime_id:"openrouter",active_model:model},runtimes:[]};
  const fresh={active_server:"openrouter",active_model:model,runtime_id:"openrouter@"+model,config_hash:"fresh"};
  const cases=[
    {name:"current",fallback:{...fresh},calls:0},
    {name:"stale-local",fallback:{active_server:"ollama",active_model:"local",runtime_id:"ollama@local",config_hash:"old"},calls:1},
    {name:"missing",fallback:null,calls:1},
    {name:"stale-model",fallback:{active_server:"openrouter",active_model:"old/model",runtime_id:"openrouter@old/model",config_hash:"old"},calls:1},
  ];
  for(const scenario of cases){
    const info=resolveCockpitActiveRuntimeInfo(catalog,scenario.fallback);
    let calls=0;
    const selected=await syncTargetServerIfNeeded({selectedLlmServer:"openrouter",selectedLlmModel:model,activeServerInfo:info,
      setActiveLlmRuntime:async(provider,selection)=>{assert.equal(provider,"openrouter");assert.equal(selection,model);calls++;return fresh;},
      setActiveLlmServer:async()=>{throw new Error("must not activate a local server");},
      refreshActiveServer:()=>{},setMessage:()=>{},t:key=>key});
    assert.equal(calls,scenario.calls,scenario.name);
    assert.notEqual(selected,false,scenario.name);
    if(selected){
      const payload=buildSimpleStreamRequestPayload("q",model,null,"session",selected);
      assert.equal(payload.expectedRuntimeId,fresh.runtime_id,scenario.name);
      assert.equal(payload.expectedConfigHash,fresh.config_hash,scenario.name);
    }
  }
});


test("chunked SSE dispatch preserves accounting and ignores unknown event names", async () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { value: { setTimeout: () => 0 }, configurable: true });
  let details: Record<string, import("../lib/types").HistoryRequestDetail> = {};
  let history: import("../components/cockpit/chat-send-helpers").LocalHistoryEntry[] = [];
  let answer = "";
  let sends = 0;
  const cost = { currency: "USD", state: "settled", reported_usd: "0.001" };
  const completion = { cost, requested_model: "vendor/model", confirmed_model: "vendor/model", generation_id: "gen-complete", usage: { total_tokens: 3 }, usage_source: "upstream" };
  const encoded = new TextEncoder().encode([
    "event: constructor\ndata: {}\n\n",
    "event: toString\ndata: {}\n\n",
    "event: start\ndata: {\"requested_model\":\"vendor/model\",\"generation_id\":\"gen-start\"}\n\n",
    "event: cost\ndata: " + JSON.stringify(cost) + "\n\n",
    "event: content\ndata: {\"text\":\"Zażółć\"}\n\n",
    "event: done\ndata: " + JSON.stringify(completion) + "\n\n",
  ].join(""));
  try {
    await handleSimpleTaskSend({
      clientId: "local", trimmed: "question", resolvedSession: "session", generationParams: null, selectedLlmModel: "vendor/model",
      activeServerInfo: { active_server: "openrouter", runtime_id: "openrouter@vendor/model", config_hash: "fixed" },
      expectedQuoteHash: "q".repeat(64), onCompleted: value => { answer = value; },
      sendSimpleChatStream: async payload => {
        sends++;
        assert.equal(payload.expectedQuoteHash, "q".repeat(64));
        return new Response(new ReadableStream({ start(controller) {
          for (let index = 0; index < encoded.length; index += 7) controller.enqueue(encoded.slice(index, index + 7));
          controller.close();
        } }), { headers: { "x-request-id": "server-request" } });
      },
      setLocalSessionHistory: update => { history = typeof update === "function" ? update(history) : update; },
      setSimpleRequestDetails: update => { details = typeof update === "function" ? update(details) : update; },
      linkOptimisticRequest: () => {}, updateSimpleStream: () => {}, recordUiTiming: () => {}, uiTimingsRef: { current: new Map() },
      ingestMemoryEntry: async () => {}, setLastResponseDurationMs: () => {}, setResponseDurations: () => {}, dropOptimisticRequest: () => {}, clearSimpleStream: () => {}, setMessage: () => {}, setSending: () => {},
    });
    assert.equal(sends, 1);
    assert.equal(answer, "Zażółć");
    assert.equal(details["server-request"].status, "COMPLETED");
    assert.equal(details["server-request"].openrouter_cost?.reported_usd, "0.001");
    assert.equal(details["server-request"].openrouter_metadata?.generation_id, "gen-complete");
    assert.equal(details["server-request"].openrouter_usage?.total_tokens, 3);
    assert.equal(history.find(entry => entry.role === "assistant")?.pending, false);
  } finally {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  }
});

test("SSE errors retain partial output and mark the reconciled remote request failed", async () => {
  let details: Record<string, import("../lib/types").HistoryRequestDetail> = {};
  let history: import("../components/cockpit/chat-send-helpers").LocalHistoryEntry[] = [];
  let completed = false;
  let sending = true;
  let message: string | null = null;
  await handleSimpleTaskSend({
    clientId: "local", trimmed: "question", resolvedSession: "session", generationParams: null, selectedLlmModel: "vendor/model",
    activeServerInfo: { active_server: "openrouter", runtime_id: "openrouter@vendor/model", config_hash: "fixed" },
    onCompleted: () => { completed = true; }, t: key => key,
    sendSimpleChatStream: async () => new Response('event: content\ndata: {"text":"partial"}\n\nevent: error\ndata: {"error":"private upstream reason"}\n\n', { headers: { "x-request-id": "failed-request" } }),
    setLocalSessionHistory: update => { history = typeof update === "function" ? update(history) : update; },
    setSimpleRequestDetails: update => { details = typeof update === "function" ? update(details) : update; },
    linkOptimisticRequest: () => {}, updateSimpleStream: () => {}, recordUiTiming: () => {}, uiTimingsRef: { current: new Map() },
    ingestMemoryEntry: async () => {}, setLastResponseDurationMs: () => {}, setResponseDurations: () => {}, dropOptimisticRequest: () => {}, clearSimpleStream: () => {}, setMessage: value => { message = value; }, setSending: value => { sending = value; },
  });
  assert.equal(completed, false);
  assert.equal(sending, false);
  assert.equal(message, "cockpit.openrouter.failure");
  assert.equal(details["failed-request"].status, "FAILED");
  assert.equal(details["failed-request"].openrouter_cost?.state, "pending");
  const assistant = history.find(entry => entry.role === "assistant");
  assert.equal(assistant?.request_id, "failed-request");
  assert.equal(assistant?.pending, false);
  assert.equal(assistant?.status, "FAILED");
  assert.equal(assistant?.content, "partial");
  assert.equal(JSON.stringify({ history, details }).includes("private upstream reason"), false);
});
