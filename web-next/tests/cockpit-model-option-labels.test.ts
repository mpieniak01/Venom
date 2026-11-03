import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { StudioModelPicker } from "../components/chat/studio-model-picker";
import { LanguageProvider } from "../lib/i18n";
import type { RuntimeCatalogModelInfo } from "../lib/academy-api";
import { useLlmServerSelectionData } from "../components/cockpit/cockpit-hooks";

import { formatRuntimeModelOptionLabel } from "../components/cockpit/cockpit-section-props";

describe("cockpit runtime model labels", () => {
  const t = (key: string) => {
    const map: Record<string, string> = {
      "cockpit.models.feedbackLoopPrimaryBadge": "feedback-loop: recommended",
      "cockpit.models.feedbackLoopFallbackBadge": "feedback-loop: fallback",
    };
    return map[key] || key;
  };

  it("adds primary badge label", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "qwen2.5-coder:7b", feedback_loop_tier: "primary" },
      t,
    );
    assert.equal(label, "qwen2.5-coder:7b · feedback-loop: recommended");
  });

  it("adds fallback badge label", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "qwen2.5-coder:3b", feedback_loop_tier: "fallback" },
      t,
    );
    assert.equal(label, "qwen2.5-coder:3b · feedback-loop: fallback");
  });

  it("keeps plain model name for non-recommended models", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "phi3:mini", feedback_loop_tier: "not_recommended" },
      t,
    );
    assert.equal(label, "phi3:mini");
  });

  it("adds runtime tag when runtime id is present", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "phi3:mini", feedback_loop_tier: "not_recommended", runtime_id: "ollama" },
      t,
    );
    assert.equal(label, "phi3:mini [ollama]");
  });

  it("shows canonical alias for gemma3 ollama tag", () => {
    const label = formatRuntimeModelOptionLabel(
      {
        name: "gemma3:latest",
        canonical_model_id: "gemma-3-4b-it",
        feedback_loop_tier: "not_recommended",
        runtime_id: "ollama",
      },
      t,
    );
    assert.equal(label, "gemma3:latest <-> gemma-3-4b-it [ollama]");
  });
});


describe("Gemma4 operator labels", () => {
  it("uses explicit variant labels without changing request IDs", () => {
    const t = (key: string) => key;
    assert.equal(formatRuntimeModelOptionLabel({name:"gemma4:e4b",runtime_id:"ollama",display_name:"Gemma4 E4B IT Q4_K_M"},t),
                 "Gemma4 E4B IT Q4_K_M [ollama]");
    assert.equal(formatRuntimeModelOptionLabel({name:"gemma4:12b-it-q4_K_M",runtime_id:"ollama"},t),
                 "Gemma4 12B IT Q4_K_M [ollama]");
  });
});


it("server-selection hook preserves backend selection and activation flags", () => {
  function Probe() {
    const {llmModelOptions} = useLlmServerSelectionData({
      llmServers:[],selectedLlmServer:"ollama",activeServerInfo:null,
      models:{models:[
        {name:"blocked-selection",provider:"ollama",selection_supported:false},
        {name:"blocked-activation",provider:"ollama",activation_supported:false},
        {name:"enabled",provider:"ollama"},
      ]},
    });
    return createElement("select",{},llmModelOptions.map(option =>
      createElement("option",{key:option.value,value:option.value},option.label)));
  }
  assert.equal(renderToStaticMarkup(createElement(Probe)),
               '<select><option value="enabled">enabled</option></select>');
});


function studioPickerMarkup(model: RuntimeCatalogModelInfo, selected = model.name, selectedRuntime = "ollama", catalogModels = [model]) {
  const props = {
    catalog:{
      active:{active_server:"ollama",active_model:model.name},
      runtimes:[{runtime_id:"ollama",source_type:"local-runtime",configured:true,available:true,
                 status:"online",active:true,models:catalogModels}],
    },
    interaction:{
      state:{selectedLlmServer:selectedRuntime,selectedLlmModel:selected,chatMode:"direct"},
      setters:{setSelectedLlmServer:()=>{},setSelectedLlmModel:()=>{},setChatMode:()=>{}},
    },
    session:"fixture-session",activeModel:model.name,onApply:async()=>true,busy:false,
  } as unknown as Parameters<typeof StudioModelPicker>[0];
  return renderToStaticMarkup(createElement(LanguageProvider,null,createElement(StudioModelPicker,props)));
}

