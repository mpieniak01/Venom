"""Execution package: providers are loaded only when their public entrypoint is used."""

from importlib import import_module

__all__ = ["KernelBuilder", "SkillManager", "SkillValidationError"]


def __getattr__(name: str):
    if name == "KernelBuilder":
        return getattr(import_module(".kernel_builder", __name__), name)
    if name in {"SkillManager", "SkillValidationError"}:
        return getattr(import_module(".skill_manager", __name__), name)
    raise AttributeError(name)
