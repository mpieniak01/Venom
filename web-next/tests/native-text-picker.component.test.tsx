import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {LanguageProvider} from "../lib/i18n";
import {NativeTextPicker} from "../components/chat/native-text-picker";
import {useNativeTextChat} from "../components/chat/use-native-text-chat";
const identity={runtime:"omni-native-peft-text",adapter_id:"omni-p13-145",weights_sha256:"a".repeat(64),config_sha256:"b".repeat(64),snapshot_sha256:"c".repeat(64),runtime_id:"omni-native-peft-text:omni-p13-145:"+"a".repeat(64)};
function Harness(){const native=useNativeTextChat();return <><NativeTextPicker native={native} busy={false}/><output data-testid="state">{native.state.selection?.runtime_id??"ordinary"}</output></>;}
test("picker probes, rolls back, retains selection after failed probe, and refreshes after API restart",async()=>{
 const old=globalThis.fetch;let selection:typeof identity|null=null;let fail=false;const requests:unknown[]=[];
 globalThis.fetch=async(input,init)=>{
  const url=String(input);
  if(url.endsWith("/catalog"))return Response.json({adapters:[{...identity,label:"P13"}]});
  if(url.endsWith("/selection")){requests.push(JSON.parse(String(init?.body)));if(fail)return Response.json({detail:{reason_code:"omni_native_text_selection_changed"}},{status:409});selection=identity;}
  if(url.endsWith("/rollback")){requests.push(JSON.parse(String(init?.body)));selection=null;}
  return Response.json({selection,previous:null,persistent:false});
 };
 try{
  render(<LanguageProvider><Harness/></LanguageProvider>);
  await waitFor(()=>assert.ok(screen.getByRole("option",{name:/P13/})));
  const choose=screen.getByRole("combobox");fireEvent.change(choose,{target:{value:identity.adapter_id}});
  fireEvent.click(screen.getByRole("button",{name:/Wczytaj|Load|Laden/}));
  await waitFor(()=>assert.equal(screen.getByTestId("state").textContent,identity.runtime_id));
  assert.deepEqual(requests[0],{adapter_id:identity.adapter_id,expected_runtime_id:null});
  fail=true;fireEvent.click(screen.getByRole("button",{name:/Wczytaj|Load|Laden/}));
  await waitFor(()=>assert.ok(screen.getByRole("alert")));
  assert.equal(screen.getByTestId("state").textContent,identity.runtime_id);
  fireEvent.click(screen.getByRole("button",{name:/Przywróć|Restore|wiederherstellen/}));
  await waitFor(()=>assert.equal(screen.getByTestId("state").textContent,"ordinary"));
  assert.deepEqual(requests[2],{expected_runtime_id:identity.runtime_id});
  fail=false;fireEvent.click(screen.getByRole("button",{name:/Wczytaj|Load|Laden/}));
  await waitFor(()=>assert.equal(screen.getByTestId("state").textContent,identity.runtime_id));
  selection=null;
  await act(async()=>{window.dispatchEvent(new Event("focus"));});
  await waitFor(()=>assert.equal(screen.getByTestId("state").textContent,"ordinary"));
 }finally{cleanup();globalThis.fetch=old;}
});
