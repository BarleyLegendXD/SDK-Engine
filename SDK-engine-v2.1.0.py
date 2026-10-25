import sys
import os
import re
import importlib.util
import importlib.metadata

ENGINE_NAME = "SDK-engine-v2.1.0"
ENGINE_VERSION = "2.1.0"


def _set_console_title(title):
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        else:
            sys.stdout.write(f"\x1b]0;{title}\x07")
            sys.stdout.flush()
    except Exception:
        pass


class Requirements:
    REQUIRED = {
        "glfw": "2.5",
        "moderngl": "5.8",
        "numpy": "1.17",
        "PIL": "9.0",
    }
    PIP_NAMES = {
        "glfw": "glfw",
        "moderngl": "moderngl",
        "numpy": "numpy",
        "PIL": "Pillow",
    }

    @staticmethod
    def _parse(version):
        parts = []
        for chunk in str(version).split("."):
            m = re.match(r"\d+", chunk)
            if not m:
                break
            parts.append(int(m.group()))
        return tuple(parts)

    @staticmethod
    def split_req(text):
        m = re.match(r"\s*([^<>=!,\s]+)\s*(.*)", str(text))
        return m.group(1), m.group(2)

    @classmethod
    def clauses(cls, spec):
        parts = [p for p in str(spec or "").replace(" ", "").split(",") if p]
        found = [re.match(r"(>=|<=|==|!=|>|<)?(.*)", p) for p in parts]
        return [(m.group(1) or ">=", m.group(2)) for m in found]

    @classmethod
    def pip_spec(cls, spec):
        return ",".join(op + ref for op, ref in cls.clauses(spec))

    @classmethod
    def judge(cls, version, spec):
        have = cls._parse(version)
        for op, ref in cls.clauses(spec):
            need = cls._parse(ref)
            size = max(len(have), len(need))
            a = have + (0,) * (size - len(have))
            b = need + (0,) * (size - len(need))
            ok = {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b, "==": a == b, "!=": a != b}[op]
            if not ok:
                return "too old" if op in (">=", ">") else "too new" if op in ("<=", "<") else "mismatch"
        return None

    @classmethod
    def _installed_version(cls, name):
        try:
            return importlib.metadata.version(cls.PIP_NAMES.get(name, name))
        except importlib.metadata.PackageNotFoundError:
            return None

    @classmethod
    def scan(cls, required=None):
        required = cls.REQUIRED if required is None else required
        missing = []
        outdated = []
        for name, spec in required.items():
            if importlib.util.find_spec(name) is None:
                missing.append(name)
                continue
            if spec is None:
                continue
            current = cls._installed_version(name)
            if current is None:
                continue
            verdict = cls.judge(current, spec)
            if verdict:
                outdated.append((name, current, cls.pip_spec(spec), verdict))
        return missing, outdated

    @classmethod
    def verify(cls, required=None):
        required = cls.REQUIRED if required is None else required
        missing, outdated = cls.scan(required)
        if not missing and not outdated:
            return True
        if missing:
            print(f"Missing libraries: {', '.join(missing)}")
        for name, current, spec, verdict in outdated:
            print(f"Incompatible library: {name} {current} is {verdict} (need {spec})")
        packages = [f'"{cls.PIP_NAMES.get(n, n)}{cls.pip_spec(required.get(n))}"' for n in missing + [o[0] for o in outdated]]
        print(f"Install: {sys.executable} -m pip install --upgrade {' '.join(packages)}")
        print("Press Enter to exit...")
        try:
            input()
        except EOFError:
            pass
        return False


_set_console_title(ENGINE_NAME)
if not Requirements.verify():
    sys.exit(1)

import base64
import concurrent.futures
import datetime
import functools
import queue
import threading
import time
import traceback
import types
import zipfile
import zlib

import glfw
import moderngl
import numpy as np
from PIL import Image


