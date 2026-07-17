import sys
import os
import importlib.util
import datetime
import traceback

_BOOT_TIME = datetime.datetime.now()

_CON_COLORS = {
    "cyan":    "\033[96m",
    "green":   "\033[92m",
    "yellow":  "\033[93m",
    "red":     "\033[91m",
    "magenta": "\033[95m",
    "blue":    "\033[94m",
    "white":   "\033[97m",
    "gray":    "\033[90m",
    "reset":   "\033[0m",
    "bold":    "\033[1m",
}

def _cprint(text, color="white", bold=False):
    prefix = _CON_COLORS.get("bold", "") if bold else ""
    col = _CON_COLORS.get(color, "")
    rst = _CON_COLORS["reset"]
    print(f"{prefix}{col}{text}{rst}")

def _divider(char="─", length=72, color="gray"):
    _cprint(char * length, color)

def _section(label, color="cyan"):
    _divider()
    _cprint(f"  {label}", color, bold=True)
    _divider()

def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

def _elapsed():
    delta = datetime.datetime.now() - _BOOT_TIME
    return f"{delta.total_seconds():.3f}s"

def _log_raw(level, text, color="white"):
    ts = _ts()
    print(f"{_CON_COLORS['gray']}[{ts}]{_CON_COLORS['reset']} {_CON_COLORS.get(color,'')}{_CON_COLORS.get('bold','') if level in ('CRIT','ERR') else ''}{level:<6}{_CON_COLORS['reset']} {text}")

_section("SDK-Engine v1.4.0  —  BOOT SEQUENCE", "cyan")
_log_raw("INIT", "Python interpreter started", "green")
_log_raw("INIT", f"Python version : {sys.version.split()[0]}", "green")
_log_raw("INIT", f"Platform       : {sys.platform}", "green")
_log_raw("INIT", f"Working dir    : {os.getcwd()}", "green")
_log_raw("INIT", f"Script path    : {os.path.abspath(__file__)}", "green")

_section("DEPENDENCY CHECK", "yellow")
_REQUIRED_LIBS = {
    "pygame":  "pip install pygame",
    "numpy":   "pip install numpy",
    "pymunk":  "pip install pymunk",
}
_missing = []
for _lib, _fix in _REQUIRED_LIBS.items():
    spec = importlib.util.find_spec(_lib)
    if spec is None:
        _log_raw("MISS", f"Library '{_lib}' NOT found", "red")
        _log_raw("FIX ", f"Run: {_fix}", "yellow")
        _missing.append(_lib)
    else:
        _log_raw("OK  ", f"Library '{_lib}' found at {spec.origin}", "green")

if _missing:
    _divider("═", color="red")
    _cprint("  FATAL: Missing required libraries. Cannot start engine.", "red", bold=True)
    _cprint(f"  Missing: {', '.join(_missing)}", "red")
    _cprint("  Install all missing libs with:", "yellow")
    _cprint(f"    pip install {' '.join(_missing)}", "white", bold=True)
    _divider("═", color="red")
    _cprint("Press ENTER to exit...", "gray")
    input()
    sys.exit(1)

_log_raw("OK  ", "All dependencies satisfied", "green")

import pygame
import math
import socket
import threading
import json
import numpy as np
import pymunk
import random
import weakref

_log_raw("INIT", "All modules imported successfully", "green")
_log_raw("INIT", f"pygame  v{pygame.version.ver}", "cyan")
_log_raw("INIT", f"numpy   v{np.__version__}", "cyan")
_log_raw("INIT", f"pymunk  v{pymunk.version}", "cyan")


