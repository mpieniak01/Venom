"""One pinned Transformers checkpoint at a time; optional imports are lazy."""

import gc
import importlib.metadata
import json
import math
import time
from pathlib import Path
from typing import Any

# Full revisions are part of the execution profile, not mutable Hub defaults.
_QWEN_KERNELS = {
    "causal_conv1d_fn": (
        "kernels-community/mamba-ssm",
        "da82c7927c6caac3d8024f98a350131ffec6be85",
    ),
    "causal_conv1d_update": (
        "kernels-community/mamba-ssm",
        "da82c7927c6caac3d8024f98a350131ffec6be85",
    ),
    "chunk_gated_delta_rule": (
        "kernels-community/fla",
        "4d57fd54fa5d5c15f7438de2c7e40f603b824dd8",
    ),
    "fused_recurrent_gated_delta_rule": (
        "kernels-community/fla",
        "4d57fd54fa5d5c15f7438de2c7e40f603b824dd8",
    ),
}


def _backend_options(profile: dict) -> dict:
    settings = profile["profile"]
    options = {}
    if "attention_implementation" in settings:
        options["attn_implementation"] = settings["attention_implementation"]
    kernel_profile = settings.get("kernel_profile")
    if kernel_profile is not None:
        if kernel_profile != "qwen35-deltanet-v1" or profile["id"] != "qwen3.5-9b":
            raise ValueError("unsupported_kernel_profile")
        from transformers import KernelConfig

        options.update(
            use_kernels=True,
            kernel_config=KernelConfig(
                kernel_mapping={
                    name: {
                        "cuda": (
                            repo
                            + ":"
                            + (
                                "recurrent_gated_delta_rule"
                                if name == "fused_recurrent_gated_delta_rule"
                                else name
                            ),
                            {"revision": revision},
                        )
                    }
                    for name, (repo, revision) in _QWEN_KERNELS.items()
                },
                inherit_mapping=False,
            ),
        )
    return options


def _kernel_bindings(model) -> dict[str, str]:
    bindings = {}
    for _, module in model.named_modules():
        for function in getattr(module, "_kernel_funcs", {}).values():
            name = function.kernel_layer_name
            forward = function.forward
            bindings[name] = forward.__module__ + "." + forward.__qualname__
    return bindings


class InferenceNumericalError(RuntimeError):
    """Invalid backend arithmetic must never become a model-quality failure."""


class _FiniteScores:
    def __init__(self, torch):
        self.torch = torch

    def __call__(self, _input_ids, scores):
        invalid = (
            self.torch.isnan(scores).any()
            | self.torch.isposinf(scores).any()
            | self.torch.isneginf(scores).all(dim=-1).any()
        )
        if invalid.item():
            raise InferenceNumericalError("backend_nonfinite_logits")
        return scores


class _PresencePenalty:
    """Penalize each generated token once, excluding the supplied prompt."""

    def __init__(self, torch, prompt_tokens: int, penalty: float):
        if not math.isfinite(penalty):
            raise ValueError("presence_penalty_must_be_finite")
        self.torch, self.prompt_tokens, self.penalty = torch, prompt_tokens, penalty

    def __call__(self, input_ids, scores):
        penalties = self.torch.zeros_like(scores)
        penalties.scatter_(1, input_ids[:, self.prompt_tokens :], self.penalty)
        return scores - penalties


def _tool_response_body(body):
    if not isinstance(body, str):
        return body
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _gemma4_history(messages: list[dict]) -> list[dict]:
    """Use the pinned template's native named tool_responses without inventing IDs."""
    native = [dict(message) for message in messages]
    for index, message in enumerate(native):
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        responses = []
        for following in native[index + 1 :]:
            if following.get("role") != "tool":
                break
            responses.append(
                {
                    "name": following["name"],
                    "response": _tool_response_body(following["content"]),
                }
            )
        if responses:
            message["tool_responses"] = responses
    return native