for (const [name, flag] of [
  ["saluki:latest","selection_supported"],
  ["qwen3.5:latest","activation_supported"],
] as const) {
  it("Studio preserves catalog rejection for selected " + name, () => {
    const model: RuntimeCatalogModelInfo = {
      id:name,name,provider:"ollama",runtime_id:"ollama",source_type:"local-runtime",active:true,
      [flag]:false,
    };
    const html = studioPickerMarkup(model);
    const option = html.match(/<option[^>]*>/g)?.find(tag => tag.includes('value="' + name + '"'));
    assert.ok(option);
    assert.match(option,/disabled=""/);
    assert.match(html,/<button[^>]*class="studio-button"[^>]*disabled=""/);
  });
}

it("Studio keeps the confirmed observed preset selectable", () => {
  const name = "saluki:latest";
  const html = studioPickerMarkup({
    id:name,name,provider:"ollama",runtime_id:"ollama",source_type:"local-runtime",active:true,
    display_name:"Saluki preset 26.9B IQ2_XS ·3497825c",selection_supported:true,activation_supported:true,
  });
  assert.match(html,/<option value="saluki:latest" selected="">Saluki preset/);
  assert.doesNotMatch(html,/<button[^>]*class="studio-button"[^>]*disabled/);
});

it("Studio cannot apply a missing catalog entry", () => {
  const name = "saluki:latest";
  const html = studioPickerMarkup({
    id:"other",name:"other",provider:"ollama",runtime_id:"ollama",source_type:"local-runtime",active:false,
  },name);
  assert.match(html,/<option value="saluki:latest" disabled="" selected="">/);
  assert.match(html,/<button[^>]*class="studio-button"[^>]*disabled=""/);
});


it("Studio active label uses the active Ollama runtime after a pending OpenRouter selection", () => {
  const name = "gemma4:latest";
  const html = studioPickerMarkup({
    id:name,name,provider:"ollama",runtime_id:"ollama",source_type:"local-runtime",active:true,
    selection_supported:false,display_name:name,
  },name,"openrouter");
  assert.match(html,/<span>[^<]*gemma4:latest \(nierozpoznany wariant\)<\/span>/);
});


it("Studio active label prefers an exact model name over an earlier alias", () => {
  const exact: RuntimeCatalogModelInfo = {
    id:"e4b", name:"gemma4:e4b", display_name:"Exact E4B",
    provider:"ollama",runtime_id:"ollama",source_type:"local-runtime",active:true,
  };
  const other: RuntimeCatalogModelInfo = {
    ...exact,id:"12b",name:"gemma4:12b-it-q4_K_M",display_name:"Other 12B",
    aliases:[exact.name],active:false,
  };
  const html = studioPickerMarkup(exact, exact.name, "ollama", [other, exact]);
  assert.match(html, /<span>[^<]*Exact E4B<\/span>/);
  assert.doesNotMatch(html, /<span>[^<]*Other 12B<\/span>/);
});

it("Studio active label never guesses between ambiguous aliases", () => {
  const active: RuntimeCatalogModelInfo = {
    id:"legacy",name:"legacy-model",provider:"ollama",runtime_id:"ollama",
    source_type:"local-runtime",active:true,
  };
  const first: RuntimeCatalogModelInfo = {
    ...active,id:"e4b",name:"gemma4:e4b",display_name:"First E4B",aliases:[active.name],
  };
  const second: RuntimeCatalogModelInfo = {
    ...first,id:"12b",name:"gemma4:12b-it-q4_K_M",display_name:"Second 12B",
  };
  const html = studioPickerMarkup(active, first.name, "ollama", [first,second]);
  assert.match(html, /<span>[^<]*legacy-model<\/span>/);
  assert.doesNotMatch(html, /<span>[^<]*(?:First E4B|Second 12B)<\/span>/);
});