class ResourceManager:
    def __init__(self):
        self.images = {}
        self.anims = {}
        self.engine = None
        self._missing = set()

    def load_img(self, name, path, scale=None):
        if name in self.images:
            if self.engine:
                self.engine.log(f"RES: Image '{name}' already loaded, skipping duplicate", (200, 200, 100))
            return
        resolved_path = None
        target_file = os.path.basename(path)
        if os.path.exists("assets"):
            for root, dirs, files in os.walk("assets"):
                if target_file in files:
                    resolved_path = os.path.join(root, target_file)
                    break
        if not resolved_path and os.path.exists(path):
            resolved_path = path
        if not resolved_path:
            if self.engine:
                self.engine.log(f"RES WARN: Asset not found: '{path}'", (255, 150, 50))
                self.engine.log(f"RES HINT: Place image in 'assets/' folder as '{target_file}'", (200, 150, 50))
            return
        try:
            img = pygame.image.load(resolved_path).convert_alpha()
            if scale:
                is_smooth = self.engine.cfg.get("smoothing", False) if self.engine else False
                method = "smoothscale" if is_smooth else "scale"
                if is_smooth:
                    img = pygame.transform.smoothscale(img, scale)
                else:
                    img = pygame.transform.scale(img, scale)
                if self.engine:
                    self.engine.log(f"RES: Loaded '{name}' from '{resolved_path}' scaled to {scale} via {method}", (150, 255, 150))
            else:
                if self.engine:
                    self.engine.log(f"RES: Loaded '{name}' from '{resolved_path}' size {img.get_size()}", (150, 255, 150))
            self.images[name] = img
        except Exception as e:
            if self.engine:
                self.engine.log(f"RES ERR: Failed to load '{path}': {e}", (255, 50, 50))
                self.engine.log(f"RES HINT: Check file format (PNG/JPG/BMP/GIF supported), file may be corrupt", (255, 100, 50))

    def load_ui(self, name):
        target = f"{name}.json"
        path = None
        if os.path.exists("assets"):
            for root, _, files in os.walk("assets"):
                if target in files:
                    path = os.path.join(root, target)
                    break
        if not path:
            if self.engine:
                self.engine.log(f"RES WARN: UI file '{target}' not found in assets/", (255, 150, 50))
                self.engine.log(f"RES HINT: Create '{target}' inside the 'assets/' folder", (200, 150, 50))
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if self.engine:
                self.engine.log(f"RES: Loaded UI layout '{name}' from '{path}'", (150, 255, 150))
            return data
        except json.JSONDecodeError as e:
            if self.engine:
                self.engine.log(f"RES ERR: Invalid JSON in '{path}': {e}", (255, 50, 50))
                self.engine.log(f"RES HINT: Validate JSON at jsonlint.com — check line {e.lineno}", (255, 100, 50))
        except Exception as e:
            if self.engine:
                self.engine.log(f"RES ERR: Could not read '{path}': {e}", (255, 50, 50))
        return None


