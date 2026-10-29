import assert from "node:assert/strict";
import {afterEach, test} from "node:test";
import {allowsOpenRouterChat, isGuardedChatRuntime} from "../lib/remote-chat";
import {moneyText, pendingOpenRouterCost, readOpenRouterCost} from "../lib/openrouter-chat";
import {vastChatHistoryKey} from "../lib/vast-chat-history";
import {resolveCockpitActiveRuntimeInfo} from "../lib/cockpit-runtime-selection";
import {resolveEffectiveChatModelSelection, syncTargetServerIfNeeded} from "../components/cockpit/cockpit-chat-send";
import {buildSimpleStreamRequestPayload, handleSimpleTaskSend} from "../components/cockpit/chat-send-helpers";
import {cancelSimpleChatStream, sendSimpleChatStream} from "../hooks/use-api";

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
