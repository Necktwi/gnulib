#!/usr/bin/python
# encoding: UTF-8



import codecs
import os
import stat
import sys
import traceback

from pygnulib.error import CommandLineError
from pygnulib.error import UnknownModuleError

from pygnulib.config import Base as BaseConfig
from pygnulib.config import Cache as CacheConfig

from pygnulib.module import dummy_required
from pygnulib.module import libtests_required
from pygnulib.module import transitive_closure

from pygnulib.parser import CommandLine as CommandLineParser

from pygnulib.filesystem import GnulibGit as GnulibGitFS



IGNORED_LICENSES = {
    "GPLed build tool",
    "public domain",
    "unlimited",
    "unmodifiable license text",
}



def list_hook(gnulib, *args, **kwargs):
    (_, _) = (args, kwargs)
    for module in sorted(gnulib.modules(full=False)):
        print(module.name)
    return os.EX_OK



def extract_hook(program, gnulib, mode, namespace, *args, **kwargs):
    (_, _) = (args, kwargs)
    mode = mode.replace("extract-", "")
    mode += "s" if mode == "maintainer" else ""
    for module in namespace["modules"]:
        try:
            module = gnulib.module(module, full=True)
            print(module[mode], file=sys.stdout)
        except UnknownModuleError as error:
            print("{0}:".format(program), "warning:", error, file=sys.stderr)
    return os.EX_OK



def import_hook(script, gnulib, namespace, verbosity, options, *args, **kwargs):
    (_, _) = (args, kwargs)
    config = BaseConfig(**namespace)
    values = transitive_closure(gnulib.module, config.modules, config.options)
    (base, full, main, final, tests) = transitive_closure(gnulib.module, config.modules, config.options)

    # Print some information about modules.
    print("Module list with included dependencies (indented):", file=sys.stdout)
    BOLD_ON = BOLD_OFF = ""
    mode = os.fstat(sys.stdout.fileno()).st_mode
    if not (stat.S_ISFIFO(mode) or stat.S_ISREG(mode)):
        BOLD_ON = "\033[1m"
        BOLD_OFF = "\033[0m"
    for module in sorted(final):
        manual = module.name in config.modules
        prefix = "  " if manual else "    "
        bold_on = BOLD_ON if manual else ""
        bold_off = BOLD_OFF if manual else ""
        print("{0}{1}{2}{3}".format(prefix, bold_on, module.name, bold_off), file=sys.stdout)
    if verbosity >= 1:
        print("Main module list:", file=sys.stdout)
        for module in sorted(main):
            print("  {0}".format(module.name), file=sys.stdout)
        print("Tests-related module list:", file=sys.stdout)
        for module in sorted(tests):
            print("  {0}".format(module.name), file=sys.stdout)

    # Determine if dummy needs to be added to main or test sets.
    if "dummy" not in config.avoid:
        if dummy_required(main):
            main.add(gnulib.module("dummy"))
        if libtests_required(tests) and dummy_required(tests):
            tests.add(gnulib.module("dummy"))

    # Determine license incompatibilities, if any.
    incompatibilities = set()
    if config.licenses & {"LGPLv2", "LGPLv2+", "LGPLv3", "LGPLv3+"}:
        for (name, licenses) in ((module.name, module.licenses) for module in main):
            if not ((IGNORED_LICENSES & licenses) or (config.licenses & licenses)):
                incompatibilities.add((name, licenses))
    if incompatibilities:
        print("{0}: *** incompatible license on modules:".format(script), file=sys.stderr)
        for (name, licenses) in sorted(incompatibilities):
            print(" " * 16, "{0:50}{1}".format(name, " ".join(sorted(licenses))), file=sys.stderr)
        print("{0}: *** Stop.".format(script), file=sys.stderr)
        return os.EX_DATAERR
    return os.EX_OK



def add_import_hook(script, gnulib, namespace, verbosity, options, *args, **kwargs):
    (_, _) = (args, kwargs)
    modules = set(namespace.pop("modules"))
    config = CacheConfig(**namespace)
    namespace = {k:v for (k, v) in config.items()}
    namespace["modules"] = (config.modules | modules)
    return import_hook(script, gnulib, namespace, verbosity, options)



def remove_import_hook(script, gnulib, namespace, verbosity, options, *args, **kwargs):
    (_, _) = (args, kwargs)
    modules = set(namespace.pop("modules"))
    config = CacheConfig(**namespace)
    namespace = {k:v for (k, v) in config.items()}
    namespace["modules"] = (config.modules - modules)
    return import_hook(script, gnulib, namespace, verbosity, options)



def update_hook(script, gnulib, namespace, verbosity, options, *args, **kwargs):
    (_, _) = (args, kwargs)
    config = CacheConfig(**namespace)
    namespace = {k:v for (k, v) in config.items()}
    return import_hook(script, gnulib, namespace, verbosity, options)



HOOKS = {
    "list": list_hook,
    "extract": extract_hook,
    "import": import_hook,
    "add-import": add_import_hook,
    "remove-import": remove_import_hook,
    "update": update_hook,
}



def main(script, gnulib, program, arguments, environ):
    gnulib = GnulibGitFS(gnulib)
    parser = CommandLineParser(program)
    try:
        (namespace, mode, verbosity, options) = parser.parse(arguments)
    except CommandLineError as error:
        print(parser.usage, file=sys.stderr)
        print(error, file=sys.stderr)
        return os.EX_USAGE
    if mode == "help":
        print(parser.help, file=sys.stdout)
        return os.EX_OK
    kwargs = {
        "script": script,
        "program": program,
        "gnulib": gnulib,
        "mode": mode,
        "namespace": namespace,
        "verbosity": verbosity,
        "options": options,
    }
    for (action, callback) in HOOKS.items():
        if mode.startswith(action):
            return callback(**kwargs)
    return os.EX_SOFTWARE



if __name__ == "__main__":
    script = sys.argv[0]
    gnulib = os.path.dirname(os.path.realpath(__file__))
    program = os.path.basename(script)
    log = os.path.join(os.getcwd(), "{0}.log".format(program))
    arguments = list(sys.argv[1:])
    environ = dict(os.environ)
    try:
        result = main(script, gnulib, program, arguments, environ)
    except BaseException as error:
        with codecs.open(log, "wb", "UTF-8") as stream:
            program = repr(program) if " " in program else program
            arguments = " ".join(repr(arg) if " " in arg else arg for arg in arguments)
            print(traceback.format_exc(), file=stream)
            print("COMMAND:", program, arguments, file=stream)
            print("VERSION:", gnulib, file=stream)
        typeid = type(error)
        module = typeid.__module__
        name = typeid.__name__
        if module != "builtins":
            error = "{0}.{1}: {2}".format(module, name, error)
        else:
            error = "{0}: {1}".format(name, error)
        print("{0}:".format(program), "***", error, file=sys.stderr)
        print("{0}:".format(program), "***", log, file=sys.stderr)
        result = os.EX_SOFTWARE
    sys.exit(result)