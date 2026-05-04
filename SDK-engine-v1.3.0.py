import sys
import os

_miss = []
for _m in ["pygame", "pymunk", "numpy"]:
    try: __import__(_m)
    except: _miss.append(_m)
if _miss:
    print(f"ОШИБКА: Отсутствуют библиотеки -> {', '.join(_miss)}")
    print(f"Для установки введите: pip install {' '.join(_miss)}")
    print("Нажмите любую клавишу для выхода...")
    try:
        if os.name == 'nt': 
            import msvcrt; msvcrt.getch()
        else: 
            import tty, termios; fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setraw(fd); sys.stdin.read(1); termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except: input()
    sys.exit()

import pygame
import importlib.util
import datetime
import math
import socket
import threading
import json
import numpy as np
import pymunk
import random

class InputManager:
    def __init__(self):
        self.keys = []
        self.keys_prev = []
        self.mouse = [False] * 5
        self.mouse_prev = [False] * 5
        self.mouse_pos = pygame.math.Vector2(0, 0)
        self.world_mouse_pos = pygame.math.Vector2(0, 0)

    def update(self, camera_offset=None):
        self.keys_prev = list(self.keys) if self.keys else []
        self.keys = pygame.key.get_pressed()
        self.mouse_prev = list(self.mouse)
        self.mouse = pygame.mouse.get_pressed(num_buttons=5)
        self.mouse_pos = pygame.math.Vector2(pygame.mouse.get_pos())
        if camera_offset: self.world_mouse_pos = self.mouse_pos + camera_offset
        else: self.world_mouse_pos = pygame.math.Vector2(self.mouse_pos)

    def key(self, k): return self.keys[k] if self.keys else False
    def key_down(self, k): return self.keys[k] and not self.keys_prev[k] if self.keys and self.keys_prev else False
    def key_up(self, k): return not self.keys[k] and self.keys_prev[k] if self.keys and self.keys_prev else False
    def mouse_btn(self, b): return self.mouse[b]
    def mouse_down(self, b): return self.mouse[b] and not self.mouse_prev[b]
    def mouse_up(self, b): return not self.mouse[b] and self.mouse_prev[b]

class ResourceManager:
    def __init__(self):
        self.images = {}
        self.anims = {}

    def load_img(self, name, path, scale=None):
        img = pygame.image.load(path).convert_alpha()
        if scale: img = pygame.transform.scale(img, scale)
        self.images[name] = img

    def load_gif_folder(self, name, path, delay=0.1, scale=None):
        frames = []
        for f in sorted(os.listdir(path)):
            img = pygame.image.load(os.path.join(path, f)).convert_alpha()
            if scale: img = pygame.transform.scale(img, scale)
            frames.append(img)
        self.anims[name] = {"frames": frames, "delay": delay}

class Camera:
    def __init__(self, w, h):
        self.pos = pygame.math.Vector2(0, 0)
        self.size = pygame.math.Vector2(w, h)
        self.offset = pygame.math.Vector2(0, 0)
        self.target = None
        self.mode = "static"
        self.shake_timer = 0.0
        self.shake_amp = 0.0
        self.sway_timer = 0.0
        self.sway_speed = 0.0
        self.sway_amp = 0.0

    def bind(self, target=None, mode="static", **kwargs):
        if target: self.target = target
        self.mode = mode
        for k, v in kwargs.items(): setattr(self, k, v)
        return self

    def shake(self, amp, duration):
        self.shake_amp = amp
        self.shake_timer = duration

    def update(self, dt):
        if self.target and self.mode == "dynamic":
            self.pos = self.pos.lerp(self.target.pos - self.size / 2, 5 * dt)
        shake_vec = pygame.math.Vector2(0, 0)
        if self.shake_timer > 0:
            shake_vec.x = random.uniform(-self.shake_amp, self.shake_amp)
            shake_vec.y = random.uniform(-self.shake_amp, self.shake_amp)
            self.shake_timer -= dt
        sway_vec = pygame.math.Vector2(0, 0)
        if self.sway_amp > 0:
            self.sway_timer += dt
            sway_vec.x = math.sin(self.sway_timer * self.sway_speed) * self.sway_amp
            sway_vec.y = math.cos(self.sway_timer * self.sway_speed * 0.8) * self.sway_amp
        self.offset = self.pos + shake_vec + sway_vec

