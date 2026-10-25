import sys
import os
import importlib.util

ENGINE_NAME = "SDK-engine-v1.4.0-stable"


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


def _chk():
    m = []
    for l in ['pygame', 'numpy', 'pymunk']:
        if importlib.util.find_spec(l) is None: m.append(l)
    if m:
        print(f"Missing libraries: {', '.join(m)}")
        print("Press Enter to exit...")
        input()
        sys.exit(1)

_set_console_title(ENGINE_NAME)
_chk()

import pygame
import copy
import datetime
import math
import socket
import threading
import traceback
import types
import functools
import json
import numpy as np
import pymunk
import random
import weakref


class InputManager:
    def __init__(self):
        self.keys = None
        self.keys_prev = None
        self.mouse = (False,) * 5
        self.mouse_prev = (False,) * 5
        self.mouse_pos = pygame.math.Vector2(0, 0)
        self.world_mouse_pos = pygame.math.Vector2(0, 0)
        self.binds = []
        self._code_cache = {}

    @staticmethod
    def _state(arr, code):
        if arr is None:
            return False
        try:
            return bool(arr[code])
        except (IndexError, KeyError, TypeError):
            return False

    def _get_codes(self, k):
        if isinstance(k, int):
            return (k,)
        key = str(k).upper()
        cached = self._code_cache.get(key)
        if cached is not None:
            return cached
        aliases = {
            "UP": [pygame.K_UP], "DOWN": [pygame.K_DOWN], "LEFT": [pygame.K_LEFT], "RIGHT": [pygame.K_RIGHT],
            "SPACE": [pygame.K_SPACE], "ENTER": [pygame.K_RETURN], "ESC": [pygame.K_ESCAPE],
            "LSHIFT": [pygame.K_LSHIFT], "RSHIFT": [pygame.K_RSHIFT], "TAB": [pygame.K_TAB],
            "SHIFT": [pygame.K_LSHIFT, pygame.K_RSHIFT], "CTRL": [pygame.K_LCTRL, pygame.K_RCTRL],
            "ALT": [pygame.K_LALT, pygame.K_RALT],
        }
        ru_to_en = {'Й': 'Q', 'Ц': 'W', 'У': 'E', 'К': 'R', 'Е': 'T', 'Н': 'Y', 'Г': 'U', 'Ш': 'I', 'Щ': 'O', 'З': 'P', 'Х': 'LEFTBRACKET', 'Ъ': 'RIGHTBRACKET', 'Ф': 'A', 'Ы': 'S', 'В': 'D', 'А': 'F', 'П': 'G', 'Р': 'H', 'О': 'J', 'Л': 'K', 'Д': 'L', 'Ж': 'SEMICOLON', 'Э': 'QUOTE', 'Я': 'Z', 'Ч': 'X', 'С': 'C', 'М': 'V', 'И': 'B', 'Т': 'N', 'Ь': 'M', 'Б': 'COMMA', 'Ю': 'PERIOD'}
        en_key = ru_to_en.get(key, key)
        res = list(aliases.get(en_key, []))
        code = getattr(pygame, "K_" + en_key.lower(), None)
        if code is not None and code not in res:
            res.append(code)
        res = tuple(res)
        self._code_cache[key] = res
        return res

    def check_custom(self, k_str):
        return any(self._state(self.keys, c) for c in self._get_codes(k_str))

    def check_custom_down(self, k_str):
        if self.keys is None or self.keys_prev is None:
            return False
        for c in self._get_codes(k_str):
            if self._state(self.keys, c) and not self._state(self.keys_prev, c):
                return True
        return False

    def bind_func(self, k_str, func):
        self.binds.append((k_str, func))

    def refresh_world(self, camera_offset=None):
        if camera_offset is not None:
            self.world_mouse_pos = self.mouse_pos + pygame.math.Vector2(camera_offset)
        else:
            self.world_mouse_pos = pygame.math.Vector2(self.mouse_pos)

    def update(self, camera_offset=None):
        self.keys_prev = self.keys
        self.keys = pygame.key.get_pressed()
        self.mouse_prev = self.mouse
        self.mouse = tuple(pygame.mouse.get_pressed(num_buttons=5))
        self.mouse_pos = pygame.math.Vector2(pygame.mouse.get_pos())
        self.refresh_world(camera_offset)
        for k_str, func in list(self.binds):
            if self.check_custom_down(k_str):
                func()

    def key(self, k):
        return self._state(self.keys, k)

    def key_down(self, k):
        if self.keys_prev is None:
            return False
        return self._state(self.keys, k) and not self._state(self.keys_prev, k)

    def key_up(self, k):
        if self.keys_prev is None:
            return False
        return not self._state(self.keys, k) and self._state(self.keys_prev, k)

    @staticmethod
    def _btn(arr, b):
        return 0 <= b < len(arr) and bool(arr[b])

    def mouse_btn(self, b):
        return self._btn(self.mouse, b)

    def mouse_down(self, b):
        return self._btn(self.mouse, b) and not self._btn(self.mouse_prev, b)

    def mouse_up(self, b):
        return not self._btn(self.mouse, b) and self._btn(self.mouse_prev, b)


class ResourceManager:
    def __init__(self):
        self.images = {}
        self.anims = {}
        self.engine = None
        self._missing = set()
        self._index = None

    def _log(self, text, color=(255, 50, 50)):
        if self.engine:
            self.engine.log(text, color)

    def _build_index(self):
        idx = {}
        if os.path.isdir("assets"):
            for root, _, files in os.walk("assets"):
                for f in files:
                    idx.setdefault(f, os.path.join(root, f))
        self._index = idx

    def _find(self, filename):
        if self._index is None:
            self._build_index()
        path = self._index.get(filename)
        if path and os.path.isfile(path):
            return path
        self._build_index()
        return self._index.get(filename)

    def _resolve(self, path):
        found = self._find(os.path.basename(path))
        if found:
            return found
        if os.path.isfile(path):
            return path
        return None

    def _load_surface(self, path, scale=None):
        resolved = self._resolve(path)
        if not resolved:
            if path not in self._missing:
                self._missing.add(path)
                self._log(f"WARN: Asset not found: {path}", (255, 150, 50))
            return None
        try:
            img = pygame.image.load(resolved).convert_alpha()
            if scale:
                size = (int(scale[0]), int(scale[1]))
                smooth = self.engine.cfg.get("smoothing", False) if self.engine else False
                img = pygame.transform.smoothscale(img, size) if smooth else pygame.transform.scale(img, size)
            return img
        except Exception as e:
            self._log(f"ERR: {e}")
            return None

    def load_img(self, name, path, scale=None):
        if name in self.images:
            return self.images[name]
        img = self._load_surface(path, scale)
        if img is not None:
            self.images[name] = img
        return img

    def load_anim(self, name, paths, delay=0.1, scale=None):
        if name in self.anims:
            return self.anims[name]
        frames = [s for s in (self._load_surface(p, scale) for p in paths) if s is not None]
        if not frames:
            return None
        self.anims[name] = {"delay": delay, "frames": frames}
        return self.anims[name]

    def load_ui(self, name):
        path = self._find(f"{name}.json")
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            self._log(f"ERR: UI '{name}' failed to load ({e})")
            return None


