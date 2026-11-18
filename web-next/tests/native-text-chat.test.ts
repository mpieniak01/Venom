import assert from "node:assert/strict";
import {test} from "node:test";
import {buildSimpleStreamRequestPayload, handleSimpleTaskSend, type LocalHistoryEntry} from "../components/cockpit/chat-send-helpers";
import {nativeTextQuality, nativeTextServer, readNativeTextIdentity, type NativeTextIdentity} from "../lib/native-text-chat";
import {sendSimpleChatStream} from "../hooks/use-api";
import {toHistoryMessages} from "../components/cockpit/hooks/cockpit-history-utils";
import type {HistoryRequestDetail} from "../lib/types";
import {prepareChatHistory} from "../components/cockpit/cockpit-chat-send";

const identity: NativeTextIdentity = {runtime:"omni-native-peft-text", adapter_id:"omni-p13-145", weights_sha256:"9f6863cda26a452e89085ea28628a57cd7f10742d9a0337ade100fd0eb58c493", config_sha256:"b".repeat(64), snapshot_sha256:"c".repeat(64),
 runtime_id:"omni-native-peft-text:omni-p13-145:9f6863cda26a452e89085ea28628a57cd7f10742d9a0337ade100fd0eb58c493",input_messages_sha256:"d".repeat(64)};
test("reference badge binds exact P13 weights and never invents candidate qualification",()=>{
 assert.equal(nativeTextQuality({...identity,label:"P13"}),"chat2.nativeText.reference");
 assert.equal(nativeTextQuality({...identity,label:"P13",weights_sha256:"a".repeat(64)}),"chat2.nativeText.unqualified");
 assert.equal(nativeTextQuality({...identity,label:"P25",adapter_id:"P25"}),"chat2.nativeText.unqualified");
 assert.equal(readNativeTextIdentity(identity).runtime_id,identity.runtime_id);
 assert.throws(()=>readNativeTextIdentity({...identity,runtime_id:"ordinary"}));
});
test("native transport binds immutable selection, configuration and actual own history; failed POST is not retried",async()=>{
 const history=[{role:"assistant" as const,content:"My wrong previous answer"}];
 const payload=buildSimpleStreamRequestPayload("Correct person",identity.adapter_id,null,"session",nativeTextServer(identity),history);
 assert.equal(payload.expectedRuntimeId,identity.runtime_id);
 assert.equal(payload.expectedConfigHash,identity.config_sha256);
 assert.equal(payload.history,history);
 const old=globalThis.fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;throw new Error("connection lost");};
 try {await assert.rejects(sendSimpleChatStream(payload));assert.equal(calls,1);}
 finally{globalThis.fetch=old;}
});
for(const variant of ["valid","wrong-start","changed-done","missing-done","missing-start","malformed-start"]){
 test("native SSE "+variant+" verifies actual identity before publishing completed history",async()=>{
  let history:LocalHistoryEntry[]=[];let details:Record<string,HistoryRequestDetail>={};let completed=false;
  let message: string | null = null;
  const streamStatuses: string[] = [];
  const event=(type:string,data:unknown)=>"event: "+type+"\ndata: "+JSON.stringify(data)+"\n\n";
  let start = event("start",{model_identity:variant==="wrong-start"?{...identity,config_sha256:"a".repeat(64)}:identity});
  if (variant === "missing-start") start = "";
  if (variant === "malformed-start") start = "event: start\ndata: {invalid\n\n";
  const done=variant==="missing-done" ? "" : event("done",{model_identity:variant==="changed-done"?{...identity,input_messages_sha256:"a".repeat(64)}:identity});
  await handleSimpleTaskSend({
   clientId:"id",trimmed:"q",resolvedSession:"session",generationParams:null,selectedLlmModel:identity.adapter_id,
   activeServerInfo:nativeTextServer(identity),onCompleted:()=>{completed=true;},t:key=>key,
   sendSimpleChatStream:async()=>new Response(start+event("content",{text:"answer"})+done,{headers:{"x-request-id":"request"}}),
   ingestMemoryEntry:undefined,
   linkOptimisticRequest:()=>{},setLocalSessionHistory:update=>{history=typeof update==="function"?update(history):update;},
   updateSimpleStream:(_id, update)=>{ if (update.status) streamStatuses.push(update.status); },recordUiTiming:()=>{},uiTimingsRef:{current:new Map()},
   setSimpleRequestDetails:update=>{details=typeof update==="function"?update(details):update;},
   setLastResponseDurationMs:()=>{},setResponseDurations:()=>{},dropOptimisticRequest:()=>{},clearSimpleStream:()=>{},setMessage:value=>{message=value;},setSending:()=>{},
  });
  assert.equal(completed,variant==="valid");
  const answer=history.find(item=>item.role==="assistant");
  if(variant==="valid"){
   assert.equal(answer?.model_identity?.weights_sha256,identity.weights_sha256);
   assert.equal(details.request.model_identity?.input_messages_sha256,identity.input_messages_sha256);
   assert.equal(toHistoryMessages(history).find(item=>item.role==="assistant")?.modelIdentity?.runtime_id,identity.runtime_id);
  }else{
   assert.equal(answer?.status,"FAILED");
   assert.equal(streamStatuses.at(-1),"FAILED");
   const expected = ["missing-done","malformed-start"].includes(variant) ? "failed" : "changed";
   assert.equal(message, "chat2.nativeText." + expected);
  }
 });
}

test("native sends all 22 short history messages while ordinary keeps its 20-message budget", async () => {
 const history = Array.from({length:22}, (_, index) => ({
  role: index % 2 === 0 ? "user" as const : "assistant" as const,
  content: "turn " + index,
 }));
 const nativeHistory = prepareChatHistory(identity.runtime_id, history, 1);
 assert.equal(nativeHistory,history);
 const ordinary = prepareChatHistory("ollama",history,1);
 assert.equal(ordinary?.length,20);
 assert.deepEqual(ordinary,history.slice(2));
 const payload=buildSimpleStreamRequestPayload("next",identity.adapter_id,null,"session",nativeTextServer(identity),nativeHistory);
 const old=globalThis.fetch;let body:Record<string,unknown>={};
 globalThis.fetch=async(_input,init)=>{
  body=JSON.parse(String(init?.body));
  return new Response("",{headers:{"x-request-id":"native-full-history"}});
 };
 try{
  const response=await sendSimpleChatStream(payload);
  assert.equal(body.expected_runtime_id,identity.runtime_id);
  assert.deepEqual(body.history,history);
  await response.body?.cancel();
 }finally{globalThis.fetch=old;}
});