class Anim:
    def __init__(self, target, attr, end_val, duration):
        self.target = target
        self.attr = attr
        self.start_val = getattr(target, attr)
        if isinstance(self.start_val, (tuple, list, pygame.math.Vector2)):
            self.start_val = pygame.math.Vector2(self.start_val)
            self.end_val = pygame.math.Vector2(end_val)
        else:
            self.end_val = end_val
        self.duration = duration
        self.time = 0.0
        self.done = False

    def update(self, dt):
        if self.done: return
        self.time += dt
        t = 1.0 if self.duration <= 0 else max(0.0, min(self.time / self.duration, 1.0))
        if isinstance(self.start_val, pygame.math.Vector2):
            if t >= 1.0: setattr(self.target, self.attr, pygame.math.Vector2(self.end_val.x, self.end_val.y))
            else: setattr(self.target, self.attr, self.start_val.lerp(self.end_val, t))
        else:
            setattr(self.target, self.attr, self.start_val + (self.end_val - self.start_val) * t)
        if t >= 1.0: self.done = True

class GObj:
    def __init__(self, x, y, w, h, layer=0, space=None, body_type=pymunk.Body.KINEMATIC, shape_type="rect", hitbox_size=None):
        self.engine = None
        self.pos = pygame.math.Vector2(x, y)
        self.size = pygame.math.Vector2(w, h)
        self.layer = layer
        self.color = (255, 255, 255)
        self.anims = []
        self.custom_updates = []
        self.texture_name = None
        self.anim_name = None
        self.anim_timer = 0.0
        self.anim_idx = 0
        self.space = space
        self.body = None
        self.shape = None
        if self.space:
            mass = 1
            hx, hy = hitbox_size if hitbox_size else (w, h)
            if shape_type == "rect": moment = pymunk.moment_for_box(mass, (hx, hy))
            else: moment = pymunk.moment_for_circle(mass, 0, hx / 2)
            self.body = pymunk.Body(mass, moment, body_type)
            self.body.position = (x, y)
            if shape_type == "rect": self.shape = pymunk.Poly.create_box(self.body, (hx, hy))
            elif shape_type == "circle": self.shape = pymunk.Circle(self.body, hx / 2)
            self.space.add(self.body, self.shape)

    def set(self, **kwargs):
        for k, v in kwargs.items():
            if k in ['pos', 'size'] and isinstance(v, (tuple, list)): v = pygame.math.Vector2(v)
            setattr(self, k, v)
        return self

    def bind(self, **kwargs):
        if "move" in kwargs and kwargs["move"] == "wasd":
            spd = kwargs.get("speed", 200)
            self.add_update(lambda dt: self._move_wasd(dt, spd))
        if "on_click" in kwargs:
            self.add_update(lambda dt: kwargs["on_click"]() if self.is_clicked(self.engine.input, camera_offset=self.engine.camera.offset) else None)
        return self

    def _move_wasd(self, dt, speed):
        if not self.engine: return
        vx, vy = 0, 0
        inp = self.engine.input
        if inp.key(pygame.K_w) or inp.key(pygame.K_UP): vy -= 1
        if inp.key(pygame.K_s) or inp.key(pygame.K_DOWN): vy += 1
        if inp.key(pygame.K_a) or inp.key(pygame.K_LEFT): vx -= 1
        if inp.key(pygame.K_d) or inp.key(pygame.K_RIGHT): vx += 1
        if vx != 0 or vy != 0:
            length = math.hypot(vx, vy)
            vx, vy = (vx/length)*speed, (vy/length)*speed
        if self.body and self.body.body_type in (pymunk.Body.KINEMATIC, pymunk.Body.DYNAMIC):
            self.body.velocity = (vx, vy)
        else:
            self.pos.x += vx * dt; self.pos.y += vy * dt

    def is_hovered(self, inp, camera_offset=None):
        off_x = camera_offset.x if camera_offset else 0
        off_y = camera_offset.y if camera_offset else 0
        return self.pos.x - off_x <= inp.mouse_pos.x <= self.pos.x - off_x + self.size.x and self.pos.y - off_y <= inp.mouse_pos.y <= self.pos.y - off_y + self.size.y

    def is_clicked(self, inp, button=0, camera_offset=None):
        return self.is_hovered(inp, camera_offset) and inp.mouse_down(button)

    def anim(self, attr, end_val, duration):
        self.anims.append(Anim(self, attr, end_val, duration))
        return self

    def add_update(self, func):
        self.custom_updates.append(func)
        return self

    def update(self, dt, resources=None):
        for a in self.anims[:]:
            a.update(dt)
            if a.done: self.anims.remove(a)
        for uf in self.custom_updates: uf(dt)
        if self.body:
            if self.body.body_type == pymunk.Body.DYNAMIC:
                self.pos.x, self.pos.y = self.body.position.x, self.body.position.y
            else: self.body.position = (self.pos.x, self.pos.y)
        if self.anim_name and resources and self.anim_name in resources.anims:
            self.anim_timer += dt
            anim_data = resources.anims[self.anim_name]
            if self.anim_timer >= anim_data["delay"]:
                self.anim_timer = 0
                self.anim_idx = (self.anim_idx + 1) % len(anim_data["frames"])

    def draw(self, screen, camera_offset=None, resources=None):
        off_x = camera_offset.x if camera_offset else 0
        off_y = camera_offset.y if camera_offset else 0
        draw_x, draw_y = int(self.pos.x - off_x), int(self.pos.y - off_y)
        if self.anim_name and resources and self.anim_name in resources.anims:
            screen.blit(resources.anims[self.anim_name]["frames"][self.anim_idx], (draw_x, draw_y))
        elif self.texture_name and resources and self.texture_name in resources.images:
            screen.blit(resources.images[self.texture_name], (draw_x, draw_y))
        else:
            pygame.draw.rect(screen, self.color, (draw_x, draw_y, int(self.size.x), int(self.size.y)))

