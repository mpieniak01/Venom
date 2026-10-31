"""One pinned Transformers checkpoint at a time; optional imports are lazy."""

import gc
import importlib.metadata
import time
from pathlib import Path
from typing import Any


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
            "torch_version": torch.__version__,
            "quantization": "bnb-nf4" if quantized else dtype_name,
            "bitsandbytes_version": importlib.metadata.version("bitsandbytes")
            if quantized
            else None,
            "context_tokens": self.context,
        }

    def generate(self, messages: list[dict], tools: list[dict], seconds: float) -> str:
        native = self.profile["protocol"] != "bash"
        if self.profile["protocol"] == "lfm2_tool":
            tools = [tool["function"] for tool in tools]
        tool_payload: Any = tools if native else None
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
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=maximum,
                logits_processor=[_FiniteScores(self.torch)],
                max_time=max(1.0, seconds),
                do_sample=self.temperature > 0,
                temperature=self.temperature if self.temperature > 0 else None,
                top_p=self.profile["profile"].get("top_p")
                if self.temperature > 0
                else None,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0, count:]
        eos = self.model.generation_config.eos_token_id
        eos_ids = eos if isinstance(eos, list) else [eos]
        self.last_generation_finish = (
            "eos"
            if len(generated) and int(generated[-1]) in eos_ids
            else "length"
            if len(generated) >= maximum
            else "time"
        )
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
