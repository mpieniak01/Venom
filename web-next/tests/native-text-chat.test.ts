import assert from "node:assert/strict";
import {test} from "node:test";
import {buildSimpleStreamRequestPayload, handleSimpleTaskSend, type LocalHistoryEntry} from "../components/cockpit/chat-send-helpers";
import {nativeTextQuality, nativeTextServer, readNativeTextIdentity, type NativeTextIdentity} from "../lib/native-text-chat";
import {sendSimpleChatStream} from "../hooks/use-api";
import {toHistoryMessages} from "../components/cockpit/hooks/cockpit-history-utils";
import type {HistoryRequestDetail} from "../lib/types";

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
for(const variant of ["valid","wrong-start","changed-done","missing-done","missing-start"]){
 test("native SSE "+variant+" verifies actual identity before publishing completed history",async()=>{
  let history:LocalHistoryEntry[]=[];let details:Record<string,HistoryRequestDetail>={};let completed=false;
  const event=(type:string,data:unknown)=>"event: "+type+"\ndata: "+JSON.stringify(data)+"\n\n";
  const start=variant==="missing-start" ? "" : event("start",{model_identity:variant==="wrong-start"?{...identity,config_sha256:"a".repeat(64)}:identity});
  const done=variant==="missing-done" ? "" : event("done",{model_identity:variant==="changed-done"?{...identity,input_messages_sha256:"a".repeat(64)}:identity});
  await handleSimpleTaskSend({
   clientId:"id",trimmed:"q",resolvedSession:"session",generationParams:null,selectedLlmModel:identity.adapter_id,
   activeServerInfo:nativeTextServer(identity),onCompleted:()=>{completed=true;},t:key=>key,
   sendSimpleChatStream:async()=>new Response(start+event("content",{text:"answer"})+done,{headers:{"x-request-id":"request"}}),
   ingestMemoryEntry:undefined,
   linkOptimisticRequest:()=>{},setLocalSessionHistory:update=>{history=typeof update==="function"?update(history):update;},
   updateSimpleStream:()=>{},recordUiTiming:()=>{},uiTimingsRef:{current:new Map()},
   setSimpleRequestDetails:update=>{details=typeof update==="function"?update(details):update;},
   setLastResponseDurationMs:()=>{},setResponseDurations:()=>{},dropOptimisticRequest:()=>{},clearSimpleStream:()=>{},setMessage:()=>{},setSending:()=>{},
  });
  assert.equal(completed,variant==="valid");
  const answer=history.find(item=>item.role==="assistant");
  if(variant==="valid"){
   assert.equal(answer?.model_identity?.weights_sha256,identity.weights_sha256);
   assert.equal(details.request.model_identity?.input_messages_sha256,identity.input_messages_sha256);
   assert.equal(toHistoryMessages(history).find(item=>item.role==="assistant")?.modelIdentity?.runtime_id,identity.runtime_id);
  }else{assert.notEqual(answer?.status,"COMPLETED");}
 });
}