class ObjectManager:
    def __init__(self, engine=None):
        self.engine = engine
        self.groups = {}
        self.loose_objs = []

    def create(self, x, y, w, h, layer=0, physics=False, body_type=pymunk.Body.KINEMATIC, shape_type="rect", hitbox_size=None):
        spc = self.engine.physics_space if (self.engine and physics) else None
        o = GObj(x, y, w, h, layer, spc, body_type, shape_type, hitbox_size)
        o.engine = self.engine
        self.loose_objs.append(o)
        return o

    def spawn(self, preset, x, y, w=50, h=50, **kwargs):
        layer = kwargs.get("layer", 0)
        if preset == "static": return self.create(x, y, w, h, layer, physics=False)
        elif preset == "entity": return self.create(x, y, w, h, layer, physics=True, body_type=pymunk.Body.DYNAMIC)
        elif preset == "kinematic": return self.create(x, y, w, h, layer, physics=True, body_type=pymunk.Body.KINEMATIC)

    def group(self, name, *objs):
        if name not in self.groups: self.groups[name] = GGroup(*objs)
        else: self.groups[name].add(*objs)
        return self.groups[name]

    def update(self, dt):
        res = self.engine.resources if self.engine else None
        for g in self.groups.values(): g.update(dt, res)
        for o in self.loose_objs: o.update(dt, res)

    def draw(self, screen, camera=None, resources=None):
        cam_off = camera.offset if camera else None
        all_objs = []
        for g in self.groups.values(): all_objs.extend(g.objs)
        all_objs.extend(self.loose_objs)
        all_objs.sort(key=lambda o: getattr(o, 'layer', 0))
        for o in all_objs: o.draw(screen, cam_off, resources)

