"""Self-contained UnRAR Python bindings.

This package compiles the official UnRAR C++ source into a native Python
extension. No external unrar/7z binaries are required.
"""

from unrar.rarfile import RarFile, BadRarFile, RarWrongPassword, NeedFirstVolume

__all__ = ["RarFile", "BadRarFile", "RarWrongPassword", "NeedFirstVolume"]
