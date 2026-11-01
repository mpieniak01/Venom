import "./component-test-setup";
import React from "react";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import { LanguageProvider, useLanguage } from "../lib/i18n";
import { InstalledAndOperations } from "../components/models/models-viewer-sections";
import { InstalledCard } from "../components/models/models-viewer-components";

afterEach(() => cleanup());
const props = {onActivate:()=>{},allowRemoveProviders:new Set(["ollama"])};

describe("installed model evidence", () => {
  it("does not render an active label from stale legacy configuration", () => {
    render(<InstalledCard {...props} model={{name:"old",provider:"ollama",active:true,loaded:false,selected:true}} />);
    const text=document.body.textContent ?? "";
    assert.match(text,/Niezaładowany|Not loaded|Nicht geladen/);
    assert.doesNotMatch(text,/Aktywny|Active|Aktiv/);
    assert.ok(screen.getByRole("button"));
  });
  it("does not offer vLLM activation for a dedicated Transformers checkpoint", () => {
    render(<InstalledCard {...props} model={{name:"Qwen/Qwen3.5-9B",provider:"transformers",activation_supported:false,loaded:null}} />);
    assert.equal(screen.queryByRole("button"),null);
    assert.match(document.body.textContent ?? "",/niepotwierdzony|unverified|unbestätigt/);
  });
  it("allows selecting a model already loaded by another engine selection", () => {
    render(<InstalledCard {...props} model={{name:"local",provider:"ollama",loaded:true,selected:false,activation_supported:true}} />);
    assert.equal((screen.getByRole("button") as HTMLButtonElement).disabled,false);
    assert.match(document.body.textContent ?? "",/Załadowany|Loaded|Geladen/);
  });
});


it("renders the installed-entry count through the actual language provider", () => {
  const models=[{name:"first:latest",provider:"ollama",loaded:false},{name:"second:latest",provider:"ollama",loaded:false}];
  function Inventory() {
    const {t}=useLanguage();
    const input={installedCollapsed:false,setInstalledCollapsed:()=>{},installed:{data:{models,count:2},loading:false,error:null,refresh:async()=>{}},installedModels:models,installedBuckets:{ollama:models},handleActivate:async()=>{},handleRemove:async()=>{},pendingActions:{},operationsCollapsed:true,setOperationsCollapsed:()=>{},operations:{data:null,loading:false,error:null,refresh:async()=>{}},t} as unknown as Parameters<typeof InstalledAndOperations>[0];
    return <InstalledAndOperations {...input}/>;
  }
  render(<LanguageProvider initialLanguage="pl"><Inventory/></LanguageProvider>);
  assert.ok(screen.getByText("Pozycje: 2"));
});