class LocalModel:
    """Generation only: this class never executes a proposed tool call."""

    def __init__(self, profile: dict[str, Any], cache: Path):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self.profile = profile
        self.torch = torch
        self.input_tokens = self.output_tokens = 0
        self.context = profile["profile"]["context_tokens"]
        self.temperature = profile["profile"]["temperature"]
        dtype_name = profile["profile"].get("compute_dtype", "bfloat16")
        dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16}[dtype_name]
        quantized = profile["parameters"] > 2_000_000_000
        options = {
            "revision": profile["revision"],
            "cache_dir": str(cache),
            "trust_remote_code": False,
        }
        started = time.monotonic()
        self.tokenizer = AutoTokenizer.from_pretrained(profile["hf_id"], **options)
        self.model = AutoModelForCausalLM.from_pretrained(
            profile["hf_id"],
            **options,
            **_backend_options(profile),
            device_map={"": 0},
            dtype=dtype,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=dtype,
            )
            if quantized
            else None,
        ).eval()
        self.kernel_bindings = (
            _kernel_bindings(self.model)
            if profile["profile"].get("kernel_profile")
            else {}
        )
        self.load_seconds = time.monotonic() - started
        torch.cuda.reset_peak_memory_stats()
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory
        hardware = (
            "rtx3060-12gb"
            if "RTX 3060" in gpu_name and 11 * 1024**3 <= gpu_memory <= 13 * 1024**3
            else gpu_name.lower().replace(" ", "-") + "-" + str(gpu_memory)
        )
        self.configuration = {
            **profile["profile"],
            "hardware": hardware,
            "gpu_name": gpu_name,
            "gpu_total_memory_bytes": gpu_memory,
            "backend": "transformers",
            "backend_version": importlib.metadata.version("transformers"),
            "model_class": type(self.model).__name__,
            "tokenizer_class": type(self.tokenizer).__name__,
            "modality": "text",
            "torch_version": torch.__version__,
            "quantization": "bnb-nf4" if quantized else dtype_name,
            "bitsandbytes_version": importlib.metadata.version("bitsandbytes")
            if quantized
            else None,
            "context_tokens": self.context,
            "attention_implementation_actual": self.model.config._attn_implementation,
            "kernel_bindings": self.kernel_bindings,
            "kernel_revisions": _QWEN_KERNELS if self.kernel_bindings else {},
            "kernels_version": importlib.metadata.version("kernels")
            if self.kernel_bindings
            else None,
        }

    def generate(self, messages: list[dict], tools: list[dict], seconds: float) -> str:
        native = self.profile["protocol"] != "bash"
        if self.profile["protocol"] == "lfm2_tool":
            tools = [tool["function"] for tool in tools]
        tool_payload: Any = tools if native else None
        if self.profile["protocol"] == "gemma4_tool":
            messages = _gemma4_history(messages)
        text = self.tokenizer.apply_chat_template(
            messages,
            tools=tool_payload,
            tokenize=False,
            add_generation_prompt=True,
            **(
                {"enable_thinking": self.profile["profile"]["enable_thinking"]}
                if "enable_thinking" in self.profile["profile"]
                else {}
            ),
        )
        inputs = self.tokenizer(text, return_tensors="pt", add_special_tokens=False).to(
            self.model.device
        )
        count = inputs["input_ids"].shape[-1]
        maximum = self.profile["profile"]["max_new_tokens"]
        if count + maximum > self.context:
            raise ValueError("context_limit")
        self.input_tokens += count
        self.torch.manual_seed(self.profile["profile"]["seed"])
        processors: list[Any] = [_FiniteScores(self.torch)]
        presence = self.profile["profile"].get("presence_penalty", 0)
        if presence:
            processors.append(_PresencePenalty(self.torch, count, presence))
        stopping = {}
        eos = self.profile["profile"].get("eos_token_ids")
        if eos is not None:
            stopping["eos_token_id"] = eos
        sampling = {
            key: self.profile["profile"][key]
            for key in ("top_k", "min_p", "repetition_penalty")
            if key in self.profile["profile"]
        }
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=maximum,
                logits_processor=processors,
                max_time=max(1.0, seconds),
                do_sample=self.temperature > 0,
                temperature=self.temperature if self.temperature > 0 else None,
                top_p=self.profile["profile"].get("top_p")
                if self.temperature > 0
                else None,
                pad_token_id=self.tokenizer.eos_token_id,
                use_cache=self.profile["profile"].get("use_cache", True),
                **sampling,
                **stopping,
            )
        generated = output[0, count:]
        eos = self.profile["profile"].get(
            "eos_token_ids", self.model.generation_config.eos_token_id
        )
        eos_ids = eos if isinstance(eos, list) else [eos]
        if len(generated) and int(generated[-1]) in eos_ids:
            self.last_generation_finish = "eos"
        elif len(generated) >= maximum:
            self.last_generation_finish = "length"
        else:
            self.last_generation_finish = "time"
        self.output_tokens += len(generated)
        decoded = self.tokenizer.decode(generated, skip_special_tokens=False)
        if not isinstance(decoded, str):
            raise ValueError("backend_decode_response")
        ending = self.tokenizer.eos_token
        if ending and decoded.endswith(ending):
            decoded = decoded[: -len(ending)]
        return decoded

    def memory(self) -> dict[str, int]:
        return {
            "cuda_peak_allocated_bytes": self.torch.cuda.max_memory_allocated(),
            "cuda_peak_reserved_bytes": self.torch.cuda.max_memory_reserved(),
        }

    def close(self) -> None:
        del self.model
        gc.collect()
        self.torch.cuda.empty_cache()
