"""Built-in skills package init."""
from .time_skill import TimeSkill, register as register_time
from .system_skill import SystemSkill, register as register_system
from .file_skill import FileSkill, register as register_file
from .web_skill import WebSkill, register as register_web
from .meta_skill import MetaSkill, register as register_meta
from .memory_skill import MemorySkill, register as register_memory

__all__ = [
    "TimeSkill",
    "SystemSkill",
    "FileSkill",
    "WebSkill",
    "MetaSkill",
    "MemorySkill",
    "register_time",
    "register_system",
    "register_file",
    "register_web",
    "register_meta",
    "register_memory",
]