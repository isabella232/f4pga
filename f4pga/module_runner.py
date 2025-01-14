"""
Dynamically import and run F4PGA modules.
"""

from contextlib import contextmanager
import importlib.util as importlib_util
from pathlib import Path

from colorama import Style

from f4pga.module import Module, ModuleContext, get_mod_metadata
from f4pga.common import ResolutionEnv, deep, sfprint


@contextmanager
def _add_to_sys_path(path: str):
    import sys
    old_syspath = sys.path
    sys.path = [path] + sys.path
    try:
        yield
    finally:
        sys.path = old_syspath


def import_module_from_path(path: str):
    absolute_path = str(Path(path).resolve())
    with _add_to_sys_path(path):
        spec = importlib_util.spec_from_file_location(absolute_path, absolute_path)
        module = importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


# Once imported a module will be added to that dict to avaid re-importing it
preloaded_modules = {}


def get_module(path: str):
    global preloaded_modules

    cached = preloaded_modules.get(path)
    if cached:
        return cached.ModuleClass

    mod = import_module_from_path(path)
    preloaded_modules[path] = mod

    # All F4PGA modules should expose a `ModuleClass` type/alias which is a class implementing a Module interface
    return mod.ModuleClass


class ModRunCtx:
    share: str
    bin: str
    config: 'dict[str, ]'

    def __init__(self, share: str, bin: str, config: 'dict[str, ]'):
        self.share = share
        self.bin = bin
        self.config = config

    def make_r_env(self):
        return ResolutionEnv(self.config['values'])


class ModuleFailException(Exception):
    module: str
    mode: str
    e: Exception

    def __init__(self, module: str, mode: str, e: Exception):
        self.module = module
        self.mode = mode
        self.e = e

    def __str__(self) -> str:
        return f"""ModuleFailException:
  Module `{self.module}` failed MODE: \'{self.mode}\'
  Exception `{type(self.e)}`: {self.e}
"""


def module_io(module: Module):
    return {
        'name': module.name,
        'takes': module.takes,
        'produces': module.produces,
        'meta': get_mod_metadata(module)
    }


def module_map(module: Module, ctx: ModRunCtx):
    try:
        mod_ctx = ModuleContext(
            module,
            ctx.config,
            ctx.make_r_env(),
            ctx.share,
            ctx.bin
        )
    except Exception as e:
        raise ModuleFailException(module.name, 'map', e)

    return deep(lambda p: str(Path(p).resolve()))(vars(mod_ctx.outputs))


def module_exec(module: Module, ctx: ModRunCtx):
    try:
        mod_ctx = ModuleContext(
            module,
            ctx.config,
            ctx.make_r_env(),
            ctx.share,
            ctx.bin
        )
    except Exception as e:
        raise ModuleFailException(module.name, 'exec', e)

    sfprint(1, f'Executing module `{Style.BRIGHT + module.name + Style.RESET_ALL}`:')
    current_phase = 1
    try:
        for phase_msg in module.execute(mod_ctx):
            sfprint(1, f'    {Style.BRIGHT}[{current_phase}/{module.no_of_phases}] {Style.RESET_ALL}: {phase_msg}')
            current_phase += 1
    except Exception as e:
        raise ModuleFailException(module.name, 'exec', e)

    sfprint(1, f'Module `{Style.BRIGHT + module.name + Style.RESET_ALL}` has finished its work!')