class UIElement:
    def __init__(self, x, y, w, h):
        self.pos = pygame.math.Vector2(x, y)
        self.size = pygame.math.Vector2(w, h)
        self.alpha = 255
        self.color = (200, 200, 200)
        self.visible = True
        self.layer = 0
        self.shadow = None
        self.anims = []

    def set_color(self, color): self.color = color; return self
    def set_shadow(self, offset=(5,5), blur=10, color=(0,0,0)): self.shadow = (offset, blur, color); return self
    def anim(self, attr, end_val, duration): self.anims.append(Anim(self, attr, end_val, duration)); return self
    def fade_in(self, duration=1.0): self.alpha = 0; return self.anim("alpha", 255, duration)

    def update(self, dt):
        for a in self.anims[:]:
            a.update(dt)
            if a.done: self.anims.remove(a)

    def draw_effects(self, screen):
        if self.shadow and self.alpha > 0:
            s_off, s_blur, s_col = self.shadow
            s_surf = pygame.Surface((self.size.x + s_blur*2, self.size.y + s_blur*2), pygame.SRCALPHA)
            pygame.draw.rect(s_surf, (*s_col, int(self.alpha * 0.5)), (s_blur, s_blur, self.size.x, self.size.y), border_radius=int(s_blur))
            screen.blit(s_surf, (self.pos.x + s_off[0] - s_blur, self.pos.y + s_off[1] - s_blur))

class UIButton(UIElement):
    def __init__(self, x, y, w, h, text="", font=None):
        super().__init__(x, y, w, h)
        self.text = text
        self.font = font
        self.hover_color = (240, 240, 240)
        self.base_color = (200, 200, 200)
        self.border_radius = 5
        self.action = None

    def on_click(self, func): self.action = func; return self

    def update(self, dt, inp):
        super().update(dt)
        mx, my = inp.mouse_pos
        is_hover = self.pos.x <= mx <= self.pos.x + self.size.x and self.pos.y <= my <= self.pos.y + self.size.y
        self.color = self.hover_color if is_hover else self.base_color
        if is_hover and inp.mouse_down(0) and self.action: self.action()

    def draw(self, screen):
        if not self.visible: return
        self.draw_effects(screen)
        surf = pygame.Surface(self.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (*self.color, int(self.alpha)), (0, 0, self.size.x, self.size.y), border_radius=self.border_radius)
        screen.blit(surf, self.pos)
        if self.text and self.font:
            t_surf = self.font.render(self.text, True, (0, 0, 0))
            t_surf.set_alpha(int(self.alpha))
            t_rect = t_surf.get_rect(center=(self.pos.x + self.size.x/2, self.pos.y + self.size.y/2))
            screen.blit(t_surf, t_rect)

class UIManager:
    def __init__(self, engine):
        self.engine = engine
        self.elements = []

    def create_button(self, x, y, w, h, text=""):
        btn = UIButton(x, y, w, h, text, self.engine.font)
        self.elements.append(btn)
        return btn

    def update(self, dt):
        for e in self.elements:
            if isinstance(e, UIButton): e.update(dt, self.engine.input)
            else: e.update(dt)

    def draw(self, screen):
        self.elements.sort(key=lambda e: e.layer)
        for e in self.elements: e.draw(screen)

class GGroup:
    def __init__(self, *objs): self.objs = list(objs)
    def add(self, *objs): self.objs.extend(objs); return self
    def do(self, method, *args, **kwargs):
        for o in self.objs: getattr(o, method)(*args, **kwargs)
        return self
    def set(self, **kwargs):
        for o in self.objs: o.set(**kwargs)
        return self
    def bind(self, **kwargs):
        for o in self.objs: o.bind(**kwargs)
        return self
    def anim(self, attr, end_val, duration):
        for o in self.objs: o.anim(attr, end_val, duration)
        return self
    def update(self, dt, resources=None):
        for o in self.objs: o.update(dt, resources)
    def draw(self, screen, camera_offset=None, resources=None):
        for o in self.objs: o.draw(screen, camera_offset, resources)