class SDKEngine:
    DEFAULT_CFG = {
        "debug": True,
        "width": 1280,
        "height": 720,
        "fps": 60,
        "vsync": True,
        "msaa": 0,
        "title": "SDK-Engine",
        "gl_major": 3,
        "gl_minor": 3,
        "max_dt": 0.25,
        "clear_color": "10,10,15",
        "hyperthreading": True,
    }

    CON_SCALE = 4 / 3
    CON_FONT = (
        "c-l=;!D`$v5PiiU=P>Nvf(k~y<<x?LKp56oJ?*I<5fI3SfOFVG798-Wr*EXtc6R0Q8)@FmJP"
        "T-M=h<3V#Mp3*2Y(T=bk2_g<Y1*_3~|^lVS_PU%M)XaSa4as17-f43pYfP$QQZj1`_ZW<Hhr"
        "I_YF(F?QiP>ISDPn1wWY3ybli39K+%7NZsfa52hOfeF`KXk0Vgb$Kvg&a{srCR?+@ydH(sXm"
        "6hKLg!T7*?;L~#DFmcamQoVt(sf;#F~(9#9C2J9-Q)FW-kj_Ht$ZNVv;e2=i^JWsP4=^v=we"
        "xMraaejAip2SYtG2)+kVTcW6n7awVoj#%ZH1bD%Ly~`qQLy{%pLVT58@2nEiUZlaD0iLXGm="
        "k)Q2v)^kS9L5KG*zu>Hz!-F3FXP;8FQFDIbckPYg{1?TcQ~f=|j4MvmX^7^m{Q{dRKK3SVh5"
        "ZUnwNH;GKyOrlwMI1#1QmdO)Cnq|>I7U=f%6yNop>vizg|2%$RhGXd(^b8d8ZeP^B;OyDL@@"
        "5)PDGpzspm?B+`pauzIVx6flJC(x&|bs$Og<"
    )

    def __init__(self):
        self.logs = []
        self.max_logs = 200
        self.events = {}
        self.libs = {}
        self._lib_order = []
        self._current_lib = None
        self._patches = {}
        self._added = {}
        self._reported_errors = set()
        self._in_log = False
        self.libs_dir = "libs"
        self.mods_dir = "mods"
        self.assets_dir = "assets"
        self.cache_dir = "cache"
        self.cfg_path = "config.cfg"
        self.targets = {}
        self.window = None
        self.ctx = None
        self.screen_size = (0, 0)
        self.window_size = (0, 0)
        self.is_fullscreen = False
        self._windowed_rect = (100, 100, 1280, 720)
        self.frame = 0
        self._main_ident = threading.get_ident()
        self._mainq = queue.SimpleQueue()
        self.pool = None
        self._tasks = []
        self._flight = []
        self._asset_index = {}
        self._asset_missing = set()
        self._asset_scan_time = 0.0
        self._tex_cache = {}

        os.makedirs(self.cache_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_file = os.path.join(self.cache_dir, f"log_{stamp}.txt")
        self.log(f"Booting {ENGINE_NAME}...", (150, 255, 255))

        self.setup_env()
        self.scan_assets()
        self.cfg = self.load_cfg(self.cfg_path)
        self.validate_cfg()
        self._setup_threads()

        self.state = {
            "engine": self,
            "running": True,
            "cfg": self.cfg,
            "ctx": None,
            "window": None,
            "dt": 0.0,
            "time": 0.0,
            "frame": 0,
            "size": (0, 0),
            "shared": {},
        }
        self.targets = {
            "engine": self,
            "SDKEngine": SDKEngine,
            "Requirements": Requirements,
        }

        self.create_window()
        self.load_libs()

    def cfg_num(self, key, default):
        v = self.cfg.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return default
        return v

    def cfg_color(self, key, default=(0, 0, 0)):
        v = self.cfg.get(key, None)
        if isinstance(v, str):
            try:
                parts = [int(p) for p in v.replace(" ", "").split(",")]
                if len(parts) == 3:
                    return tuple(max(0, min(255, p)) for p in parts)
            except ValueError:
                pass
        return default

    def log(self, text, color=(255, 255, 255)):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        self.logs.append((line, tuple(color)))
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        try:
            print(line)
        except Exception:
            pass
        try:
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        if not self._in_log:
            self._in_log = True
            try:
                self.emit("log", {"text": line, "color": tuple(color)})
            finally:
                self._in_log = False

    def setup_env(self):
        for d in (self.mods_dir, self.assets_dir, self.libs_dir, self.cache_dir):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.cfg_path):
            self._write_cfg(self.cfg_path, self.DEFAULT_CFG)
            self.log("I/O: Generated config.cfg", (100, 255, 100))

    def load_cfg(self, path):
        data = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = [x.strip() for x in line.split("=", 1)]
                    k = k.lower()
                    low = v.lower()
                    if low in ("true", "false"):
                        v = low == "true"
                    else:
                        try:
                            v = float(v) if "." in v else int(v)
                        except ValueError:
                            pass
                    data[k] = v
        except Exception as e:
            self.log(f"CFG Error: {e}", (255, 50, 50))
        return data

    @staticmethod
    def _write_cfg(path, data):
        with open(path, "w", encoding="utf-8") as f:
            for k, v in data.items():
                if isinstance(v, bool):
                    f.write(f"{k} = {'true' if v else 'false'}\n")
                else:
                    f.write(f"{k} = {v}\n")

    def validate_cfg(self):
        changed = False
        for k, v in self.DEFAULT_CFG.items():
            if k not in self.cfg:
                self.log(f"CFG: Missing '{k}', set to default ({v})", (255, 255, 50))
                self.cfg[k] = v
                changed = True
        if changed:
            self.save_cfg()

    def save_cfg(self):
        try:
            self._write_cfg(self.cfg_path, self.cfg)
            self.log("CFG: Saved", (100, 255, 100))
        except OSError as e:
            self.log(f"CFG Error: {e}", (255, 50, 50))

    def create_window(self):
        if not glfw.init():
            self.log("GLFW: init failed", (255, 50, 50))
            raise RuntimeError("GLFW init failed")
        width = int(self.cfg_num("width", 1280))
        height = int(self.cfg_num("height", 720))
        title = str(self.cfg.get("title", "SDK-Engine"))
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, int(self.cfg_num("gl_major", 3)))
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, int(self.cfg_num("gl_minor", 3)))
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)
        glfw.window_hint(glfw.SAMPLES, int(self.cfg_num("msaa", 0)))
        glfw.window_hint(glfw.RESIZABLE, glfw.TRUE)
        self.window = glfw.create_window(width, height, title, None, None)
        if not self.window:
            glfw.terminate()
            self.log("GLFW: window creation failed", (255, 50, 50))
            raise RuntimeError("GLFW window creation failed")
        glfw.make_context_current(self.window)
        glfw.swap_interval(1 if self.cfg.get("vsync", True) else 0)
        self.ctx = moderngl.create_context()
        info = self.ctx.info
        self.log(f"GL: {info.get('GL_RENDERER', '?')} | {info.get('GL_VERSION', '?')}", (80, 150, 255))
        x, y = glfw.get_window_pos(self.window)
        self._windowed_rect = (x, y, width, height)
        self._bind_callbacks()
        self._sync_size()
        self.state["ctx"] = self.ctx
        self.state["window"] = self.window
        self.log(f"Window: {self.screen_size[0]}x{self.screen_size[1]}, Title: '{title}'", (255, 0, 0))

    def _bind_callbacks(self):
        w = self.window
        glfw.set_window_close_callback(w, lambda _w: self._dispatch("close"))
        glfw.set_framebuffer_size_callback(w, self._cb_framebuffer)
        glfw.set_window_focus_callback(w, lambda _w, f: self._dispatch("focus", focused=bool(f)))
        glfw.set_key_callback(w, self._cb_key)
        glfw.set_char_callback(w, lambda _w, c: self._dispatch("char", char=chr(c)))
        glfw.set_mouse_button_callback(w, lambda _w, b, a, m: self._dispatch("mouse_button", button=b, action=a, mods=m))
        glfw.set_cursor_pos_callback(w, lambda _w, x, y: self._dispatch("mouse_move", x=x, y=y))
        glfw.set_scroll_callback(w, lambda _w, dx, dy: self._dispatch("scroll", dx=dx, dy=dy))
        glfw.set_drop_callback(w, lambda _w, paths: self._dispatch("drop", paths=list(paths)))

    def _dispatch(self, kind, **data):
        data["type"] = kind
        self.emit(kind, data)
        self.emit("event", data)

    def _cb_framebuffer(self, _w, width, height):
        self._sync_size()
        self._dispatch("resize", size=self.screen_size)

    def _cb_key(self, _w, key, scancode, action, mods):
        if key == glfw.KEY_F11 and action == glfw.PRESS:
            self.toggle_fullscreen()
        self._dispatch("key", key=key, scancode=scancode, action=action, mods=mods)

    def _sync_size(self):
        if self.window is None:
            return
        self.screen_size = tuple(glfw.get_framebuffer_size(self.window))
        self.window_size = tuple(glfw.get_window_size(self.window))
        if self.ctx is not None and self.screen_size[0] > 0 and self.screen_size[1] > 0:
            self.ctx.viewport = (0, 0, self.screen_size[0], self.screen_size[1])
        self.state["size"] = self.screen_size

    def set_title(self, title):
        self.cfg["title"] = str(title)
        glfw.set_window_title(self.window, str(title))

    def toggle_fullscreen(self):
        if not self.is_fullscreen:
            x, y = glfw.get_window_pos(self.window)
            w, h = glfw.get_window_size(self.window)
            self._windowed_rect = (x, y, w, h)
            monitor = glfw.get_primary_monitor()
            mode = glfw.get_video_mode(monitor)
            glfw.set_window_monitor(self.window, monitor, 0, 0, mode.size.width, mode.size.height, mode.refresh_rate)
        else:
            x, y, w, h = self._windowed_rect
            glfw.set_window_monitor(self.window, None, x, y, w, h, 0)
        self.is_fullscreen = not self.is_fullscreen
        glfw.swap_interval(1 if self.cfg.get("vsync", True) else 0)
        self._sync_size()

    def quit(self):
        self.state["running"] = False

    @staticmethod
    def _asset_key(name):
        key = str(name).replace("\\", "/").strip().lower()
        while key.startswith("./"):
            key = key[2:]
        return key.lstrip("/")

    def scan_assets(self, quiet=False):
        base = os.path.abspath(self.assets_dir)
        index = {}
        ambiguous = {}
        count = 0
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for fn in sorted(files):
                if fn.startswith("."):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                count += 1
                for key in (rel, os.path.splitext(rel)[0], fn, os.path.splitext(fn)[0]):
                    key = key.lower()
                    prev = index.get(key)
                    if prev is None:
                        index[key] = full
                    elif prev != full and full not in ambiguous.get(key, ()):
                        ambiguous.setdefault(key, [prev]).append(full)
        self._asset_index = index
        self._asset_scan_time = time.monotonic()
        if quiet:
            return count
        self._asset_missing.clear()
        for key, paths in sorted(ambiguous.items()):
            rels = ", ".join(os.path.relpath(x, base).replace(os.sep, "/") for x in paths)
            self.log(f"ASSET: '{key}' is ambiguous ({rels}), using '{os.path.relpath(index[key], base).replace(os.sep, '/')}'", (255, 255, 50))
        self.log(f"ASSETS: {count} files indexed in '{self.assets_dir}'", (150, 255, 255))
        return count

    def asset_path(self, name, quiet=False):
        key = self._asset_key(name)
        path = self._asset_index.get(key)
        if path is None and time.monotonic() - self._asset_scan_time > 1.0:
            self.scan_assets(quiet=True)
            path = self._asset_index.get(key)
        if path is None and not quiet and key not in self._asset_missing:
            self._asset_missing.add(key)
            self.log(f"ASSET Error: '{name}' not found in '{self.assets_dir}'", (255, 50, 50))
        return path

    def has_asset(self, name):
        return self.asset_path(name, quiet=True) is not None

    def asset_bytes(self, name):
        path = self.asset_path(name)
        if path is None:
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as e:
            self.log(f"ASSET Error: cannot read '{name}' ({e})", (255, 50, 50))
            return None

    def asset_text(self, name, encoding="utf-8"):
        data = self.asset_bytes(name)
        if data is None:
            return None
        return data.decode(encoding, "replace")

    @staticmethod
    def _decode_image(path, flip):
        with Image.open(path) as im:
            im = im.convert("RGBA")
            size = im.size
            data = np.asarray(im, dtype=np.uint8)
        if flip:
            data = data[::-1]
        return size, np.ascontiguousarray(data).tobytes()

    def _make_texture(self, key, size, data, smooth, repeat, mipmaps):
        tex = self.ctx.texture(size, 4, data)
        near = moderngl.LINEAR if smooth else moderngl.NEAREST
        if mipmaps:
            tex.build_mipmaps()
            tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR if smooth else moderngl.NEAREST_MIPMAP_NEAREST, near)
        else:
            tex.filter = (near, near)
        tex.repeat_x = bool(repeat)
        tex.repeat_y = bool(repeat)
        self._tex_cache[key] = tex
        return tex

    def texture(self, name, flip=True, smooth=True, repeat=False, mipmaps=False):
        if threading.get_ident() != self._main_ident:
            raise RuntimeError("texture() must be called from the main thread, use texture_async()")
        path = self.asset_path(name)
        if path is None:
            return None
        key = (path, flip, smooth, repeat, mipmaps)
        tex = self._tex_cache.get(key)
        if tex is not None:
            return tex
        try:
            size, data = self._decode_image(path, flip)
        except Exception as e:
            self.log(f"ASSET Error: cannot decode '{name}' ({e})", (255, 50, 50))
            return None
        return self._make_texture(key, size, data, smooth, repeat, mipmaps)

    def texture_async(self, name, callback, flip=True, smooth=True, repeat=False, mipmaps=False):
        path = self.asset_path(name)
        if path is None:
            return None
        key = (path, flip, smooth, repeat, mipmaps)
        cached = self._tex_cache.get(key)
        if cached is not None:
            self._mainq.put(lambda: callback(cached))
            return None

        def done(res):
            tex = self._tex_cache.get(key)
            if tex is None:
                tex = self._make_texture(key, res[0], res[1], smooth, repeat, mipmaps)
            callback(tex)

        return self.submit(self._decode_image, path, flip, callback=done)

    def release_textures(self):
        for tex in self._tex_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        self._tex_cache.clear()

    def _setup_threads(self):
        ht = bool(self.cfg.get("hyperthreading", True))
        threads = (os.cpu_count() or 1) if ht else 1
        workers = threads - 1
        if workers > 0:
            self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sdk-worker")
        self.log(f"CPU: {threads} threads (hyperthreading {'on' if ht else 'off'}), workers: {workers}", (80, 150, 255))

    def submit(self, func, *args, callback=None, **kwargs):
        def job():
            try:
                res = func(*args, **kwargs)
            except Exception as e:
                self._mainq.put(lambda err=e: self._report_error("task", func, err))
                return
            if callback is not None:
                self._mainq.put(lambda: callback(res))

        if self.pool is None:
            job()
            return None
        return self.pool.submit(job)

    def add_task(self, func, priority=0):
        self._tasks.append({"func": func, "prio": priority, "owner": self._current_lib})
        self._tasks.sort(key=lambda t: t["prio"], reverse=True)
        return self

    def _run_task(self, task):
        try:
            task["func"](self.state)
        except Exception as e:
            self._report_error("task", task["func"], e)

    def _start_tasks(self):
        if self.pool is None:
            for task in list(self._tasks):
                self._run_task(task)
        else:
            self._flight = [self.pool.submit(self._run_task, t) for t in self._tasks]

    def _join_tasks(self):
        if self._flight:
            concurrent.futures.wait(self._flight)
            self._flight = []

    def _drain(self):
        while True:
            try:
                job = self._mainq.get_nowait()
            except queue.Empty:
                return
            try:
                job()
            except Exception as e:
                self._report_error("task", job, e)

    def on(self, name, func, priority=0, once=False):
        self.events.setdefault(name, []).append(
            {"func": func, "prio": priority, "once": once, "owner": self._current_lib}
        )
        self.events[name].sort(key=lambda x: x["prio"], reverse=True)

    def off(self, name, func):
        subs = self.events.get(name)
        if subs:
            self.events[name] = [s for s in subs if s["func"] is not func]

    def _report_error(self, name, func, exc):
        key = (name, id(func), type(exc).__name__, str(exc))
        if key in self._reported_errors:
            return
        self._reported_errors.add(key)
        self.log(f"MOD ERR: Event '{name}' failed. ({type(exc).__name__}: {exc})", (255, 80, 80))
        traceback.print_exception(type(exc), exc, exc.__traceback__)

    def emit(self, name, data=None):
        subs = self.events.get(name)
        if not subs:
            return
        if threading.get_ident() != self._main_ident:
            self._mainq.put(lambda: self.emit(name, data))
            return
        payload = data if data is not None else self.state
        for sub in list(subs):
            try:
                sub["func"](payload)
            except Exception as e:
                self._report_error(name, sub["func"], e)
            if sub["once"] and sub in subs:
                subs.remove(sub)

    def _resolve_target(self, target):
        if isinstance(target, str):
            if target not in self.targets:
                raise KeyError(f"Unknown patch target '{target}'")
            return self.targets[target]
        return target

    def _wrap_patch(self, obj, prev, mode, func):
        is_class = isinstance(obj, type)

        def call(bound, inst, a, k):
            if mode == "replace":
                return func(inst, *a, **k)
            if mode == "wrap":
                return func(bound, inst, *a, **k)
            if mode == "before":
                func(inst, *a, **k)
                return bound(*a, **k)
            res = bound(*a, **k)
            out = func(inst, res, *a, **k)
            return res if out is None else out

        if is_class:
            def patched(inst, *a, **k):
                return call(types.MethodType(prev, inst), inst, a, k)
        else:
            def patched(*a, **k):
                return call(prev, obj, a, k)
        try:
            functools.update_wrapper(patched, prev)
        except Exception:
            pass
        return patched

    def _rebuild_patch(self, entry):
        obj, name = entry["target"], entry["name"]
        if not entry["chain"]:
            if entry["own"]:
                setattr(obj, name, entry["base"])
            else:
                delattr(obj, name)
            self._patches.pop((id(obj), name), None)
            return
        fn = entry["base"]
        for mode, func, owner in entry["chain"]:
            fn = self._wrap_patch(obj, fn, mode, func)
        setattr(obj, name, fn)

    def patch(self, target, name, func, mode="wrap", owner=None):
        if mode not in ("replace", "wrap", "before", "after"):
            raise ValueError(f"Unknown patch mode '{mode}'")
        obj = self._resolve_target(target)
        owner = owner or self._current_lib or "user"
        key = (id(obj), name)
        entry = self._patches.get(key)
        if entry is None:
            if isinstance(obj, type):
                raw = None
                for klass in obj.__mro__:
                    if name in vars(klass):
                        raw = vars(klass)[name]
                        break
                if raw is None:
                    raise AttributeError(f"{obj.__name__} has no attribute '{name}'")
                if isinstance(raw, (staticmethod, classmethod, property)) or not callable(raw):
                    raise TypeError(f"'{name}' is not a plain method and cannot be patched")
                entry = {"target": obj, "name": name, "base": raw, "own": name in vars(obj), "chain": []}
            else:
                if not hasattr(obj, name):
                    raise AttributeError(f"{type(obj).__name__} has no attribute '{name}'")
                cur = getattr(obj, name)
                if not callable(cur):
                    raise TypeError(f"'{name}' is not callable and cannot be patched")
                entry = {"target": obj, "name": name, "base": cur, "own": name in getattr(obj, "__dict__", {}), "chain": []}
            self._patches[key] = entry
        entry["chain"].append((mode, func, owner))
        self._rebuild_patch(entry)
        return self

    def unpatch(self, target, name, owner=None):
        obj = self._resolve_target(target)
        entry = self._patches.get((id(obj), name))
        if not entry:
            return False
        before = len(entry["chain"])
        entry["chain"] = [c for c in entry["chain"] if owner is not None and c[2] != owner]
        if len(entry["chain"]) == before:
            return False
        self._rebuild_patch(entry)
        return True

    def unpatch_all(self, owner):
        for entry in list(self._patches.values()):
            kept = [c for c in entry["chain"] if c[2] != owner]
            if len(kept) != len(entry["chain"]):
                entry["chain"] = kept
                self._rebuild_patch(entry)

    def list_patches(self):
        res = []
        for entry in self._patches.values():
            obj = entry["target"]
            label = getattr(obj, "__name__", type(obj).__name__)
            for mode, func, owner in entry["chain"]:
                res.append((owner, label, entry["name"], mode))
        return res

    def register_target(self, name, obj):
        self.targets[name] = obj
        return self

    def add_method(self, target, name, func, owner=None):
        obj = self._resolve_target(target)
        owner = owner or self._current_lib or "user"
        if hasattr(obj, name):
            raise AttributeError(f"'{name}' already exists, use patch()")
        setattr(obj, name, func if isinstance(obj, type) else types.MethodType(func, obj))
        self._added.setdefault(owner, []).append((obj, name))
        return self

    def _remove_added(self, owner):
        for obj, name in self._added.pop(owner, []):
            try:
                delattr(obj, name)
            except AttributeError:
                pass

    def get_lib(self, name):
        info = self.libs.get(name)
        return info["module"] if info and info["loaded"] else None

    def has_lib(self, name):
        return self.get_lib(name) is not None

    def _forget(self, mod_name):
        for k in [k for k in sys.modules if k == mod_name or k.startswith(mod_name + ".")]:
            sys.modules.pop(k, None)

    def _read_zip_lib(self, entry, full):
        abs_zip = os.path.abspath(full)
        try:
            with zipfile.ZipFile(abs_zip) as z:
                infos = {i.filename: i for i in z.infolist()}
                packed = [n for n, i in infos.items() if not i.is_dir() and i.compress_type != zipfile.ZIP_STORED]
                if "libcore.py" in infos:
                    core, locations = "libcore.py", [abs_zip]
                elif "libcore/__init__.py" in infos:
                    core, locations = "libcore/__init__.py", [abs_zip + "/libcore"]
                else:
                    self.log(f"LIB Error [{entry}]: file 'libcore' not found in archive", (255, 50, 50))
                    return None
                source = z.read(core)
        except (zipfile.BadZipFile, OSError) as e:
            self.log(f"LIB Error [{entry}]: cannot open archive ({e})", (255, 50, 50))
            return None
        if packed:
            self.log(f"LIB Warning [{entry}]: {len(packed)} file(s) are compressed, expected zero compression", (255, 255, 50))
        return source, f"{abs_zip}/{core}", locations

    def _import_lib(self, mod_name, path, locations, source=None):
        abs_path = os.path.abspath(path)
        existing = sys.modules.get(mod_name)
        if existing is not None:
            ef = getattr(existing, "__file__", None)
            if ef and os.path.abspath(ef) == abs_path:
                return existing
            self.log(f"LIB Error [{mod_name}]: name conflicts with another module", (255, 50, 50))
            return None
        try:
            other = importlib.util.find_spec(mod_name)
        except (ImportError, ValueError):
            other = None
        if other is not None and other.origin and os.path.abspath(other.origin) != abs_path:
            self.log(f"LIB Error [{mod_name}]: name conflicts with an installed module", (255, 50, 50))
            return None
        try:
            if source is not None:
                m = types.ModuleType(mod_name)
                m.__file__ = path
                m.__path__ = list(locations)
                m.__package__ = mod_name
                sys.modules[mod_name] = m
                exec(compile(source, path, "exec"), m.__dict__)
                return m
            spec = importlib.util.spec_from_file_location(mod_name, path, submodule_search_locations=locations)
            m = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = m
            spec.loader.exec_module(m)
            return m
        except Exception as e:
            self._forget(mod_name)
            self.log(f"LIB Error [{mod_name}]: {e}", (255, 50, 50))
            traceback.print_exc()
            return None

    def _check_lib_requirements(self, name, module):
        required = getattr(module, "PIP", None)
        if not required:
            return True
        if isinstance(required, (list, tuple)):
            required = {str(r): None for r in required}
        missing, outdated = Requirements.scan(required)
        if missing:
            self.log(f"LIB Error [{name}]: missing packages: {', '.join(missing)}", (255, 50, 50))
        for pkg, current, spec, verdict in outdated:
            self.log(f"LIB Error [{name}]: {pkg} {current} is {verdict} (needs {spec})", (255, 50, 50))
        return not missing and not outdated

    def load_libs(self):
        if not os.path.isdir(self.libs_dir):
            return
        abs_dir = os.path.abspath(self.libs_dir)
        if abs_dir not in sys.path:
            sys.path.append(abs_dir)
        found = []
        for entry in sorted(os.listdir(self.libs_dir)):
            if entry.startswith((".", "_")):
                continue
            full = os.path.join(self.libs_dir, entry)
            if os.path.isdir(full):
                init_file = os.path.join(full, "__init__.py")
                if not os.path.isfile(init_file):
                    self.log(f"I/O: Folder '{entry}' in libs has no __init__.py, ignored", (200, 150, 50))
                    continue
                found.append((entry, init_file, [os.path.abspath(full)], None))
            elif entry.endswith(".py"):
                if os.path.getsize(full) == 0:
                    self.log(f"I/O: Lib '{entry}' is empty, skipping", (255, 100, 50))
                    continue
                found.append((entry[:-3], full, None, None))
            elif entry.lower().endswith(".zip"):
                packed = self._read_zip_lib(entry, full)
                if packed is None:
                    continue
                found.append((entry[:-4], packed[1], packed[2], packed[0]))
            else:
                self.log(f"I/O: Unknown file type '{entry}' in libs ignored", (200, 150, 50))

        pending = {}
        for mod_name, path, locations, source in found:
            if any(i["mod_name"] == mod_name for i in self.libs.values()):
                continue
            m = self._import_lib(mod_name, path, locations, source)
            if m is None:
                continue
            lib_name = str(getattr(m, "NAME", mod_name))
            if lib_name in self.libs or lib_name in pending:
                self.log(f"LIB Error [{lib_name}]: duplicate library name", (255, 50, 50))
                self._forget(mod_name)
                continue
            lib_ver = str(getattr(m, "VERSION", "?"))
            spec = getattr(m, "ENGINE", None)
            verdict = Requirements.judge(ENGINE_VERSION, spec)
            if verdict:
                flip = {"too old": "too new", "too new": "too old"}.get(verdict, verdict)
                self.log(f"LIB Error [{lib_name}]: v{lib_ver} is {flip} for engine {ENGINE_VERSION} (needs engine {Requirements.pip_spec(spec)})", (255, 50, 50))
                self._forget(mod_name)
                continue
            if not self._check_lib_requirements(lib_name, m):
                self._forget(mod_name)
                continue
            reqs = [Requirements.split_req(r) for r in getattr(m, "REQUIRES", [])]
            pending[lib_name] = {
                "module": m,
                "mod_name": mod_name,
                "version": lib_ver,
                "requires": [r[0] for r in reqs],
                "specs": dict(reqs),
                "priority": getattr(m, "PRIORITY", 0),
                "loaded": False,
            }

        state = {}
        order = []

        def visit(n, stack):
            st = state.get(n)
            if st == "done":
                return True
            if st == "fail":
                return False
            if n in stack:
                self.log(f"LIB Error [{n}]: circular dependency", (255, 50, 50))
                state[n] = "fail"
                return False
            ok = True
            for dep in pending[n]["requires"]:
                spec = pending[n]["specs"].get(dep, "")
                done = self.libs.get(dep)
                fresh = not (done and done["loaded"])
                have = pending.get(dep) if fresh else done
                if have is None:
                    self.log(f"LIB Error [{n}]: missing dependency '{dep}{Requirements.pip_spec(spec)}'", (255, 50, 50))
                    ok = False
                    continue
                verdict = Requirements.judge(have["version"], spec)
                if verdict:
                    self.log(f"LIB Error [{n}]: dependency '{dep}' v{have['version']} is {verdict} (needs {Requirements.pip_spec(spec)})", (255, 50, 50))
                    ok = False
                elif fresh and not visit(dep, stack + [n]):
                    self.log(f"LIB Error [{n}]: dependency '{dep}' failed", (255, 50, 50))
                    ok = False
            state[n] = "done" if ok else "fail"
            if ok:
                order.append(n)
            return ok

        for n in sorted(pending, key=lambda x: (-pending[x]["priority"], x)):
            visit(n, [])

        loaded = 0
        for n in order:
            info = pending[n]
            if any(not self.libs.get(d, {}).get("loaded") for d in info["requires"]):
                self.log(f"LIB Error [{n}]: dependency failed to initialize", (255, 50, 50))
                continue
            self.libs[n] = info
            self._current_lib = n
            try:
                fn = getattr(info["module"], "init", None)
                if callable(fn):
                    fn(self)
                info["loaded"] = True
                self._lib_order.append(n)
                loaded += 1
                self.log(f"LIB: Loaded {n} v{info['version']}", (80, 255, 10))
            except Exception as e:
                self.unpatch_all(n)
                self._remove_added(n)
                self._drop_handlers(n)
                self.libs.pop(n, None)
                self._forget(info["mod_name"])
                self.log(f"LIB Error [{n}]: init failed ({e})", (255, 50, 50))
                traceback.print_exc()
            finally:
                self._current_lib = None
        if found:
            self.log(f"LIBS: {loaded}/{len(found)} loaded", (150, 255, 255))

    def _drop_handlers(self, owner):
        self._join_tasks()
        self._tasks = [t for t in self._tasks if t["owner"] != owner]
        for name in list(self.events):
            self.events[name] = [s for s in self.events[name] if s.get("owner") != owner]

    def unload_lib(self, name):
        info = self.libs.get(name)
        if not info:
            return False
        for other, oi in list(self.libs.items()):
            if name in oi["requires"] and oi["loaded"]:
                self.unload_lib(other)
        self._current_lib = name
        try:
            fn = getattr(info["module"], "shutdown", None)
            if callable(fn):
                fn(self)
        except Exception as e:
            self.log(f"LIB Error [{name}]: shutdown failed ({e})", (255, 50, 50))
        finally:
            self._current_lib = None
        self.unpatch_all(name)
        self._remove_added(name)
        self._drop_handlers(name)
        self.libs.pop(name, None)
        if name in self._lib_order:
            self._lib_order.remove(name)
        self._forget(info["mod_name"])
        return True

    def unload_libs(self):
        for n in reversed(list(self._lib_order)):
            if n in self.libs:
                self.unload_lib(n)

    def load_mods(self):
        if not os.path.isdir(self.mods_dir):
            return
        for fn in sorted(os.listdir(self.mods_dir)):
            full_path = os.path.join(self.mods_dir, fn)
            if not fn.endswith(".py"):
                self.log(f"I/O: Unknown file type '{fn}' ignored", (200, 150, 50))
                continue
            if os.path.getsize(full_path) == 0:
                self.log(f"I/O: Mod '{fn}' is empty, skipping", (255, 100, 50))
                continue
            name = fn[:-3]
            try:
                spec = importlib.util.spec_from_file_location(name, full_path)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                if hasattr(m, "init"):
                    m.init(self)
                self.log(f"MOD: Injected {name}", (80, 255, 10))
            except Exception as e:
                self.log(f"MOD Error [{name}]: {e}", (255, 50, 50))
                traceback.print_exc()

    def render_ui(self):
        if not self.cfg.get("debug", True):
            return
        w, h = self.screen_size
        z = self.CON_SCALE
        n = int((h - 10 * z) // (9 * z))
        if w <= 0 or n <= 0:
            return
        if getattr(self, "_con", None) is None:
            f = np.frombuffer(zlib.decompress(base64.b85decode("".join(self.CON_FONT))), np.uint8)
            bits = np.unpackbits(f.reshape(95, 8, 1), axis=2, bitorder="little") * 255
            tex = self.ctx.texture((8, 760), 1, bits.astype(np.uint8).tobytes())
            prog = self.ctx.program(
                vertex_shader="""#version 330
                uniform vec2 screen;
                uniform float s;
                in vec2 p; in float g; in vec3 c;
                out vec2 l; flat out float v_g; out vec3 v_c;
                void main() {
                    vec2 k = vec2(gl_VertexID & 1, gl_VertexID >> 1);
                    vec2 px = (vec2(10.0) + p * vec2(8.0, 9.0) + k * 8.0) * s;
                    gl_Position = vec4(px / screen * vec2(2.0, -2.0) + vec2(-1.0, 1.0), 0.0, 1.0);
                    l = k * 8.0; v_g = g; v_c = c;
                }""",
                fragment_shader="""#version 330
                uniform sampler2D f;
                in vec2 l; flat in float v_g; in vec3 v_c; out vec4 o;
                void main() {
                    vec2 q = clamp(l, 0.5, 7.5);
                    o = vec4(v_c, texture(f, vec2(q.x, v_g * 8.0 + q.y) / vec2(8.0, 760.0)).r);
                }""",
            )
            buf = self.ctx.buffer(reserve=6 * 4 * 8192)
            self._con = (tex, prog, buf, self.ctx.vertex_array(prog, [(buf, "2f 1f 3f/i", "p", "g", "c")]))
        tex, prog, buf, vao = self._con
        cols = int((w - 20 * z) // (8 * z))
        parts = []
        for i, (text, color) in enumerate(self.logs[-n:]):
            b = np.frombuffer(text.encode("ascii", "replace")[:cols], np.uint8)
            parts.append(np.column_stack([np.arange(len(b)), np.full(len(b), i), np.clip(b, 32, 127) - 32,
                                          np.tile(np.array(color) / 255.0, (len(b), 1))]))
        if not parts:
            return
        data = np.vstack(parts).astype("f4")[:8192]
        buf.write(data.tobytes())
        self.ctx.screen.use()
        self.ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.ctx.enable(moderngl.BLEND)
        tex.use(0)
        prog["screen"].value = (float(w), float(h))
        prog["s"].value = z
        vao.render(moderngl.TRIANGLE_STRIP, vertices=4, instances=len(data))
        self.ctx.disable(moderngl.BLEND)

    def run(self):
        self.load_mods()
        fps_cap = max(0, int(self.cfg_num("fps", 60)))
        vsync = bool(self.cfg.get("vsync", True))
        max_dt = float(self.cfg_num("max_dt", 0.25))
        clear = tuple(c / 255.0 for c in self.cfg_color("clear_color", (10, 10, 15)))
        last = time.perf_counter()
        self.emit("start")
        try:
            while self.state["running"] and not glfw.window_should_close(self.window):
                self._join_tasks()
                glfw.poll_events()
                self._drain()
                now = time.perf_counter()
                dt = min(now - last, max_dt)
                last = now
                self.state["dt"] = dt
                self.state["time"] += dt
                self.frame += 1
                self.state["frame"] = self.frame
                self.emit("update")
                self._start_tasks()
                if self.screen_size[0] > 0 and self.screen_size[1] > 0:
                    self.ctx.screen.use()
                    self.ctx.clear(*clear)
                    self.emit("draw")
                    self.render_ui()
                glfw.swap_buffers(self.window)
                if fps_cap and not vsync:
                    spare = 1.0 / fps_cap - (time.perf_counter() - now)
                    if spare > 0:
                        time.sleep(spare)
        finally:
            self._join_tasks()
            self.emit("shutdown")
            self.unload_libs()
            self.release_textures()
            if self.pool is not None:
                self.pool.shutdown(wait=False, cancel_futures=True)
            if self.ctx is not None:
                self.ctx.release()
            if self.window is not None:
                glfw.destroy_window(self.window)
            glfw.terminate()


if __name__ == "__main__":
    SDKEngine().run()