class Camera:
    def __init__(self, w, h):
        self.pos = pygame.math.Vector2(0, 0)
        self.size = pygame.math.Vector2(w, h)
        self.offset = pygame.math.Vector2(0, 0)
        self.target = None
        self.shake_timer = 0.0
        self.shake_amp = 0.0
        self.sway_timer = 0.0
        self.sway_speed = 0.0
        self.sway_amp = 0.0

    def _target_pos(self):
        c = getattr(self.target, "center", None)
        if c is None:
            c = self.target.pos
        return pygame.math.Vector2(c) - self.size / 2

    def follow(self, target, snap=False):
        self.target = target
        if snap and target is not None:
            self.pos = self._target_pos()
            self.offset = pygame.math.Vector2(self.pos)
        return self

    def shake(self, amp, duration):
        self.shake_amp = amp
        self.shake_timer = duration
        return self

    def sway(self, amp, speed):
        self.sway_amp = amp
        self.sway_speed = speed
        return self

    def update(self, dt):
        if self.target is not None:
            lerp_factor = max(0.0, min(5 * dt, 1.0))
            self.pos = self.pos.lerp(self._target_pos(), lerp_factor)
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
        self.duration = duration
        self.time = 0.0
        self.done = False
        start = getattr(target, attr)
        if isinstance(start, pygame.math.Vector2):
            self.mode = "vec"
            self.start_val = pygame.math.Vector2(start)
            self.end_val = pygame.math.Vector2(end_val)
        elif isinstance(start, (tuple, list)):
            self.mode = "seq"
            self.kind = type(start)
            self.start_val = list(start)
            self.end_val = list(end_val)
            if len(self.start_val) != len(self.end_val):
                raise ValueError("Anim: start and end values must have the same length")
            self.as_int = all(isinstance(v, int) and not isinstance(v, bool) for v in self.start_val + self.end_val)
        else:
            self.mode = "scalar"
            self.start_val = start
            self.end_val = end_val

    def update(self, dt):
        if self.done:
            return
        self.time += dt
        t = 1.0 if self.duration <= 0 else max(0.0, min(self.time / self.duration, 1.0))
        if self.mode == "vec":
            value = pygame.math.Vector2(self.end_val) if t >= 1.0 else self.start_val.lerp(self.end_val, t)
        elif self.mode == "seq":
            if t >= 1.0:
                values = list(self.end_val)
            else:
                values = [s + (e - s) * t for s, e in zip(self.start_val, self.end_val)]
                if self.as_int:
                    values = [int(round(v)) for v in values]
            value = self.kind(values)
        else:
            value = self.end_val if t >= 1.0 else self.start_val + (self.end_val - self.start_val) * t
        setattr(self.target, self.attr, value)
        if t >= 1.0:
            self.done = True


def _gradient_key(g):
    return tuple(tuple(c) for c in g) if g else None


def _fill_gradient(surf, grad, w, h, alpha=255):
    c1, c2 = grad
    for y in range(h):
        r = y / h
        col = [int(c1[i] + (c2[i] - c1[i]) * r) for i in range(3)]
        pygame.draw.line(surf, (*col, alpha), (0, y), (w, y))


