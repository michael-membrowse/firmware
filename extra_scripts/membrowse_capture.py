# trunk-ignore-all(ruff/F821)
# trunk-ignore-all(flake8/F821): For SConstruct imports
"""Dump linker scripts, --defsym pairs, and the map-file path to
$BUILD_DIR/membrowse.json so the MemBrowse CI workflow can pass them to the
action without hand-maintaining per-target config.

Reads SCons' resolved $LINKFLAGS at link time, so it inherits whatever the
platform package supplies (e.g. esp32 chip-specific .ld scripts, stm32
LD_MAX_SIZE defsyms).
"""

import json
import os

Import("env")


def _unquote(s):
    # SCons keeps quotes that the build literally wraps around a value
    # (e.g. esp32/stm32 use -Wl,-Map="..."), which would otherwise become
    # part of the recorded path/name.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _flatten(flags):
    out = []
    for f in flags:
        f = env.subst(f)
        if not f:
            continue
        if f.startswith("-Wl,"):
            out.extend(_unquote(p) for p in f[4:].split(",") if p)
        else:
            out.append(_unquote(f))
    return out


def _resolve_ld(name, search_dirs):
    # Many frameworks pass linker scripts by bare name (e.g. Adafruit nRF52's
    # `-T nrf52840_s140_v6.ld`, ESP-IDF's `-T esp32s3.peripherals.ld`) and let
    # the linker locate them via `-L` search paths. MemBrowse has no knowledge
    # of those paths, so resolve to an absolute path here.
    if os.path.isabs(name) or os.path.exists(name):
        return name
    for d in search_dirs:
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            return os.path.abspath(cand)
    return name


def _capture(target, source, env):
    flags = _flatten(env["LINKFLAGS"])

    # Collect linker library search dirs (-L) so bare `-T` scripts resolve.
    search_dirs = []
    i = 0
    while i < len(flags):
        t = flags[i]
        if t == "-L" and i + 1 < len(flags):
            search_dirs.append(_unquote(flags[i + 1])); i += 2; continue
        if t.startswith("-L") and len(t) > 2:
            search_dirs.append(_unquote(t[2:])); i += 1; continue
        i += 1
    search_dirs.append(env.subst("$BUILD_DIR"))
    for p in env.get("LIBPATH", []):
        search_dirs.append(env.subst(p))

    ld, defsyms = [], []
    map_path = ""
    i = 0
    while i < len(flags):
        t = flags[i]
        if t == "-T" and i + 1 < len(flags):
            ld.append(_unquote(flags[i + 1])); i += 2; continue
        if t.startswith("-T") and len(t) > 2:
            ld.append(_unquote(t[2:])); i += 1; continue
        if t == "--defsym" and i + 1 < len(flags):
            defsyms.append(_unquote(flags[i + 1])); i += 2; continue
        if t.startswith("--defsym="):
            defsyms.append(_unquote(t[len("--defsym="):])); i += 1; continue
        if t in ("-Map", "--Map") and i + 1 < len(flags):
            map_path = _unquote(flags[i + 1]); i += 2; continue
        if t.startswith("-Map=") or t.startswith("--Map="):
            map_path = _unquote(t.split("=", 1)[1]); i += 1; continue
        i += 1

    ld = [_resolve_ld(s, search_dirs) for s in ld]

    info = {
        "ld": list(dict.fromkeys(ld)),
        "defsyms": list(dict.fromkeys(defsyms)),
        "map": map_path,
    }
    out_path = os.path.join(env.subst("$BUILD_DIR"), "membrowse.json")
    with open(out_path, "w") as f:
        json.dump(info, f, indent=2)
    print(f"MemBrowse capture -> {out_path}")


env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", _capture)