class SDKEngine:
    def __init__(self):
        self.logs = []
        self.max_logs = 35
        self.cache_dir = "cache"
        if not os.path.exists(self.cache_dir): os.makedirs(self.cache_dir)
        self.current_log_file = os.path.join(self.cache_dir, f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        self.log("Booting SDK-Engine v1.3.0 beta...", (150, 255, 255))
        self.setup_env()
        self.cfg = self.load_cfg("config.cfg")
        self.validate_cfg()
        self.events = {}
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.is_fullscreen = False
        self.window_mode_size = (self.cfg.get("width", 800), self.cfg.get("height", 600))
        self.set_window(self.window_mode_size[0], self.window_mode_size[1], self.cfg.get("title", "SDK-Engine"), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 16) 
        self.physics_space = pymunk.Space()
        self.physics_space.gravity = (0, self.cfg.get("gravity", 900))
        self.audio = {"sounds": {}, "load": self.load_sound, "play": self.play_sound, "generate": self.generate_sound}
        self.resources = ResourceManager()
        self.camera = Camera(self.window_mode_size[0], self.window_mode_size[1])
        self.objects = ObjectManager(self)
        self.ui = UIManager(self)
        self.input = InputManager()
        self.state = {
            "running": True, "cfg": self.cfg, "dt": 0.0, "time": 0.0, "shared": {},
            "screen": self.screen, "net": {"socket": None, "clients": {}, "is_server": False},
            "physics": self.physics_space, "audio": self.audio, "objects": self.objects,
            "ui": self.ui, "resources": self.resources, "camera": self.camera, "input": self.input
        }
        self.math = {
            "lerp": lambda a, b, t: a + (b - a) * t,
            "dist": lambda x1, y1, x2, y2: math.sqrt((x2-x1)**2 + (y2-y1)**2),
            "angle": lambda x1, y1, x2, y2: math.atan2(y2-y1, x2-x1),
            "trajectory": lambda v, th, g, x: x * math.tan(th) - (g * x**2) / (2 * v**2 * math.cos(th)**2),
            "exp_decay": lambda a, b, decay, dt: b + (a - b) * math.exp(-decay * dt)
        }
        self.on("update", lambda s: self.camera.update(s["dt"]), priority=100)
        self.on("update", lambda s: self.objects.update(s["dt"]))
        self.on("update", lambda s: self.ui.update(s["dt"]))
        self.on("draw", lambda s: self.objects.draw(s["screen"], s["camera"], s["resources"]))
        self.on("draw", lambda s: self.ui.draw(s["screen"]))

    def validate_cfg(self):
        req = {"width": 800, "height": 600, "fps": 60, "gravity": 900, "title": "SDK-Engine", "debug": True}
        needs_save = False
        for k, v in req.items():
            if k not in self.cfg:
                self.log(f"CFG: Missing '{k}', set to default", (255, 255, 50))
                self.cfg[k] = v
                needs_save = True
        if needs_save: self.save_cfg()

    def set_window(self, w, h, title=None, flags=0):
        if title is None: title = self.cfg.get("title", "SDK-Engine")
        self.screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption(title)
        if hasattr(self, 'state'): self.state["screen"] = self.screen
        self.log(f"Window: {w}x{h}, Title: '{title}'", (200, 255, 200))

    def log(self, text, color=(255, 255, 255)):
        log_str = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}"
        self.logs.append((log_str, color))
        if len(self.logs) > self.max_logs: self.logs.pop(0)
        print(log_str)
        try:
            with open(self.current_log_file, "a", encoding="utf-8") as f: f.write(log_str + "\n")
        except: pass

    def setup_env(self):
        if not os.path.exists("mods"): os.makedirs("mods")
        if not os.path.exists("config.cfg"):
            with open("config.cfg", "w") as f: f.write("debug = true\nwidth = 800\nheight = 600\nfps = 60\ngravity = 900\ntitle = SDK-Engine\n")

    def load_cfg(self, path):
        d = {}
        try:
            with open(path, "r") as f:
                for line in f:
                    if "=" in line:
                        k, v = [x.strip() for x in line.split("=", 1)]
                        k = k.lower()
                        if v.lower() in ["true", "false"]: v = v.lower() == "true"
                        else:
                            try: v = float(v) if "." in v else int(v)
                            except: pass
                        d[k] = v
        except Exception as e: self.log(f"CFG Error: {e}", (255, 50, 50))
        return d

    def save_cfg(self):
        try:
            with open("config.cfg", "w") as f:
                for k, v in self.cfg.items():
                    f.write(f"{k} = {'true' if v else 'false'}\n" if isinstance(v, bool) else f"{k} = {v}\n")
        except: pass

    def load_sound(self, name, path):
        try: self.audio["sounds"][name] = pygame.mixer.Sound(path)
        except Exception as e: self.log(f"AUDIO Error: {e}", (255, 50, 50))

    def play_sound(self, name, volume=1.0):
        if name in self.audio["sounds"]:
            s = self.audio["sounds"][name]
            s.set_volume(volume)
            s.play()

    def generate_sound(self, name, freq=440, duration=0.5, volume=0.5, wave_type="sine"):
        try:
            t = np.linspace(0, duration, int(44100 * duration), endpoint=False)
            wave = np.sin(freq * t * 2 * np.pi) if wave_type == "sine" else np.sign(np.sin(freq * t * 2 * np.pi))
            snd_arr = np.zeros((len(wave), 2), dtype=np.int16)
            snd_arr[:, 0] = wave * volume * 32767
            snd_arr[:, 1] = wave * volume * 32767
            snd = pygame.sndarray.make_sound(snd_arr)
            self.audio["sounds"][name] = snd
            return snd
        except: pass

    def on(self, name, func, priority=0, once=False):
        if name not in self.events: self.events[name] = []
        self.events[name].append({"func": func, "prio": priority, "once": once})
        self.events[name].sort(key=lambda x: x["prio"], reverse=True)

    def emit(self, name, data=None):
        if name in self.events:
            to_remove = []
            for sub in self.events[name].copy():
                try: 
                    sub["func"](data if data is not None else self.state)
                    if sub["once"]: to_remove.append(sub)
                except Exception as e: 
                    self.log(f"MOD ERR: Event '{name}' failed. ({e})", (255, 80, 80))
                    to_remove.append(sub)
            for sub in to_remove:
                if sub in self.events[name]: self.events[name].remove(sub)

    def load_mods(self):
        if not os.path.exists("mods"): return
        for fn in os.listdir("mods"):
            full_path = os.path.join("mods", fn)
            if not fn.endswith(".py") or os.path.getsize(full_path) == 0: continue
            name = fn[:-3]
            try:
                spec = importlib.util.spec_from_file_location(name, full_path)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                if hasattr(m, "init"): m.init(self)
                self.log(f"MOD: Injected {name}", (80, 255, 10))
            except Exception as e: self.log(f"MOD Error [{name}]: {e}", (255, 50, 50))

    def render_ui(self):
        if not self.cfg.get("debug", True): return
        con_surf = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
        con_surf.fill((0, 0, 0, 140))
        self.screen.blit(con_surf, (0, 0))
        for i, (txt, col) in enumerate(self.logs):
            self.screen.blit(self.font.render(txt, True, col), (10, 10 + i*18))

    def run(self):
        self.load_mods()
        fps_cap = self.cfg.get("fps", 60)
        physics_steps = 2
        step_dt = (1.0 / fps_cap) / physics_steps
        while self.state["running"]:
            self.state["dt"] = self.clock.tick(fps_cap) / 1000.0
            self.state["time"] += self.state["dt"]
            for _ in range(physics_steps): self.physics_space.step(step_dt)
            for e in pygame.event.get():
                if e.type == pygame.QUIT: self.state["running"] = False
                elif e.type == pygame.VIDEORESIZE:
                    if not self.is_fullscreen:
                        self.window_mode_size = (e.w, e.h)
                        self.screen = pygame.display.set_mode((e.w, e.h), pygame.RESIZABLE)
                        self.state["screen"] = self.screen
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    self.is_fullscreen = not self.is_fullscreen
                    self.screen = pygame.display.set_mode((0, 0) if self.is_fullscreen else self.window_mode_size, pygame.FULLSCREEN if self.is_fullscreen else pygame.RESIZABLE)
                    self.state["screen"] = self.screen
                self.emit("event", e)
            self.input.update(self.camera.offset)
            self.emit("update")
            self.screen.fill((10, 10, 15))
            self.emit("draw")
            self.render_ui()
            pygame.display.flip()
        pygame.quit()

if __name__ == "__main__":
    SDKEngine().run()