import "./component-test-setup";
import assert from "node:assert/strict";
import {afterEach,test} from "node:test";
import {cleanup,render,screen} from "@testing-library/react";
import {OpenRouterModelStatus} from "../components/cockpit/openrouter-model-status";
import {OpenRouterProvenance} from "../components/cockpit/openrouter-provenance";
import {OpenRouterCost} from "../components/cockpit/openrouter-cost";
import {pendingOpenRouterCost} from "../lib/openrouter-chat";
import {publishOpenRouterQuote} from "../lib/openrouter-quote-state";
import {LanguageProvider} from "../lib/i18n";

afterEach(()=>cleanup());

test("the panel distinguishes configured credentials from unverified authentication and retains zero prices",()=>{
  render(<LanguageProvider><OpenRouterModelStatus model="provider/model" session="s" selection={{failed:false,result:{
    status:{enabled:true,configured:true,library_available:true,available:true,authenticated:null,reason:null,pricing_as_of:"2026-10-29"},
    catalog:{pricing_as_of:"2026-10-29",models:[{id:"provider/model",name:"model",input_price_per_million:"0",output_price_per_million:"0.25",request_price:null,context_length:8192,max_output_tokens:128,pricing_as_of:"2026-10-29"}]},
  }}}/></LanguageProvider>);
  const text=screen.getByTestId("openrouter-model-status").textContent??"";
  assert.match(text,/0.*0.25/);
  assert.match(text,/niesprawdzone|not verified|nicht geprüft/);
  assert.match(text,/Nieznane|Unknown|Unbekannt/);
});

test("interrupted accounting renders pending and unknown rather than a zero cost",()=>{
  render(<OpenRouterCost cost={pendingOpenRouterCost()} t={(key,values)=>key+" "+(values?.amount??"")}/>);
  const text=screen.getByTestId("openrouter-cost").textContent??"";
  assert.match(text,/pending/);
  assert.match(text,/unknown/);
  assert.doesNotMatch(text,/0 USD/);
});


test("last-send estimates are scoped to the selected model and conversation",()=>{
  const selection:Parameters<typeof OpenRouterModelStatus>[0]["selection"]={failed:false,result:{
    status:{enabled:true,configured:true,library_available:true,available:true,authenticated:null,reason:null,pricing_as_of:null},
    catalog:{pricing_as_of:null,models:[]},
  }};
  publishOpenRouterQuote("chosen/model","session",{estimated_usd:"0.002",currency:"USD",input_token_upper_bound:1000,max_output_tokens:128,context_length:8192,config_hash:"same",quote_hash:"a".repeat(64)});
  const view=render(<LanguageProvider><OpenRouterModelStatus selection={selection} model="chosen/model" session="session"/></LanguageProvider>);
  assert.match(screen.getByTestId("openrouter-last-quote").textContent??"",/0.002.*1000.*128/);
  view.rerender(<LanguageProvider><OpenRouterModelStatus selection={selection} model="chosen/model" session="another"/></LanguageProvider>);
  assert.equal(screen.queryByTestId("openrouter-last-quote"),null);
  view.rerender(<LanguageProvider><OpenRouterModelStatus selection={selection} model="other/model" session="session"/></LanguageProvider>);
  assert.equal(screen.queryByTestId("openrouter-last-quote"),null);
});


test("the conversation panel renders confirmed charges separately from held reservations",()=>{
  render(<OpenRouterCost cost={{...pendingOpenRouterCost(),estimated_usd:"1",conversation_reported_usd:"0.007",conversation_reserved_usd:"0.003",conversation_state:"pending"}}
    t={(key,values)=>key+" "+(values?.amount??"")}/>);
  const text=screen.getByTestId("openrouter-cost").textContent??"";
  assert.match(text,/conversationReported 0.007/);
  assert.match(text,/conversationReserved 0.003/);
  assert.match(text,/pending/);
});


test("reported zero token usage remains visible in existing model details",()=>{
  render(<OpenRouterProvenance detail={{request_id:"r",prompt:"q",status:"COMPLETED",created_at:"2026-10-29T12:00:00Z",
    openrouter_metadata:{requested_model:"chosen/model",confirmed_model:"chosen/model",confirmed_provider:"provider",generation_id:"gen-r"},
    openrouter_usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0}}}
    t={(key,values)=>key+" "+Object.values(values??{}).join(" ")}/>);
  assert.match(screen.getByTestId("openrouter-upstream-usage").textContent??"",/0 0 0/);
  assert.ok(screen.getByText("gen-r"));
});
