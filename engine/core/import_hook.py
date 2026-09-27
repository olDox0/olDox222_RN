from __future__ import annotations

import sys
import importlib
import importlib.abc
import importlib.util

from types import ModuleType
from functools import lru_cache
from importlib.machinery import PathFinder

# -------------------------
# CACHE GLOBAL
# -------------------------

@lru_cache(maxsize=1024)
def _cached_import(name: str) -> ModuleType:
    return importlib.import_module(name)


# -------------------------
# LOADER LAZY
# -------------------------

class LazyModule(ModuleType):
    def __init__(self, name: str):
        super().__init__(name)
        self._real_module = None

    def _load(self):
        if self._real_module is None:
            real = _cached_import(self.__name__)
            sys.modules[self.__name__] = real
            self._real_module = real
        return self._real_module

    def __getattr__(self, item):
        return getattr(self._load(), item)


# -------------------------
# FINDER CUSTOM
# -------------------------

class LazyImportFinder(importlib.abc.MetaPathFinder):

    def __init__(self, target_prefixes: list[str] | None = None):
        self.target_prefixes = target_prefixes or []

    def find_spec(self, fullname, path, target=None):
        if not self._should_intercept(fullname):
            return None

        spec = PathFinder.find_spec(fullname, path)
        if spec is None:
            return None

        return importlib.util.spec_from_loader(
            fullname,
            LazyImportLoader(fullname),
            origin=spec.origin
        )

    def _should_intercept(self, fullname: str) -> bool:
        if fullname in sys.builtin_module_names:
            return False
        return any(fullname.startswith(p) for p in self.target_prefixes)


# -------------------------
# LOADER
# -------------------------

class LazyImportLoader(importlib.abc.Loader):

    def __init__(self, fullname: str):
        self.fullname = fullname

    def create_module(self, spec):
        return LazyModule(spec.name)

    def exec_module(self, module):
        # NÃO carrega aqui → lazy real
        pass


# -------------------------
# ATIVADOR
# -------------------------

def install_lazy_imports(prefixes: list[str]):
    finder = LazyImportFinder(prefixes)
    sys.meta_path.insert(0, finder)