class GObj:
    def __init__(self, x, y, w, h, layer=0, space=None, body_type=pymunk.Body.KINEMATIC, shape_type="rect", hitbox_size=None):
        self._engine_ref = None
        self._pos = pygame.math.Vector2(x, y)
        self._size = pygame.math.Vector2(w, h)
        self._angle = 0.0
        self.layer = layer
        self.color = (255, 255, 255)
        self.gradient = None
        self.shimmer = False
        self.visible = True
        self.alive = True
        self.anims = []
        self.custom_updates = []
        self.components = []
        self.texture_name = None
        self.anim_name = None
        self.anim_timer = 0.0
        self.anim_idx = 0
        self._anim_last = None
        self.space = space
        self.body = None
        self.shape = None
        self.shape_type = shape_type
        self.hitbox_size = hitbox_size
        self.physics_mode = "2d"
        self.anchor = "topleft"
        self._mass = 1
        self._synced_pos = (self._pos.x, self._pos.y)
        self._control_fn = None
        self._controls_cfg = None
        self._surf_cache = None
        self._surf_cache_key = None
        if self.space:
            self._create_physics(body_type, 1)

    @property
    def engine(self):
        return self._engine_ref() if self._engine_ref is not None else None

    @engine.setter
    def engine(self, value):
        self._engine_ref = weakref.ref(value) if value is not None else None

    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, value):
        self._pos = pygame.math.Vector2(value)

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, value):
        self._size = pygame.math.Vector2(value)

    @property
    def angle(self):
        return math.degrees(self.body.angle) if self.body else self._angle

    @angle.setter
    def angle(self, value):
        if self.body:
            self.body.angle = math.radians(value)
        else:
            self._angle = float(value)

    def _centered(self):
        return self.anchor == "center" or self.body is not None

    @property
    def center(self):
        if self._centered():
            return pygame.math.Vector2(self._pos)
        return self._pos + self._size / 2

    def _half(self):
        if self._centered():
            return pygame.math.Vector2(0, 0)
        return self._size / 2

    def _create_physics(self, body_type, mass):
        hx, hy = self.hitbox_size if self.hitbox_size else (self._size.x, self._size.y)
        self._mass = mass
        if self.shape_type == "rect":
            moment = pymunk.moment_for_box(mass, (hx, hy))
        else:
            moment = pymunk.moment_for_circle(mass, 0, hx / 2)
        self.body = pymunk.Body(mass, moment, body_type)
        self.body.position = (self._pos.x, self._pos.y)
        if self.shape_type == "rect":
            self.shape = pymunk.Poly.create_box(self.body, (hx, hy))
        else:
            self.shape = pymunk.Circle(self.body, hx / 2)
        self.space.add(self.body, self.shape)
        self._synced_pos = (self._pos.x, self._pos.y)

    def release_physics(self):
        if self.space is not None and self.body is not None and self.body.space is not None:
            self.space.remove(self.body, self.shape)

    def teleport(self, x, y):
        self._pos.x = x
        self._pos.y = y
        if self.body is not None:
            self.body.position = (x, y)
            if self.space is not None and self.body.space is not None:
                self.space.reindex_shapes_for_body(self.body)
        self._synced_pos = (self._pos.x, self._pos.y)
        return self

    def attr(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    at = attr

    def bind_camera(self, **settings):
        if not self.engine: return self
        snap = settings.pop("snap", False)
        self.engine.camera.follow(self, snap=snap)
        for k, v in settings.items():
            if hasattr(self.engine.camera, k):
                setattr(self.engine.camera, k, v)
        return self

    def bind_input(self, mode="rpg", mapping=None, **settings):
        phys_mode = "rpg" if mode in ["rpg", False, "none"] else "2d"
        self.setup_physics(phys_mode)
        if mapping is None:
            mapping = {"up": "W", "down": "S", "left": "A", "right": "D", "jump": "SPACE"}
        self.setup_controls(mapping, speed=settings.get("speed", 200), jump=settings.get("jump", 400), lock_rotation=settings.get("lock_rotation", True))
        return self

    def set(self, **kwargs):
        for k, v in kwargs.items():
            if k == 'texture_name' and v and self.engine and self.engine.resources:
                res = self.engine.resources
                if v not in res.images and v not in res._missing:
                    res.load_img(v, v, scale=(int(self._size.x), int(self._size.y)))
            setattr(self, k, v)
        return self

    def anim(self, attr, end_val, duration):
        self.anims.append(Anim(self, attr, end_val, duration))
        return self

    def add_update(self, func):
        self.custom_updates.append(func)
        return self

    def add_component(self, component):
        component.owner = self
        self.components.append(component)
        return self

    def destroy(self):
        self.alive = False
        return self

    def setup_physics(self, mode="2d"):
        self.physics_mode = mode
        if self.body:
            if mode == "rpg":
                def z_grav(b, g, d, dt):
                    pymunk.Body.update_velocity(b, (0, 0), d, dt)
                self.body.velocity_func = z_grav
            else:
                self.body.velocity_func = pymunk.Body.update_velocity
        return self

    def _on_ground(self):
        if not self.body:
            return False
        found = [False]
        shape = self.shape

        def cb(arb):
            ny = arb.contact_point_set.normal.y
            if arb.shapes[0] is not shape:
                ny = -ny
            if ny > 0.5:
                found[0] = True

        self.body.each_arbiter(cb)
        return found[0]

    def setup_controls(self, mapping, speed=200, jump=400, lock_rotation=True):
        if self._control_fn in self.custom_updates:
            self.custom_updates.remove(self._control_fn)
        self._controls_cfg = (dict(mapping), speed, jump, lock_rotation)
        if lock_rotation and self.body and self.body.body_type == pymunk.Body.DYNAMIC:
            self.body.moment = float("inf")

        def m(dt):
            eng = self.engine
            if not eng:
                return
            inp = eng.input
            vx, vy = 0, 0
            is_jump = False
            for d_name, k_str in mapping.items():
                if inp.check_custom(k_str):
                    if d_name == "up": vy -= 1
                    elif d_name == "down": vy += 1
                    elif d_name == "left": vx -= 1
                    elif d_name == "right": vx += 1
                    elif d_name == "jump": is_jump = True
            body = self.body
            movable = body is not None and body.body_type in (pymunk.Body.KINEMATIC, pymunk.Body.DYNAMIC)
            if self.physics_mode == "rpg":
                length = math.hypot(vx, vy)
                if length:
                    vx, vy = vx / length * speed, vy / length * speed
                if movable:
                    body.velocity = (vx, vy)
                else:
                    self.pos.x += vx * dt
                    self.pos.y += vy * dt
            else:
                vx = math.copysign(speed, vx) if vx else 0
                wants_jump = is_jump or vy < 0
                if movable:
                    cvx, cvy = body.velocity
                    if body.body_type == pymunk.Body.KINEMATIC:
                        cvy = -jump if wants_jump else (speed if vy > 0 else 0)
                    elif wants_jump and self._on_ground():
                        cvy = -jump
                    body.velocity = (vx, cvy)
                else:
                    self.pos.x += vx * dt
                    if wants_jump:
                        self.pos.y -= jump * dt

        self._control_fn = m
        self.custom_updates.append(m)
        return self

    def setup_camera(self, mode="dynamic", sway_amp=0, sway_speed=0, shake_amp=0, shake_dur=0):
        if not self.engine: return self
        cam = self.engine.camera
        if mode == "dynamic":
            cam.follow(self)
        elif mode == "static":
            cam.target = None
            cam.pos = self.center - cam.size / 2
        if sway_amp > 0 and sway_speed > 0:
            cam.sway(sway_amp, sway_speed)
        if shake_amp > 0 and shake_dur > 0:
            cam.shake(shake_amp, shake_dur)
        return self

    def set_bullet(self, angle, speed):
        if self.body:
            self.body.velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
        return self

    def is_hovered(self, inp, camera_offset=None):
        off_x = camera_offset.x if camera_offset is not None else 0
        off_y = camera_offset.y if camera_offset is not None else 0
        mx = inp.mouse_pos.x + off_x
        my = inp.mouse_pos.y + off_y
        c = self.center
        return abs(mx - c.x) <= self._size.x / 2 and abs(my - c.y) <= self._size.y / 2

    def is_clicked(self, inp, button=0, camera_offset=None):
        return self.is_hovered(inp, camera_offset) and inp.mouse_down(button)

    def clone(self):
        new_obj = self.__class__(self.pos.x, self.pos.y, self.size.x, self.size.y, self.layer, None)
        new_obj.engine = self.engine
        skip = {
            "_pos", "_size", "body", "shape", "space", "_engine_ref", "anims", "custom_updates", "components",
            "_synced_pos", "_control_fn", "_controls_cfg", "_surf_cache", "_surf_cache_key",
        }
        for k, v in self.__dict__.items():
            if k not in skip:
                new_obj.__dict__[k] = v
        new_obj._pos = pygame.math.Vector2(self._pos)
        new_obj._size = pygame.math.Vector2(self._size)
        new_obj._synced_pos = (new_obj._pos.x, new_obj._pos.y)
        new_obj.anims = []
        new_obj.custom_updates = [f for f in self.custom_updates if f is not self._control_fn]
        new_obj.components = []
        for c in self.components:
            nc = c.clone(new_obj) if hasattr(c, "clone") else None
            if nc is None:
                nc = copy.copy(c)
            nc.owner = new_obj
            new_obj.components.append(nc)
        if self.body is not None and self.space is not None:
            new_obj.space = self.space
            mass = self.body.mass if self.body.body_type == pymunk.Body.DYNAMIC else self._mass
            new_obj._create_physics(self.body.body_type, mass)
            new_obj.body.angle = self.body.angle
            for a in ("friction", "elasticity", "sensor", "collision_type", "filter", "surface_velocity"):
                setattr(new_obj.shape, a, getattr(self.shape, a))
            new_obj.setup_physics(self.physics_mode)
        if self._controls_cfg:
            new_obj.setup_controls(*self._controls_cfg)
        if self.engine:
            self.engine.objects.loose_objs.append(new_obj)
        return new_obj

    def _sync_body(self):
        body = self.body
        if body is None:
            return
        cur = (self._pos.x, self._pos.y)
        if cur != self._synced_pos:
            c = self.center
            body.position = (c.x, c.y)
            if self.space is not None and body.space is not None:
                self.space.reindex_shapes_for_body(body)
        elif body.body_type != pymunk.Body.STATIC:
            half = self._half()
            p = body.position
            self._pos.x = p.x - half.x
            self._pos.y = p.y - half.y
        self._synced_pos = (self._pos.x, self._pos.y)

    def update(self, dt, resources=None):
        if not self.alive:
            return
        for c in list(self.components):
            c.update(self, dt)
        for a in self.anims[:]:
            a.update(dt)
            if a.done:
                self.anims.remove(a)
        for uf in list(self.custom_updates):
            uf(dt)
        self._sync_body()
        if self.anim_name != self._anim_last:
            self._anim_last = self.anim_name
            self.anim_idx = 0
            self.anim_timer = 0.0
        if self.anim_name and resources and self.anim_name in resources.anims:
            anim_data = resources.anims[self.anim_name]
            frames = anim_data["frames"]
            if frames:
                delay = max(anim_data["delay"], 1e-4)
                self.anim_timer += dt
                steps = int(self.anim_timer / delay)
                if steps:
                    self.anim_timer -= steps * delay
                    self.anim_idx = (self.anim_idx + steps) % len(frames)

    def _surface_key(self):
        return (max(1, int(self._size.x)), max(1, int(self._size.y)), tuple(self.color), _gradient_key(self.gradient))

    def _rebuild_surf(self, key):
        w, h = key[0], key[1]
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if self.gradient:
            _fill_gradient(surf, self.gradient, w, h)
        else:
            surf.fill(self.color)
        self._surf_cache = surf
        self._surf_cache_key = key

    def draw(self, screen, camera_offset=None, resources=None):
        if not self.visible:
            return
        off_x = camera_offset.x if camera_offset is not None else 0
        off_y = camera_offset.y if camera_offset is not None else 0
        ang = self.angle
        c = self.center
        cx = c.x - off_x
        cy = c.y - off_y
        surf = None
        if self.anim_name and resources and self.anim_name in resources.anims and resources.anims[self.anim_name]["frames"]:
            frames = resources.anims[self.anim_name]["frames"]
            surf = frames[self.anim_idx % len(frames)]
        elif self.texture_name and resources and self.texture_name in resources.images:
            surf = resources.images[self.texture_name]
        elif self.shimmer:
            t = pygame.time.get_ticks() * 0.005
            r, g, b = int(127 + 127 * math.sin(t)), int(127 + 127 * math.sin(t + 2)), int(127 + 127 * math.sin(t + 4))
            surf = pygame.Surface((max(1, int(self._size.x)), max(1, int(self._size.y))), pygame.SRCALPHA)
            surf.fill((r, g, b))
        else:
            key = self._surface_key()
            if self._surf_cache is None or self._surf_cache_key != key:
                self._rebuild_surf(key)
            surf = self._surf_cache
        if ang != 0:
            surf = pygame.transform.rotate(surf, -ang)
        rect = surf.get_rect(center=(int(round(cx)), int(round(cy))))
        sw, sh = screen.get_size()
        if rect.right < 0 or rect.bottom < 0 or rect.left > sw or rect.top > sh:
            return
        screen.blit(surf, rect)


class UIElement:
    def __init__(self, engine, name, pos=(0,0), size=(100,100), parent=None):
        self._engine_ref = weakref.ref(engine) if engine is not None else None
        self.name = name
        self.rel_pos = pygame.math.Vector2(pos)
        self.size = pygame.math.Vector2(size)
        self.parent = parent
        self.children = []
        self.visible = True
        self.layer = 0
        self.color = (50, 50, 50)
        self.alpha = 255
        self.gradient = None
        self.border_color = None
        self.border_width = 0
        self.text = ""
        self.text_color = (255, 255, 255)
        self.on_click = None
        self.scale_val = 1.0
        self._surf_cache = None
        self._surf_cache_key = None
        if parent: parent.children.append(self)

    @property
    def engine(self):
        return self._engine_ref() if self._engine_ref is not None else None

    @engine.setter
    def engine(self, value):
        self._engine_ref = weakref.ref(value) if value is not None else None

    def set_pos(self, x, y):
        self.rel_pos = pygame.math.Vector2(x, y)
        return self

    def scale(self, s):
        self.scale_val = s
        return self

    def style(self, **kwargs):
        for k, v in kwargs.items(): setattr(self, k, v)
        return self

    def click(self, func):
        self.on_click = func
        return self

    def get_real_pos(self):
        p_pos = self.parent.get_real_pos() if self.parent else pygame.math.Vector2(0, 0)
        return p_pos + self.rel_pos

    def is_hovered(self):
        eng = self.engine
        if not eng:
            return False
        pos = self.get_real_pos()
        sz = self.size * self.scale_val
        m = eng.input.mouse_pos
        return pos.x <= m.x <= pos.x + sz.x and pos.y <= m.y <= pos.y + sz.y

    def destroy(self):
        for c in list(self.children):
            c.destroy()
        if self.parent and self in self.parent.children:
            self.parent.children.remove(self)
        eng = self.engine
        if eng and eng.ui.roots.get(self.name) is self:
            del eng.ui.roots[self.name]
        self.visible = False

    def update(self, dt):
        if not self.visible: return
        for child in list(self.children): child.update(dt)

    def _fill_color(self):
        return self.color

    def _extra_key(self):
        return (self.text, tuple(self.text_color))

    def _decorate(self, surf, w, h, font):
        if self.text and font:
            t_surf = font.render(self.text, True, self.text_color)
            surf.blit(t_surf, (w / 2 - t_surf.get_width() / 2, h / 2 - t_surf.get_height() / 2))

    def _get_surf(self):
        eng = self.engine
        font = eng.font if eng else None
        sz = self.size * self.scale_val
        w, h = max(1, int(sz.x)), max(1, int(sz.y))
        fill = tuple(self._fill_color())[:3]
        grad = _gradient_key(self.gradient)
        border = tuple(self.border_color) if self.border_color else None
        key = (w, h, fill, grad, self.alpha, border, self.border_width, self._extra_key(), id(font))
        if self._surf_cache is None or self._surf_cache_key != key:
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            if grad:
                _fill_gradient(surf, grad, w, h, self.alpha)
            else:
                surf.fill((*fill, self.alpha))
            if border and self.border_width > 0:
                pygame.draw.rect(surf, border, (0, 0, w, h), self.border_width)
            self._decorate(surf, w, h, font)
            self._surf_cache = surf
            self._surf_cache_key = key
        return self._surf_cache

    def draw(self, screen):
        if not self.visible: return
        pos = self.get_real_pos()
        screen.blit(self._get_surf(), (pos.x, pos.y))
        for child in sorted(self.children, key=lambda c: c.layer): child.draw(screen)

class UIButton(UIElement):
    def __init__(self, engine, name, pos=(0,0), size=(100,100), parent=None):
        super().__init__(engine, name, pos, size, parent)
        self.color = (60, 60, 180)
        self.hover_color = (80, 80, 220)
        self.press_color = (40, 40, 140)
        self._hovered = False
        self._pressed = False

    def _fill_color(self):
        if self._pressed:
            return self.press_color
        if self._hovered:
            return self.hover_color
        return self.color

    def update(self, dt):
        if not self.visible: return
        eng = self.engine
        if eng:
            self._hovered = self.is_hovered()
            self._pressed = self._hovered and eng.input.mouse_btn(0)
        for child in list(self.children): child.update(dt)


class UIInput(UIElement):
    def __init__(self, engine, name, pos=(0,0), size=(200,40), parent=None):
        super().__init__(engine, name, pos, size, parent)
        self.color = (30, 30, 30)
        self.active_color = (50, 50, 80)
        self.border_color = (120, 120, 120)
        self.border_width = 2
        self.text_color = (255, 255, 255)
        self.placeholder = ""
        self.value = ""
        self._active = False
        self._cursor_timer = 0.0
        self._cursor_visible = True

    def _fill_color(self):
        return self.active_color if self._active else self.color

    def update(self, dt):
        if not self.visible: return
        self._cursor_timer += dt
        if self._cursor_timer >= 0.5:
            self._cursor_timer = 0.0
            self._cursor_visible = not self._cursor_visible
        for child in list(self.children): child.update(dt)

    def activate(self):
        self._active = True
        self._cursor_visible = True
        self._cursor_timer = 0.0

    def deactivate(self):
        self._active = False

    def handle_event(self, event):
        if not self._active: return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.deactivate()
            elif event.unicode and event.unicode.isprintable():
                self.value += event.unicode

    def _extra_key(self):
        return (self.value, self.placeholder, self._active and self._cursor_visible, tuple(self.text_color))

    def _decorate(self, surf, w, h, font):
        if not font: return
        display = self.value if self.value else self.placeholder
        col = self.text_color if self.value else (100, 100, 100)
        cursor_str = "|" if (self._active and self._cursor_visible) else ""
        t_surf = font.render(display + cursor_str, True, col)
        surf.blit(t_surf, (8, h / 2 - t_surf.get_height() / 2))


_UI_TYPE_MAP = {
    "element": UIElement,
    "button": UIButton,
    "input": UIInput,
}


class UIManager:
    def __init__(self, engine):
        self.engine = engine
        self.roots = {}

    def _register(self, el, parent):
        if parent is None:
            self.roots[el.name] = el
        return el

    def create(self, name, pos=(0,0), size=(100,100), parent=None):
        el = UIElement(self.engine, name, pos, size, parent)
        return self._register(el, parent)

    def create_button(self, name, pos=(0,0), size=(120,40), parent=None):
        el = UIButton(self.engine, name, pos, size, parent)
        return self._register(el, parent)

    def create_input(self, name, pos=(0,0), size=(200,40), parent=None):
        el = UIInput(self.engine, name, pos, size, parent)
        return self._register(el, parent)

    def from_json(self, name):
        data = self.engine.resources.load_ui(name)
        if not data: return None
        def parse(d, parent=None):
            cls = _UI_TYPE_MAP.get(d.get("type", "element"), UIElement)
            el = cls(self.engine, d.get("name", "el"), d.get("pos", (0,0)), d.get("size", (100,100)), parent)
            el.style(**d.get("style", {}))
            for c in d.get("children", []): parse(c, el)
            return el
        res = parse(data)
        self.roots[name] = res
        return res

    def get(self, name):
        return self.roots.get(name)

    def remove(self, name):
        el = self.roots.pop(name, None)
        if el:
            el.destroy()

    def update(self, dt):
        for r in list(self.roots.values()): r.update(dt)

    def draw(self, screen):
        sorted_roots = sorted(self.roots.values(), key=lambda el: getattr(el, 'layer', 0))
        for r in sorted_roots: r.draw(screen)

class GGroup:
    def __init__(self, *objs):
        self.objs = list(objs)

    def add(self, *objs):
        self.objs.extend(objs)
        return self

    def remove(self, *objs):
        for o in objs:
            if o in self.objs:
                self.objs.remove(o)
        return self

    def do(self, method, *args, **kwargs):
        for o in self.objs:
            getattr(o, method)(*args, **kwargs)
        return self

    def set(self, **kwargs):
        for o in self.objs: o.set(**kwargs)
        return self

    def anim(self, attr, end_val, duration):
        for o in self.objs: o.anim(attr, end_val, duration)
        return self

    def setup_physics(self, mode="2d"):
        for o in self.objs: o.setup_physics(mode)
        return self

    def setup_controls(self, mapping, speed=200, jump=400, lock_rotation=True):
        for o in self.objs: o.setup_controls(mapping, speed, jump, lock_rotation)
        return self

    def setup_camera(self, mode="dynamic", sway_amp=0, sway_speed=0, shake_amp=0, shake_dur=0):
        if self.objs: self.objs[0].setup_camera(mode, sway_amp, sway_speed, shake_amp, shake_dur)
        return self

    def set_bullet(self, angle, speed):
        for o in self.objs: o.set_bullet(angle, speed)
        return self

    def update(self, dt, resources=None):
        for o in list(self.objs): o.update(dt, resources)

    def draw(self, screen, camera_offset=None, resources=None):
        for o in list(self.objs): o.draw(screen, camera_offset, resources)

class ObjectManager:
    def __init__(self, engine=None):
        self.engine = engine
        self.groups = {}
        self.loose_objs = []
        self.prefabs = {}

    def create(self, x, y, w, h, layer=0, physics=False, body_type=pymunk.Body.KINEMATIC, shape_type="rect", hitbox_size=None):
        spc = self.engine.physics_space if (self.engine and physics) else None
        o = GObj(x, y, w, h, layer, spc, body_type, shape_type, hitbox_size)
        o.engine = self.engine
        self.loose_objs.append(o)
        return o

    def create_part(self, p_type, x, y, w, h, layer=0, shape_type="rect", hitbox_size=None):
        b_type = pymunk.Body.KINEMATIC
        if p_type == "static": b_type = pymunk.Body.STATIC
        elif p_type in ["entity", "bullet"]: b_type = pymunk.Body.DYNAMIC
        o = self.create(x, y, w, h, layer, physics=True, body_type=b_type, shape_type=shape_type, hitbox_size=hitbox_size)
        setattr(o, 'part_type', p_type)
        return o

    def detach(self, obj):
        if obj in self.loose_objs:
            self.loose_objs.remove(obj)
        for g in self.groups.values():
            g.remove(obj)
        if hasattr(obj, "release_physics"):
            obj.release_physics()

    def remove(self, obj):
        obj.destroy()
        return self

    def register_prefab(self, name, obj):
        self.prefabs[name] = obj
        self.detach(obj)
        return self

    def spawn(self, prefab_name, x, y):
        if prefab_name not in self.prefabs:
            if self.engine: self.engine.log(f"PREFAB: '{prefab_name}' not found", (255, 100, 50))
            return None
        new_obj = self.prefabs[prefab_name].clone()
        new_obj.teleport(x, y)
        if new_obj.body:
            new_obj.body.velocity = (0, 0)
            new_obj.body.angular_velocity = 0
        if new_obj not in self.loose_objs:
            self.loose_objs.append(new_obj)
        return new_obj

    def group(self, name, *objs):
        if name not in self.groups:
            self.groups[name] = GGroup(*objs)
        else:
            self.groups[name].add(*objs)
        return self.groups[name]

    def _all(self):
        objs = []
        for g in self.groups.values():
            objs.extend(g.objs)
        objs.extend(self.loose_objs)
        return list(dict.fromkeys(objs))

    def update(self, dt):
        res = self.engine.resources if self.engine else None
        objs = self._all()
        for o in objs:
            if getattr(o, "alive", True):
                o.update(dt, res)
        for o in objs:
            if not getattr(o, "alive", True):
                self.detach(o)

    def draw(self, screen, camera=None, resources=None):
        cam_off = camera.offset if camera else None
        objs = [o for o in self._all() if getattr(o, "alive", True)]
        objs.sort(key=lambda o: getattr(o, 'layer', 0))
        for o in objs:
            o.draw(screen, cam_off, resources)

class SDKEngine:
    DEFAULT_CFG = {
        "debug": True, "width": 800, "height": 600, "fps": 60,
        "gravity": 900, "title": "SDK-Engine", "smoothing": False
    }

    def __init__(self):
        self.logs = []
        self.max_logs = 35
        self._log_cache = {}
        self._reported_errors = set()
        self.events = {}
        self._in_log = False
        self._current_lib = None
        self._patches = {}
        self._added = {}
        self.libs = {}
        self._lib_order = []
        self.libs_dir = "libs"
        self.targets = {}
        self.cache_dir = "cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        log_filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.current_log_file = os.path.join(self.cache_dir, log_filename)
        self.log(f"Booting {ENGINE_NAME}...", (150, 255, 255))
        self.setup_env()
        self.cfg = self.load_cfg("config.cfg")
        self.validate_cfg()
        pygame.init()
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except pygame.error as e:
            self.log(f"AUDIO Error: {e}", (255, 50, 50))
        self.is_fullscreen = False
        self.window_mode_size = (int(self.cfg_num("width", 800)), int(self.cfg_num("height", 600)))
        win_title = str(self.cfg.get("title", "SDK-Engine"))
        self.set_window(self.window_mode_size[0], self.window_mode_size[1], win_title, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("Consolas", 16)

        self.physics_space = pymunk.Space()
        self.physics_space.gravity = (0, self.cfg_num("gravity", 900))

        self.audio = {
            "sounds": {},
            "load": lambda *a, **k: self.load_sound(*a, **k),
            "play": lambda *a, **k: self.play_sound(*a, **k),
            "generate": lambda *a, **k: self.generate_sound(*a, **k)
        }
        self.resources = ResourceManager()
        self.resources.engine = self
        self.camera = Camera(*self.screen.get_size())
        self.objects = ObjectManager(self)
        self.ui = UIManager(self)
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
        self.math = {
            "lerp": lambda a, b, t: a + (b - a) * t,
            "dist": lambda x1, y1, x2, y2: math.sqrt((x2-x1)**2 + (y2-y1)**2),
            "angle": lambda x1, y1, x2, y2: math.atan2(y2-y1, x2-x1),
            "clamp": lambda v, lo, hi: max(lo, min(v, hi)),
            "sin_wave": lambda amp, freq, t: amp * math.sin(freq * t),
            "trajectory": lambda x0, y0, v, ang, t, g=900: (x0 + v * math.cos(ang) * t, y0 + v * math.sin(ang) * t + 0.5 * g * t**2),
            "exp_decay": lambda a, b, decay, dt: b + (a - b) * math.exp(-decay * dt)
        }
        self.on("update", lambda s: self._update_camera(s), priority=100)
        self.on("update", lambda s: self.objects.update(s["dt"]))
        self.on("update", lambda s: self.ui.update(s["dt"]))
        self.on("draw", lambda s: self.objects.draw(s["screen"], s["camera"], s["resources"]))
        self.on("draw", lambda s: self.ui.draw(s["screen"]))
        self.targets = {
            "engine": self, "input": self.input, "camera": self.camera, "objects": self.objects,
            "ui": self.ui, "resources": self.resources,
            "SDKEngine": SDKEngine, "InputManager": InputManager, "ResourceManager": ResourceManager,
            "Camera": Camera, "Anim": Anim, "GObj": GObj, "GGroup": GGroup, "ObjectManager": ObjectManager,
            "UIElement": UIElement, "UIButton": UIButton, "UIInput": UIInput, "UIManager": UIManager
        }
        self.load_libs()

    def _update_camera(self, s):
        self.camera.update(s["dt"])
        self.input.refresh_world(self.camera.offset)

    def cfg_num(self, key, default):
        v = self.cfg.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return default
        return v

    def validate_cfg(self):
        needs_save = False
        for k, v in self.DEFAULT_CFG.items():
            if k not in self.cfg:
                self.log(f"CFG: Missing '{k}' parameter, set to default ({v})", (255, 255, 50))
                self.cfg[k] = v
                needs_save = True
        if needs_save:
            self.save_cfg()

    def set_window(self, w, h, title=None, flags=0):
        if title is None: title = self.cfg.get("title", "SDK-Engine")
        self.screen = pygame.display.set_mode((int(w), int(h)), flags)
        pygame.display.set_caption(str(title))
        self._refresh_screen()
        self.log(f"Window: {int(w)}x{int(h)}, Title: '{title}'", (200, 255, 200))

    def _refresh_screen(self):
        if hasattr(self, "state"):
            self.state["screen"] = self.screen
        if hasattr(self, "camera"):
            self.camera.size = pygame.math.Vector2(self.screen.get_size())

    def toggle_fullscreen(self):
        if not self.is_fullscreen:
            self.window_mode_size = self.screen.get_size()
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self.window_mode_size, pygame.RESIZABLE)
        self._refresh_screen()

    def log(self, text, color=(255, 255, 255)):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_string = f"[{timestamp}] {text}"
        self.logs.append((log_string, tuple(color)))
        if len(self.logs) > self.max_logs: self.logs.pop(0)
        try:
            print(log_string)
        except Exception:
            pass
        try:
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(log_string + "\n")
        except OSError:
            pass
        if not self._in_log:
            self._in_log = True
            try:
                self.emit("log", {"text": log_string, "color": tuple(color)})
            finally:
                self._in_log = False

    def setup_env(self):
        if not os.path.exists("mods"): os.makedirs("mods")
        if not os.path.exists("assets"): os.makedirs("assets")
        if not os.path.exists(self.libs_dir): os.makedirs(self.libs_dir)
        if not os.path.exists("config.cfg"):
            self._write_cfg("config.cfg", self.DEFAULT_CFG)
            self.log("I/O: Generated config.cfg", (100, 255, 100))

    def load_cfg(self, path):
        d = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = [x.strip() for x in line.split("=", 1)]
                    k = k.lower()
                    if v.lower() in ["true", "false"]: v = v.lower() == "true"
                    else:
                        try: v = float(v) if "." in v else int(v)
                        except ValueError: pass
                    d[k] = v
        except Exception as e: self.log(f"CFG Error: {e}", (255, 50, 50))
        return d

    @staticmethod
    def _write_cfg(path, data):
        with open(path, "w", encoding="utf-8") as f:
            for k, v in data.items():
                if isinstance(v, bool): f.write(f"{k} = {'true' if v else 'false'}\n")
                else: f.write(f"{k} = {v}\n")

    def save_cfg(self):
        try:
            self._write_cfg("config.cfg", self.cfg)
            self.log("CFG: Saved", (100, 255, 100))
        except OSError as e:
            self.log(f"CFG Error: {e}", (255, 50, 50))

    def load_sound(self, name, path):
        if not pygame.mixer.get_init():
            return
        if not os.path.isfile(path):
            path = self.resources._find(os.path.basename(path)) or path
        try:
            sound = pygame.mixer.Sound(path)
            self.audio["sounds"][name] = sound
        except Exception as e: self.log(f"AUDIO Error: {e}", (255, 50, 50))

    def play_sound(self, name, volume=1.0):
        sound = self.audio["sounds"].get(name)
        if sound is None:
            return None
        sound.set_volume(volume)
        return sound.play()

    def generate_sound(self, name, freq=440, duration=0.5, volume=0.5, wave_type="sine"):
        try:
            sample_rate = 44100
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            wave = np.sin(freq * t * 2 * np.pi) if wave_type == "sine" else np.sign(np.sin(freq * t * 2 * np.pi))
            sound_array = np.zeros((len(wave), 2), dtype=np.int16)
            sound_array[:, 0] = wave * volume * 32767
            sound_array[:, 1] = wave * volume * 32767
            sound = pygame.sndarray.make_sound(sound_array)
            self.audio["sounds"][name] = sound
            return sound
        except Exception as e:
            self.log(f"AUDIO Error: {e}", (255, 50, 50))
            return None

    def on(self, name, func, priority=0, once=False):
        if name not in self.events: self.events[name] = []
        self.events[name].append({"func": func, "prio": priority, "once": once, "owner": self._current_lib})
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

    def _import_lib(self, mod_name, path, locations):
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
            spec = importlib.util.spec_from_file_location(mod_name, path, submodule_search_locations=locations)
            m = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = m
            spec.loader.exec_module(m)
            return m
        except Exception as e:
            sys.modules.pop(mod_name, None)
            self.log(f"LIB Error [{mod_name}]: {e}", (255, 50, 50))
            traceback.print_exc()
            return None

    def load_libs(self):
        if not os.path.isdir(self.libs_dir): return
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
                found.append((entry, init_file, [os.path.abspath(full)]))
            elif entry.endswith(".py"):
                if os.path.getsize(full) == 0:
                    self.log(f"I/O: Lib '{entry}' is empty, skipping", (255, 100, 50))
                    continue
                found.append((entry[:-3], full, None))
            else:
                self.log(f"I/O: Unknown file type '{entry}' in libs ignored", (200, 150, 50))
        pending = {}
        for mod_name, path, locations in found:
            if any(i["mod_name"] == mod_name for i in self.libs.values()):
                continue
            m = self._import_lib(mod_name, path, locations)
            if m is None:
                continue
            lib_name = str(getattr(m, "NAME", mod_name))
            if lib_name in self.libs or lib_name in pending:
                self.log(f"LIB Error [{lib_name}]: duplicate library name", (255, 50, 50))
                continue
            pending[lib_name] = {
                "module": m, "mod_name": mod_name, "version": str(getattr(m, "VERSION", "?")),
                "requires": [str(r) for r in getattr(m, "REQUIRES", [])],
                "priority": getattr(m, "PRIORITY", 0), "loaded": False
            }
        state = {}
        order = []

        def visit(n, stack):
            st = state.get(n)
            if st == "done": return True
            if st == "fail": return False
            if n in stack:
                self.log(f"LIB Error [{n}]: circular dependency", (255, 50, 50))
                state[n] = "fail"
                return False
            ok = True
            for dep in pending[n]["requires"]:
                if dep in self.libs and self.libs[dep]["loaded"]:
                    continue
                if dep not in pending:
                    self.log(f"LIB Error [{n}]: missing dependency '{dep}'", (255, 50, 50))
                    ok = False
                elif not visit(dep, stack + [n]):
                    self.log(f"LIB Error [{n}]: dependency '{dep}' failed", (255, 50, 50))
                    ok = False
            state[n] = "done" if ok else "fail"
            if ok: order.append(n)
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
                sys.modules.pop(info["mod_name"], None)
                self.log(f"LIB Error [{n}]: init failed ({e})", (255, 50, 50))
                traceback.print_exc()
            finally:
                self._current_lib = None
        if found:
            self.log(f"LIBS: {loaded}/{len(found)} loaded", (150, 255, 255))

    def _drop_handlers(self, owner):
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
        sys.modules.pop(info["mod_name"], None)
        return True

    def unload_libs(self):
        for n in reversed(list(self._lib_order)):
            if n in self.libs:
                self.unload_lib(n)

    def load_mods(self):
        if not os.path.exists("mods"): return
        files = sorted(os.listdir("mods"))
        for fn in files:
            full_path = os.path.join("mods", fn)
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
                if hasattr(m, "init"): m.init(self)
                self.log(f"MOD: Injected {name}", (80, 255, 10))
            except Exception as e:
                self.log(f"MOD Error [{name}]: {e}", (255, 50, 50))
                traceback.print_exc()

    def render_ui(self):
        if not self.cfg.get("debug", True): return
        for i, (txt, col) in enumerate(self.logs):
            key = (txt, col)
            surf = self._log_cache.get(key)
            if surf is None:
                if len(self._log_cache) > 256:
                    self._log_cache.clear()
                surf = self.font.render(txt, True, col)
                self._log_cache[key] = surf
            self.screen.blit(surf, (10, 10 + i * 18))

    def _ui_dispatch_input_click(self, mpos):
        def walk(el):
            if not el.visible: return
            if isinstance(el, UIInput):
                pos = el.get_real_pos()
                sz = el.size * el.scale_val
                if pygame.Rect(pos.x, pos.y, sz.x, sz.y).collidepoint(mpos.x, mpos.y):
                    el.activate()
                else:
                    el.deactivate()
            for child in list(el.children): walk(child)
        for root in list(self.ui.roots.values()): walk(root)

    def _ui_dispatch_input_event(self, event):
        def walk(el):
            if isinstance(el, UIInput) and el._active: el.handle_event(event)
            for child in list(el.children): walk(child)
        for root in list(self.ui.roots.values()): walk(root)

    def _ui_dispatch_click(self, element, mpos):
        if not element.visible: return False
        pos = element.get_real_pos()
        sz = element.size * element.scale_val
        if not pygame.Rect(pos.x, pos.y, sz.x, sz.y).collidepoint(mpos.x, mpos.y):
            return False
        for child in reversed(list(element.children)):
            if self._ui_dispatch_click(child, mpos):
                return True
        if element.on_click and not isinstance(element, UIInput):
            element.on_click()
            return True
        return bool(isinstance(element, UIInput))

    def run(self):
        self.load_mods()
        physics_steps = 2
        fps_cap = max(0, int(self.cfg_num("fps", 60)))
        try:
            while self.state["running"]:
                dt = min(self.clock.tick(fps_cap) / 1000.0, 0.25)
                self.state["dt"] = dt
                self.state["time"] += dt
                sub_dt = min(dt, 0.05) / physics_steps
                for _ in range(physics_steps):
                    self.physics_space.step(sub_dt)
                for e in pygame.event.get():
                    if e.type == pygame.QUIT:
                        self.state["running"] = False
                    elif e.type == pygame.VIDEORESIZE:
                        if not self.is_fullscreen:
                            surface = pygame.display.get_surface()
                            if surface is not None:
                                self.screen = surface
                            self.window_mode_size = self.screen.get_size()
                            self._refresh_screen()
                    elif e.type == pygame.KEYDOWN:
                        if e.key == pygame.K_F11:
                            self.toggle_fullscreen()
                        self._ui_dispatch_input_event(e)
                    elif e.type == pygame.MOUSEBUTTONDOWN:
                        mpos = pygame.math.Vector2(e.pos)
                        for root in sorted(self.ui.roots.values(), key=lambda el: el.layer, reverse=True):
                            if self._ui_dispatch_click(root, mpos):
                                break
                        self._ui_dispatch_input_click(mpos)
                    self.emit("event", e)

                self.input.update(self.camera.offset)
                self.emit("update")
                self.screen.fill((10, 10, 15))
                self.emit("draw")
                self.render_ui()
                pygame.display.flip()
        finally:
            self.unload_libs()
            pygame.quit()

if __name__ == "__main__":
    SDKEngine().run()