class SDKEngine:
    def __init__(self):
        self.logs = []
        self.max_logs = 40
        self.cache_dir = "cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        log_filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.current_log_file = os.path.join(self.cache_dir, log_filename)

        _section("ENGINE INIT", "magenta")
        self.log("SDK-Engine v1.4.0 boot started", (150, 255, 255))
        self.log(f"Log file: {self.current_log_file}", (150, 200, 255))

        self.log("ENV: Setting up directory structure...", (200, 200, 255))
        self.setup_env()

        self.log("CFG: Loading config.cfg...", (200, 200, 255))
        self.cfg = self.load_cfg("config.cfg")

        self.log("CFG: Validating configuration keys...", (200, 200, 255))
        self.validate_cfg()

        self.events = {}

        self.log("SDL: Initializing pygame subsystems...", (200, 200, 255))
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.log("SDL: pygame.init() OK", (100, 255, 100))
        self.log("SDL: pygame.mixer.init() — 44100Hz, 16bit, stereo, buffer=512", (100, 255, 100))

        self.is_fullscreen = False
        self.window_mode_size = (self.cfg.get("width", 800), self.cfg.get("height", 600))
        win_title = self.cfg.get("title", "SDK-Engine")

        self.log(f"WIN: Creating window {self.window_mode_size[0]}x{self.window_mode_size[1]} title='{win_title}'", (200, 200, 255))
        self.set_window(self.window_mode_size[0], self.window_mode_size[1], win_title, pygame.RESIZABLE)
        self.log("WIN: Window created successfully. F11 = toggle fullscreen, resize supported.", (100, 255, 100))

        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 16)
        self.log("FONT: Loaded 'Consolas' 16pt system font", (150, 255, 200))

        gravity_val = self.cfg.get("gravity", 900)
        self.physics_space = pymunk.Space()
        self.physics_space.gravity = (0, gravity_val)
        self.log(f"PHYS: pymunk.Space created, gravity=(0, {gravity_val})", (150, 200, 255))

        self.audio = {
            "sounds": {},
            "load": self.load_sound,
            "play": self.play_sound,
            "generate": self.generate_sound
        }
        self.log("AUDIO: Audio subsystem ready", (150, 200, 255))

        self.log("RES: Initializing ResourceManager...", (200, 200, 255))
        self.resources = ResourceManager()
        self.resources.engine = self

        from mods._lib_camera import Camera
        self.log("LIB: _lib_camera.Camera loaded", (80, 200, 255))
        self.camera = Camera(self.window_mode_size[0], self.window_mode_size[1])

        from mods._lib_objects import ObjectManager
        self.log("LIB: _lib_objects.ObjectManager loaded", (80, 200, 255))
        self.objects = ObjectManager(self)

        from mods._lib_ui import UIManager
        self.log("LIB: _lib_ui.UIManager loaded", (80, 200, 255))
        self.ui = UIManager(self)

        from mods._lib_input import InputManager
        self.log("LIB: _lib_input.InputManager loaded", (80, 200, 255))
        self.input = InputManager()

        self.state = {
            "running": True,
            "cfg": self.cfg,
            "dt": 0.0,
            "time": 0.0,
            "shared": {},
            "screen": self.screen,
            "net": {"socket": None, "clients": {}, "is_server": False},
            "physics": self.physics_space,
            "audio": self.audio,
            "objects": self.objects,
            "ui": self.ui,
            "resources": self.resources,
            "camera": self.camera,
            "input": self.input
        }
        self.log("STATE: Engine state dict initialized", (150, 255, 200))

        self.math = {
            "lerp":       lambda a, b, t: a + (b - a) * t,
            "dist":       lambda x1, y1, x2, y2: math.sqrt((x2-x1)**2 + (y2-y1)**2),
            "angle":      lambda x1, y1, x2, y2: math.atan2(y2-y1, x2-x1),
            "sin_wave":   lambda amp, freq, t: amp * math.sin(freq * t),
            "trajectory": lambda x0, y0, v, ang, t, g=900: (x0 + v*math.cos(ang)*t, y0 + v*math.sin(ang)*t + 0.5*g*t**2),
            "exp_decay":  lambda a, b, decay, dt: b + (a - b) * math.exp(-decay * dt)
        }
        self.log("MATH: Math utility dict built (lerp, dist, angle, sin_wave, trajectory, exp_decay)", (150, 255, 200))

        self.on("update", lambda s: self.camera.update(s["dt"]), priority=100)
        self.on("update", lambda s: self.objects.update(s["dt"]))
        self.on("update", lambda s: self.ui.update(s["dt"]))
        self.on("draw",   lambda s: self.objects.draw(s["screen"], s["camera"], s["resources"]))
        self.on("draw",   lambda s: self.ui.draw(s["screen"]))
        self.log("EVENTS: Core update/draw listeners registered", (150, 255, 200))

        _divider("═", color="cyan")
        self.log(f"ENGINE READY — elapsed {_elapsed()}", (0, 255, 200))
        _divider("═", color="cyan")

    def validate_cfg(self):
        required = {
            "width": 800, "height": 600, "fps": 60, "gravity": 900,
            "title": "SDK-Engine", "debug": True, "smoothing": False
        }
        needs_save = False
        for k, v in required.items():
            if k not in self.cfg:
                self.log(f"CFG WARN: Missing key '{k}' — default={v}", (255, 255, 50))
                self.log(f"CFG HINT: Add  '{k} = {v}'  to config.cfg to silence this warning", (200, 200, 50))
                self.cfg[k] = v
                needs_save = True
            else:
                self.log(f"CFG OK: {k} = {self.cfg[k]}", (150, 255, 150))
        if needs_save:
            self.log("CFG: Saving updated config with defaults...", (200, 200, 255))
            self.save_cfg()

    def set_window(self, w, h, title=None, flags=0):
        if title is None:
            title = self.cfg.get("title", "SDK-Engine")
        self.screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption(title)
        if hasattr(self, 'state'):
            self.state["screen"] = self.screen
        self.log(f"WIN: Resized to {w}x{h}, title='{title}', flags={flags}", (200, 255, 200))

    def log(self, text, color=(255, 255, 255)):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_string = f"[{timestamp}] {text}"
        self.logs.append((log_string, color))
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        level = "INFO"
        con_color = "white"
        tl = text.upper()
        if any(x in tl for x in ("ERR", "FATAL", "CRIT")):
            level = "ERR "
            con_color = "red"
        elif any(x in tl for x in ("WARN", "MISS")):
            level = "WARN"
            con_color = "yellow"
        elif any(x in tl for x in ("HINT", "FIX")):
            level = "HINT"
            con_color = "magenta"
        elif any(x in tl for x in ("OK", "READY", "LOADED", "DONE")):
            level = "OK  "
            con_color = "green"
        elif any(x in tl for x in ("LOADING", "INIT", "BOOT")):
            level = "INIT"
            con_color = "cyan"
        _log_raw(level, text, con_color)
        try:
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(log_string + "\n")
        except Exception:
            pass

    def setup_env(self):
        dirs = ["mods", "assets", "cache"]
        for d in dirs:
            if not os.path.exists(d):
                os.makedirs(d)
                self.log(f"ENV: Created directory '{d}/'", (100, 255, 100))
            else:
                self.log(f"ENV: Directory '{d}/' exists OK", (150, 200, 150))
        if not os.path.exists("config.cfg"):
            with open("config.cfg", "w") as f:
                f.write("debug = true\nwidth = 800\nheight = 600\nfps = 60\ngravity = 900\ntitle = SDK-Engine\nsmoothing = false\n")
            self.log("ENV: config.cfg not found — generated default config", (100, 255, 100))
        else:
            self.log("ENV: config.cfg found", (150, 200, 150))

    def load_cfg(self, path):
        d = {}
        try:
            with open(path, "r") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        self.log(f"CFG WARN: Line {lineno} has no '=' separator: '{line}'", (255, 200, 50))
                        self.log(f"CFG HINT: Format must be 'key = value' (e.g. fps = 60)", (200, 180, 50))
                        continue
                    k, v = [x.strip() for x in line.split("=", 1)]
                    k = k.lower()
                    if not k:
                        self.log(f"CFG WARN: Empty key on line {lineno}", (255, 200, 50))
                        continue
                    orig_v = v
                    if v.lower() in ["true", "false"]:
                        v = v.lower() == "true"
                    else:
                        try:
                            v = float(v) if "." in v else int(v)
                        except ValueError:
                            pass
                    d[k] = v
                    self.log(f"CFG: Read  {k} = {v!r}  (raw: '{orig_v}')", (180, 220, 180))
            self.log(f"CFG: Loaded {len(d)} keys from '{path}'", (100, 255, 100))
        except FileNotFoundError:
            self.log(f"CFG ERR: File '{path}' not found", (255, 50, 50))
            self.log(f"CFG HINT: Run setup_env() first or create config.cfg manually", (255, 100, 50))
        except Exception as e:
            self.log(f"CFG ERR: Unexpected error reading '{path}': {e}", (255, 50, 50))
        return d

    def save_cfg(self):
        try:
            with open("config.cfg", "w") as f:
                for k, v in self.cfg.items():
                    if isinstance(v, bool):
                        f.write(f"{k} = {'true' if v else 'false'}\n")
                    else:
                        f.write(f"{k} = {v}\n")
            self.log(f"CFG: Saved {len(self.cfg)} keys to config.cfg", (100, 255, 100))
        except PermissionError:
            self.log("CFG ERR: Permission denied writing config.cfg", (255, 50, 50))
            self.log("CFG HINT: Check file is not read-only or open in another program", (255, 100, 50))
        except Exception as e:
            self.log(f"CFG ERR: Save failed: {e}", (255, 50, 50))

    def load_sound(self, name, path):
        try:
            if not os.path.exists(path):
                self.log(f"AUDIO WARN: Sound file not found: '{path}'", (255, 150, 50))
                self.log(f"AUDIO HINT: Place sound file at '{path}' (WAV/OGG recommended)", (200, 150, 50))
                return
            sound = pygame.mixer.Sound(path)
            self.audio["sounds"][name] = sound
            self.log(f"AUDIO: Loaded sound '{name}' from '{path}'", (150, 255, 150))
        except pygame.error as e:
            self.log(f"AUDIO ERR: pygame failed loading '{path}': {e}", (255, 50, 50))
            self.log(f"AUDIO HINT: Supported formats: WAV, OGG. MP3 may need extra codec.", (255, 100, 50))
        except Exception as e:
            self.log(f"AUDIO ERR: {e}", (255, 50, 50))

    def play_sound(self, name, volume=1.0):
        if name not in self.audio["sounds"]:
            self.log(f"AUDIO WARN: Sound '{name}' not loaded, cannot play", (255, 150, 50))
            self.log(f"AUDIO HINT: Call engine.load_sound('{name}', 'path/to/file') first", (200, 150, 50))
            return
        sound = self.audio["sounds"][name]
        sound.set_volume(max(0.0, min(1.0, volume)))
        sound.play()

    def generate_sound(self, name, freq=440, duration=0.5, volume=0.5, wave_type="sine"):
        try:
            sample_rate = 44100
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            if wave_type == "sine":
                wave = np.sin(freq * t * 2 * np.pi)
            elif wave_type == "square":
                wave = np.sign(np.sin(freq * t * 2 * np.pi))
            elif wave_type == "sawtooth":
                wave = 2 * (t * freq - np.floor(0.5 + t * freq))
            else:
                self.log(f"AUDIO WARN: Unknown wave_type '{wave_type}', using sine", (255, 200, 50))
                self.log(f"AUDIO HINT: Valid wave types: 'sine', 'square', 'sawtooth'", (200, 180, 50))
                wave = np.sin(freq * t * 2 * np.pi)
            sound_array = np.zeros((len(wave), 2), dtype=np.int16)
            sound_array[:, 0] = wave * volume * 32767
            sound_array[:, 1] = wave * volume * 32767
            sound = pygame.sndarray.make_sound(sound_array)
            self.audio["sounds"][name] = sound
            self.log(f"AUDIO: Generated '{name}' freq={freq}Hz dur={duration}s vol={volume} wave={wave_type}", (150, 255, 200))
            return sound
        except Exception as e:
            self.log(f"AUDIO ERR: generate_sound failed: {e}", (255, 50, 50))
            self.log(f"AUDIO HINT: Ensure numpy and pygame.sndarray are available", (255, 100, 50))

    def on(self, name, func, priority=0, once=False):
        if name not in self.events:
            self.events[name] = []
        self.events[name].append({"func": func, "prio": priority, "once": once})
        self.events[name].sort(key=lambda x: x["prio"], reverse=True)

    def emit(self, name, data=None):
        if name in self.events:
            to_remove = []
            for sub in self.events[name].copy():
                try:
                    sub["func"](data if data is not None else self.state)
                    if sub["once"]:
                        to_remove.append(sub)
                except Exception as e:
                    tb = traceback.format_exc()
                    self.log(f"EVENT ERR: Handler for '{name}' raised: {e}", (255, 80, 80))
                    self.log(f"EVENT HINT: Check the mod that subscribed to '{name}'", (200, 100, 80))
                    for line in tb.strip().splitlines()[-4:]:
                        self.log(f"  TRACE: {line.strip()}", (200, 100, 80))
                    to_remove.append(sub)
            for sub in to_remove:
                if sub in self.events[name]:
                    self.events[name].remove(sub)

    def load_mods(self):
        if not os.path.exists("mods"):
            self.log("MODS WARN: 'mods/' directory missing, nothing to load", (255, 200, 50))
            self.log("MODS HINT: Run setup_env() or create 'mods/' manually", (200, 180, 50))
            return

        _section("MOD LOADER", "green")
        all_files = os.listdir("mods")
        py_files = [f for f in all_files if f.endswith(".py") and not f.startswith("_lib_")]
        lib_files = [f for f in all_files if f.startswith("_lib_") and f.endswith(".py")]
        ignored = [f for f in all_files if not f.endswith(".py")]

        self.log(f"MODS: Found {len(all_files)} files in mods/ ({len(lib_files)} libs, {len(py_files)} mods, {len(ignored)} ignored)", (200, 200, 255))

        if ignored:
            for f in ignored:
                self.log(f"MODS SKIP: '{f}' — not a .py file, ignored", (200, 150, 50))
                self.log(f"MODS HINT: Only .py files are loaded as mods", (180, 130, 50))

        if lib_files:
            self.log(f"MODS: Library files (auto-loaded at engine init):", (150, 200, 255))
            for f in sorted(lib_files):
                self.log(f"MODS LIB:  {f}", (100, 180, 255))

        if not py_files:
            self.log("MODS: No user mods found in 'mods/'", (200, 200, 150))
            self.log("MODS HINT: Place .py mod files in 'mods/' with an init(engine) function", (180, 180, 130))
            return

        self.log(f"MODS: Loading {len(py_files)} mod(s)...", (200, 255, 200))
        loaded = 0
        failed = 0

        for fn in sorted(py_files):
            full_path = os.path.join("mods", fn)
            name = fn[:-3]
            _divider("·", 40, "gray")
            self.log(f"MODS: Loading '{fn}'...", (200, 230, 255))

            try:
                file_size = os.path.getsize(full_path)
            except Exception:
                file_size = -1

            if file_size == 0:
                self.log(f"MODS SKIP: '{fn}' is empty (0 bytes)", (255, 100, 50))
                self.log(f"MODS HINT: Add code to '{fn}' and define init(engine) function", (200, 100, 50))
                failed += 1
                continue

            self.log(f"MODS:   Path : {full_path}", (150, 180, 200))
            self.log(f"MODS:   Size : {file_size} bytes", (150, 180, 200))

            try:
                spec = importlib.util.spec_from_file_location(name, full_path)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)

                has_init = hasattr(m, "init")
                self.log(f"MODS:   Has init() : {'YES' if has_init else 'NO (mod loaded but init() not called)'}", (150, 220, 150) if has_init else (255, 200, 50))
                if not has_init:
                    self.log(f"MODS HINT: Define 'def init(engine):' in '{fn}' to hook into engine", (200, 180, 50))

                if has_init:
                    m.init(self)

                self.log(f"MODS OK: '{name}' injected successfully", (80, 255, 10))
                loaded += 1

            except SyntaxError as e:
                self.log(f"MODS ERR [{name}]: Syntax error — {e}", (255, 50, 50))
                self.log(f"MODS HINT: Open '{fn}' and fix line {e.lineno}: {e.msg}", (255, 100, 50))
                failed += 1
            except ImportError as e:
                self.log(f"MODS ERR [{name}]: ImportError — {e}", (255, 50, 50))
                self.log(f"MODS HINT: The mod imports a missing library. Install it with pip.", (255, 100, 50))
                failed += 1
            except AttributeError as e:
                self.log(f"MODS ERR [{name}]: AttributeError — {e}", (255, 50, 50))
                self.log(f"MODS HINT: Mod tried to access engine attribute that doesn't exist. Check API.", (255, 100, 50))
                failed += 1
            except Exception as e:
                tb = traceback.format_exc()
                self.log(f"MODS ERR [{name}]: {type(e).__name__} — {e}", (255, 50, 50))
                for line in tb.strip().splitlines()[-5:]:
                    self.log(f"  TRACE: {line.strip()}", (200, 80, 80))
                self.log(f"MODS HINT: Check '{fn}' for runtime errors in init() function", (255, 100, 50))
                failed += 1

        _divider("─", color="gray")
        total = loaded + failed
        self.log(f"MODS: Done — {loaded}/{total} loaded OK, {failed}/{total} failed", (100, 255, 100) if failed == 0 else (255, 200, 50))
        if failed > 0:
            self.log(f"MODS HINT: Check errors above — fix issues in failing mods or remove them", (255, 180, 50))

    def render_ui(self):
        if not self.cfg.get("debug", True):
            return
        for i, (txt, col) in enumerate(self.logs):
            self.screen.blit(self.font.render(txt, True, col), (10, 10 + i * 18))

    def _ui_dispatch_input_click(self, mpos):
        from mods._lib_ui import UIInput
        def walk(el):
            if not el.visible:
                return
            if isinstance(el, UIInput):
                pos = el.get_real_pos()
                sz = el.size * el.scale_val
                if pygame.Rect(pos.x, pos.y, sz.x, sz.y).collidepoint(mpos.x, mpos.y):
                    el.activate()
                else:
                    el.deactivate()
            for child in el.children:
                walk(child)
        for root in self.ui.roots.values():
            walk(root)

    def _ui_dispatch_input_event(self, event):
        from mods._lib_ui import UIInput
        def walk(el):
            if isinstance(el, UIInput) and el._active:
                el.handle_event(event)
            for child in el.children:
                walk(child)
        for root in self.ui.roots.values():
            walk(root)

    def _ui_dispatch_click(self, element, mpos):
        from mods._lib_ui import UIInput
        if not element.visible:
            return False
        pos = element.get_real_pos()
        sz = element.size * element.scale_val
        if not pygame.Rect(pos.x, pos.y, sz.x, sz.y).collidepoint(mpos.x, mpos.y):
            return False
        for child in reversed(element.children):
            if self._ui_dispatch_click(child, mpos):
                return True
        if element.on_click and not isinstance(element, UIInput):
            element.on_click()
            return True
        return bool(isinstance(element, UIInput))

    def run(self):
        self.load_mods()
        _section("MAIN LOOP", "cyan")
        self.log(f"LOOP: Starting game loop — FPS cap={self.cfg.get('fps', 60)}", (150, 255, 255))
        self.log(f"LOOP: Physics substeps=2 per frame", (150, 200, 255))
        self.log(f"LOOP: F11 = fullscreen toggle | Close window = quit", (150, 200, 255))

        physics_steps = 2
        fps_cap = self.cfg.get("fps", 60)
        fixed_dt = 1.0 / fps_cap
        step_dt = fixed_dt / physics_steps

        frame_count = 0
        fps_log_timer = 0.0

        while self.state["running"]:
            raw_dt = self.clock.tick(fps_cap) / 1000.0
            self.state["dt"] = raw_dt
            self.state["time"] += raw_dt

            fps_log_timer += raw_dt
            frame_count += 1
            if fps_log_timer >= 5.0:
                actual_fps = self.clock.get_fps()
                self.log(f"LOOP: FPS={actual_fps:.1f} | frames={frame_count} | time={self.state['time']:.1f}s | objs={len(self.objects.loose_objs)}", (100, 200, 255))
                fps_log_timer = 0.0

            for _ in range(physics_steps):
                self.physics_space.step(step_dt)

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.log("LOOP: Quit event received — shutting down", (255, 200, 50))
                    self.state["running"] = False

                elif e.type == pygame.VIDEORESIZE:
                    if not self.is_fullscreen:
                        self.window_mode_size = (e.w, e.h)
                        self.screen = pygame.display.set_mode((e.w, e.h), pygame.RESIZABLE)
                        self.state["screen"] = self.screen
                        self.camera.size = pygame.math.Vector2(e.w, e.h)
                        self.log(f"WIN: Resized to {e.w}x{e.h}", (200, 200, 255))

                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F11:
                        self.is_fullscreen = not self.is_fullscreen
                        if self.is_fullscreen:
                            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                            w, h = self.screen.get_size()
                            self.log(f"WIN: Fullscreen ON — native res {w}x{h}", (200, 255, 200))
                        else:
                            self.screen = pygame.display.set_mode(self.window_mode_size, pygame.RESIZABLE)
                            self.log(f"WIN: Fullscreen OFF — back to {self.window_mode_size}", (200, 255, 200))
                        self.state["screen"] = self.screen
                        self.camera.size = pygame.math.Vector2(self.screen.get_width(), self.screen.get_height())
                    self._ui_dispatch_input_event(e)

                elif e.type == pygame.MOUSEBUTTONDOWN:
                    mpos = pygame.math.Vector2(e.pos)
                    for root in self.ui.roots.values():
                        self._ui_dispatch_click(root, mpos)
                    self._ui_dispatch_input_click(mpos)

                self.emit("event", e)

            self.input.update(self.camera.offset)
            self.emit("update")
            self.screen.fill((10, 10, 15))
            self.emit("draw")
            self.render_ui()
            pygame.display.flip()

        _section("SHUTDOWN", "yellow")
        self.log("LOOP: Main loop exited cleanly", (255, 200, 50))
        self.log(f"LOOP: Total frames rendered: {frame_count}", (200, 200, 255))
        self.log(f"LOOP: Total time: {self.state['time']:.2f}s", (200, 200, 255))
        self.log("SDL: Calling pygame.quit()", (200, 200, 255))
        pygame.quit()
        _cprint("  Engine shutdown complete.", "green", bold=True)
        _divider("═", color="green")


if __name__ == "__main__":
    try:
        SDKEngine().run()
    except KeyboardInterrupt:
        _cprint("\n[INTERRUPT] KeyboardInterrupt — forced exit.", "yellow")
        sys.exit(0)
    except Exception as e:
        _divider("═", color="red")
        _cprint("  UNHANDLED EXCEPTION IN MAIN", "red", bold=True)
        _cprint(f"  {type(e).__name__}: {e}", "red")
        _divider("─", color="red")
        traceback.print_exc()
        _divider("═", color="red")
        _cprint("Press ENTER to exit...", "gray")
        input()
        sys.exit(1)