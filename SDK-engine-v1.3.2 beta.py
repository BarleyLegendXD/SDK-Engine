import sys
import os
import importlib.util

def _chk():
    m = []
    for l in ['pygame', 'numpy', 'pymunk']:
        if importlib.util.find_spec(l) is None: m.append(l)
    if m:
        print(f"Missing libraries: {', '.join(m)}")
        print("Press Enter to exit...")
        input()
        sys.exit(1)
_chk()

import pygame
import datetime
import math
import socket
import threading
import json
import numpy as np
import pymunk
import random
import weakref

class InputManager:
    def __init__(self):
        self.keys = []
        self.keys_prev = []
        self.mouse = [False] * 5
        self.mouse_prev = [False] * 5
        self.mouse_pos = pygame.math.Vector2(0, 0)
        self.world_mouse_pos = pygame.math.Vector2(0, 0)
        self.binds = []

    def _get_codes(self, k):
        if isinstance(k, int): return [k]
        k = str(k).upper()
        m = {"UP": pygame.K_UP, "DOWN": pygame.K_DOWN, "LEFT": pygame.K_LEFT, "RIGHT": pygame.K_RIGHT, "SPACE": pygame.K_SPACE, "ENTER": pygame.K_RETURN, "ESC": pygame.K_ESCAPE, "LSHIFT": pygame.K_LSHIFT, "RSHIFT": pygame.K_RSHIFT, "TAB": pygame.K_TAB}
        res = []
        if k in m: res.append(m[k])
        ru_to_en = {'Й': 'Q', 'Ц': 'W', 'У': 'E', 'К': 'R', 'Е': 'T', 'Н': 'Y', 'Г': 'U', 'Ш': 'I', 'Щ': 'O', 'З': 'P', 'Х': 'LEFTBRACKET', 'Ъ': 'RIGHTBRACKET', 'Ф': 'A', 'Ы': 'S', 'В': 'D', 'А': 'F', 'П': 'G', 'Р': 'H', 'О': 'J', 'Л': 'K', 'Д': 'L', 'Ж': 'SEMICOLON', 'Э': 'QUOTE', 'Я': 'Z', 'Ч': 'X', 'С': 'C', 'М': 'V', 'И': 'B', 'Т': 'N', 'Ь': 'M', 'Б': 'COMMA', 'Ю': 'PERIOD'}
        en_k = ru_to_en.get(k, k)
        try:
            res.append(getattr(pygame, f"K_{en_k.lower()}"))
        except AttributeError:
            pass
        return res

    def check_custom(self, k_str):
        if not self.keys: return False
        for c in self._get_codes(k_str):
            if c < len(self.keys) and self.keys[c]: return True
        return False

    def check_custom_down(self, k_str):
        if not self.keys or not self.keys_prev: return False
        for c in self._get_codes(k_str):
            if c < len(self.keys) and c < len(self.keys_prev) and self.keys[c] and not self.keys_prev[c]: return True
        return False

    def bind_func(self, k_str, func):
        self.binds.append((k_str, func))

    def update(self, camera_offset=None):
        self.keys_prev = list(self.keys) if self.keys else []
        self.keys = pygame.key.get_pressed()
        self.mouse_prev = list(self.mouse)
        self.mouse = pygame.mouse.get_pressed(num_buttons=5)
        self.mouse_pos = pygame.math.Vector2(pygame.mouse.get_pos())
        
        if camera_offset:
            self.world_mouse_pos = self.mouse_pos + camera_offset
        else:
            self.world_mouse_pos = pygame.math.Vector2(self.mouse_pos)

        for k_str, func in self.binds:
            if self.check_custom_down(k_str):
                func()

    def key(self, k):
        if not self.keys: return False
        return self.keys[k]

    def key_down(self, k):
        if not self.keys or not self.keys_prev: return False
        return self.keys[k] and not self.keys_prev[k]

    def key_up(self, k):
        if not self.keys or not self.keys_prev: return False
        return not self.keys[k] and self.keys_prev[k]

    def mouse_btn(self, b):
        return self.mouse[b]

    def mouse_down(self, b):
        return self.mouse[b] and not self.mouse_prev[b]

    def mouse_up(self, b):
        return not self.mouse[b] and self.mouse_prev[b]

class ResourceManager:
    def __init__(self):
        self.images = {}
        self.anims = {}
        self.engine = None
        self._missing = set()

    def load_img(self, name, path, scale=None):
        if name in self.images:
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
                self.engine.log(f"WARN: Asset not found: {path}", (255, 150, 50))
            return
        try:
            img = pygame.image.load(resolved_path).convert_alpha()
            if scale:
                is_smooth = self.engine.cfg.get("smoothing", False) if self.engine else False
                if is_smooth:
                    img = pygame.transform.smoothscale(img, scale)
                else:
                    img = pygame.transform.scale(img, scale)
            self.images[name] = img
        except Exception as e:
            if self.engine: self.engine.log(f"ERR: {e}", (255, 50, 50))

    def load_ui(self, name):
        target = f"{name}.json"
        path = None
        if os.path.exists("assets"):
            for root, _, files in os.walk("assets"):
                if target in files:
                    path = os.path.join(root, target)
                    break
        if not path: return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return None

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

    def follow(self, target):
        self.target = target
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
        if self.target:
            lerp_factor = max(0.0, min(5 * dt, 1.0))
            self.pos = self.pos.lerp(self.target.pos - self.size / 2, lerp_factor)
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
        if self.duration <= 0:
            t = 1.0
        else:
            t = max(0.0, min(self.time / self.duration, 1.0))
        if isinstance(self.start_val, pygame.math.Vector2):
            if t >= 1.0:
                setattr(self.target, self.attr, pygame.math.Vector2(self.end_val.x, self.end_val.y))
            else:
                setattr(self.target, self.attr, self.start_val.lerp(self.end_val, t))
        else:
            setattr(self.target, self.attr, self.start_val + (self.end_val - self.start_val) * t)
        if t >= 1.0: 
            self.done = True

class GObj:
    def __init__(self, x, y, w, h, layer=0, space=None, body_type=pymunk.Body.KINEMATIC, shape_type="rect", hitbox_size=None):
        self._engine_ref = None
        self.pos = pygame.math.Vector2(x, y)
        self.size = pygame.math.Vector2(w, h)
        self.layer = layer
        self.color = (255, 255, 255)
        self.anims = []
        self.custom_updates = []
        self.components = []
        self.texture_name = None
        self.anim_name = None
        self.anim_timer = 0.0
        self.anim_idx = 0
        self.space = space
        self.body = None
        self.shape = None
        self.physics_mode = "2d"
        self.anchor = "topleft"
        self._surf_cache = None
        self._surf_cache_key = None
        if self.space:
            mass = 1
            hx, hy = hitbox_size if hitbox_size else (w, h)
            if shape_type == "rect":
                moment = pymunk.moment_for_box(mass, (hx, hy))
            else:
                moment = pymunk.moment_for_circle(mass, 0, hx / 2)
            self.body = pymunk.Body(mass, moment, body_type)
            self.body.position = (x, y)
            if shape_type == "rect":
                self.shape = pymunk.Poly.create_box(self.body, (hx, hy))
            elif shape_type == "circle":
                self.shape = pymunk.Circle(self.body, hx / 2)
            self.space.add(self.body, self.shape)

    @property
    def engine(self):
        return self._engine_ref() if self._engine_ref is not None else None

    @engine.setter
    def engine(self, value):
        self._engine_ref = weakref.ref(value) if value is not None else None

    def attr(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    at = attr

    def bind_camera(self, **settings):
        if not self.engine: return self
        self.engine.camera.follow(self)
        for k, v in settings.items():
            if hasattr(self.engine.camera, k):
                setattr(self.engine.camera, k, v)
        return self

    def bind_input(self, mode="rpg", mapping=None, **settings):
        phys_mode = "rpg" if mode in ["rpg", False, "none"] else "2d"
        self.setup_physics(phys_mode)
        if mapping is None:
            mapping = {"up": "W", "down": "S", "left": "A", "right": "D", "jump": "SPACE"}
        self.setup_controls(mapping, speed=settings.get("speed", 200), jump=settings.get("jump", 400))
        return self

    def set(self, **kwargs):
        for k, v in kwargs.items():
            if k in ['pos', 'size'] and isinstance(v, (tuple, list)):
                v = pygame.math.Vector2(v)
            elif k == 'angle':
                if self.body:
                    self.body.angle = math.radians(v)
            elif k == 'texture_name':
                if self.engine and self.engine.resources:
                    missing_cache = getattr(self.engine.resources, '_missing', set())
                    if v not in self.engine.resources.images and v not in missing_cache:
                        before = set(self.engine.resources.images.keys())
                        self.engine.resources.load_img(v, v, scale=(int(self.size.x), int(self.size.y)))
                        if v not in self.engine.resources.images:
                            missing_cache.add(v)
                            self.engine.resources._missing = missing_cache
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

    def setup_physics(self, mode="2d"):
        self.physics_mode = mode
        if self.body and mode == "rpg":
            def z_grav(b, g, d, dt):
                pymunk.Body.update_velocity(b, (0, 0), d, dt)
            self.body.velocity_func = z_grav
        return self

    def setup_controls(self, mapping, speed=200, jump=400):
        def m(dt):
            if not self.engine: return
            vx, vy = 0, 0
            inp = self.engine.input
            is_jump = False
            for d_name, k_str in mapping.items():
                if inp.check_custom(k_str):
                    if d_name == "up": vy -= 1
                    if d_name == "down": vy += 1
                    if d_name == "left": vx -= 1
                    if d_name == "right": vx += 1
                    if d_name == "jump": is_jump = True

            mode = getattr(self, "physics_mode", "2d")
            
            if mode == "rpg":
                if vx != 0 or vy != 0:
                    l = math.hypot(vx, vy)
                    vx, vy = (vx/l)*speed, (vy/l)*speed
                if self.body and self.body.body_type in (pymunk.Body.KINEMATIC, pymunk.Body.DYNAMIC):
                    self.body.velocity = (vx, vy)
                else:
                    self.pos.x += vx * dt
                    self.pos.y += vy * dt
            else:
                if vx != 0:
                    vx = (vx / abs(vx)) * speed
                if self.body and self.body.body_type in (pymunk.Body.KINEMATIC, pymunk.Body.DYNAMIC):
                    curr_vx, curr_vy = self.body.velocity
                    if is_jump or vy < 0:
                        curr_vy = -jump
                    self.body.velocity = (vx, curr_vy)
                else:
                    self.pos.x += vx * dt
                    if is_jump or vy < 0:
                        self.pos.y -= jump * dt
        self.add_update(m)
        return self

    def setup_camera(self, mode="dynamic", sway_amp=0, sway_speed=0, shake_amp=0, shake_dur=0):
        if not self.engine: return self
        if mode == "dynamic":
            self.engine.camera.follow(self)
        elif mode == "static":
            self.engine.camera.target = None
            self.engine.camera.pos = pygame.math.Vector2(self.pos.x - self.engine.camera.size.x / 2, self.pos.y - self.engine.camera.size.y / 2)
        if sway_amp > 0 and sway_speed > 0:
            self.engine.camera.sway(sway_amp, sway_speed)
        if shake_amp > 0 and shake_dur > 0:
            self.engine.camera.shake(shake_amp, shake_dur)
        return self

    def set_bullet(self, angle, speed):
        if self.body:
            self.body.velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
        return self

    def is_hovered(self, inp, camera_offset=None):
        off_x = camera_offset.x if camera_offset else 0
        off_y = camera_offset.y if camera_offset else 0
        mx, my = inp.mouse_pos.x, inp.mouse_pos.y
        x = self.pos.x - off_x
        y = self.pos.y - off_y
        return x <= mx <= x + self.size.x and y <= my <= y + self.size.y

    def is_clicked(self, inp, button=0, camera_offset=None):
        return self.is_hovered(inp, camera_offset) and inp.mouse_down(button)

    def clone(self):
        new_obj = self.__class__(self.pos.x, self.pos.y, self.size.x, self.size.y, self.layer, None)
        new_obj.engine = self.engine

        skip = ['pos', 'body', 'shape', 'space', '_engine_ref', 'engine', 'anims', 'custom_updates', 'components']
        for k, v in self.__dict__.items():
            if k not in skip:
                setattr(new_obj, k, v)

        new_obj.custom_updates = list(self.custom_updates)
        new_obj.components = [c.clone(new_obj) if hasattr(c, "clone") else c for c in self.components]

        if self.body and self.space:
            new_obj.space = self.space
            mass = self.body.mass
            hx, hy = self.size.x, self.size.y
            if isinstance(self.shape, pymunk.Poly):
                moment = pymunk.moment_for_box(mass, (hx, hy))
                new_obj.body = pymunk.Body(mass, moment, self.body.body_type)
                new_obj.body.position = (self.pos.x, self.pos.y)
                new_obj.body.angle = self.body.angle
                new_obj.shape = pymunk.Poly.create_box(new_obj.body, (hx, hy))
            elif isinstance(self.shape, pymunk.Circle):
                r = self.shape.radius
                moment = pymunk.moment_for_circle(mass, 0, r)
                new_obj.body = pymunk.Body(mass, moment, self.body.body_type)
                new_obj.body.position = (self.pos.x, self.pos.y)
                new_obj.body.angle = self.body.angle
                new_obj.shape = pymunk.Circle(new_obj.body, r)
            if new_obj.body and new_obj.shape:
                new_obj.shape.friction = self.shape.friction
                new_obj.shape.elasticity = self.shape.elasticity
                self.space.add(new_obj.body, new_obj.shape)
                new_obj.setup_physics(self.physics_mode)

        if hasattr(self, 'part_type'):
            new_obj.part_type = self.part_type

        if self.engine:
            self.engine.objects.loose_objs.append(new_obj)

        return new_obj
    
    def update(self, dt, resources=None):
        for c in self.components: c.update(self, dt)
        for a in self.anims[:]:
            a.update(dt)
            if a.done: 
                self.anims.remove(a)
        
        for uf in self.custom_updates:
            uf(dt)

        if self.body:
            if self.body.body_type in (pymunk.Body.DYNAMIC, pymunk.Body.KINEMATIC):
                self.pos.x = self.body.position.x
                self.pos.y = self.body.position.y
            else:
                self.body.position = (self.pos.x, self.pos.y)
        if self.anim_name and resources and self.anim_name in resources.anims:
            self.anim_timer += dt
            anim_data = resources.anims[self.anim_name]
            if self.anim_timer >= anim_data["delay"]:
                self.anim_timer = 0
                self.anim_idx = (self.anim_idx + 1) % len(anim_data["frames"])

    def _rebuild_surf(self):
        w, h = int(self.size.x), int(self.size.y)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if hasattr(self, 'gradient') and self.gradient:
            c1, c2 = self.gradient
            for y in range(h):
                ratio = y / h
                col = [int(c1[i] + (c2[i] - c1[i]) * ratio) for i in range(3)]
                pygame.draw.line(surf, col, (0, y), (w, y))
        else:
            surf.fill(self.color)
        self._surf_cache = surf
        self._surf_cache_key = (w, h, self.color, getattr(self, 'gradient', None))

    def draw(self, screen, camera_offset=None, resources=None):
        off_x = camera_offset.x if camera_offset else 0
        off_y = camera_offset.y if camera_offset else 0
        ang = math.degrees(self.body.angle) if self.body else getattr(self, 'angle', 0)

        anchor = getattr(self, 'anchor', 'topleft')
        if anchor == 'center' or self.body:
            cx = self.pos.x - off_x
            cy = self.pos.y - off_y
        else:
            cx = self.pos.x - off_x + self.size.x / 2
            cy = self.pos.y - off_y + self.size.y / 2

        surf = None
        if getattr(self, 'anim_name', None) and resources and self.anim_name in resources.anims:
            surf = resources.anims[self.anim_name]["frames"][self.anim_idx]
        elif getattr(self, 'texture_name', None) and resources and self.texture_name in resources.images:
            surf = resources.images[self.texture_name]
        elif getattr(self, 'shimmer', False):
            t = pygame.time.get_ticks() * 0.005
            r, g, b = int(127 + 127 * math.sin(t)), int(127 + 127 * math.sin(t + 2)), int(127 + 127 * math.sin(t + 4))
            shimmer_surf = pygame.Surface((int(self.size.x), int(self.size.y)), pygame.SRCALPHA)
            shimmer_surf.fill((r, g, b))
            surf = shimmer_surf
        else:
            cache_key = (int(self.size.x), int(self.size.y), self.color, getattr(self, 'gradient', None))
            if self._surf_cache is None or self._surf_cache_key != cache_key:
                self._rebuild_surf()
            surf = self._surf_cache

        if ang != 0:
            surf = pygame.transform.rotate(surf, -ang)

        rect = surf.get_rect(center=(int(cx), int(cy)))
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

    def update(self, dt):
        if not self.visible: return
        for child in self.children: child.update(dt)

    def _rebuild_surf(self):
        sz = self.size * self.scale_val
        w, h = int(sz.x), int(sz.y)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if self.gradient:
            c1, c2 = self.gradient
            for y in range(h):
                r = y / h
                c = [int(c1[i] + (c2[i]-c1[i])*r) for i in range(3)]
                pygame.draw.line(surf, (*c, self.alpha), (0, y), (w, y))
        else:
            surf.fill((*self.color, self.alpha))
        if self.border_color and self.border_width > 0:
            pygame.draw.rect(surf, self.border_color, (0, 0, w, h), self.border_width)
        self._surf_cache = surf
        self._surf_cache_key = (w, h, self.color, self.alpha, self.gradient, self.border_color, self.border_width)

    def draw(self, screen):
        if not self.visible: return
        pos = self.get_real_pos()
        sz = self.size * self.scale_val
        cache_key = (int(sz.x), int(sz.y), self.color, self.alpha, self.gradient, self.border_color, self.border_width)
        if self._surf_cache is None or self._surf_cache_key != cache_key:
            self._rebuild_surf()
        surf = self._surf_cache.copy() if self.text else self._surf_cache
        if self.text and self.engine and self.engine.font:
            t_surf = self.engine.font.render(self.text, True, self.text_color)
            surf.blit(t_surf, (sz.x/2 - t_surf.get_width()/2, sz.y/2 - t_surf.get_height()/2))
        screen.blit(surf, (pos.x, pos.y))
        for child in self.children: child.draw(screen)

class UIButton(UIElement):
    def __init__(self, engine, name, pos=(0,0), size=(100,100), parent=None):
        super().__init__(engine, name, pos, size, parent)
        self.color = (60, 60, 180)
        self.hover_color = (80, 80, 220)
        self.press_color = (40, 40, 140)
        self._base_color = self.color
        self._hovered = False
        self._pressed = False

    def update(self, dt):
        if not self.visible: return
        eng = self.engine
        if eng:
            pos = self.get_real_pos()
            sz = self.size * self.scale_val
            rect = pygame.Rect(pos.x, pos.y, sz.x, sz.y)
            m = eng.input.mouse_pos
            self._hovered = rect.collidepoint(m.x, m.y)
            self._pressed = self._hovered and eng.input.mouse_btn(0)
            if self._pressed:
                self.color = self.press_color
            elif self._hovered:
                self.color = self.hover_color
            else:
                self.color = self._base_color
        for child in self.children: child.update(dt)


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
        self._base_color = self.color

    def update(self, dt):
        if not self.visible: return
        self._cursor_timer += dt
        if self._cursor_timer >= 0.5:
            self._cursor_timer = 0.0
            self._cursor_visible = not self._cursor_visible
        for child in self.children: child.update(dt)

    def activate(self):
        self._active = True
        self.color = self.active_color
        self._surf_cache = None

    def deactivate(self):
        self._active = False
        self.color = self._base_color
        self._surf_cache = None

    def handle_event(self, event):
        if not self._active: return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.deactivate()
            elif event.unicode and event.unicode.isprintable():
                self.value += event.unicode
            self._surf_cache = None

    def draw(self, screen):
        if not self.visible: return
        pos = self.get_real_pos()
        sz = self.size * self.scale_val
        cache_key = (int(sz.x), int(sz.y), self.color, self.alpha, self.gradient, self.border_color, self.border_width)
        if self._surf_cache is None or self._surf_cache_key != cache_key:
            self._rebuild_surf()
        surf = self._surf_cache.copy()
        eng = self.engine
        if eng and eng.font:
            display = self.value if self.value else self.placeholder
            col = self.text_color if self.value else (100, 100, 100)
            cursor_str = "|" if (self._active and self._cursor_visible) else ""
            t_surf = eng.font.render(display + cursor_str, True, col)
            pad = 8
            surf.blit(t_surf, (pad, sz.y/2 - t_surf.get_height()/2))
        screen.blit(surf, (pos.x, pos.y))
        for child in self.children: child.draw(screen)


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
        if el and el.parent and el in el.parent.children:
            el.parent.children.remove(el)

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

    def setup_controls(self, mapping, speed=200, jump=400):
        for o in self.objs: o.setup_controls(mapping, speed, jump)
        return self

    def setup_camera(self, mode="dynamic", sway_amp=0, sway_speed=0, shake_amp=0, shake_dur=0):
        if self.objs: self.objs[0].setup_camera(mode, sway_amp, sway_speed, shake_amp, shake_dur)
        return self

    def set_bullet(self, angle, speed):
        for o in self.objs: o.set_bullet(angle, speed)
        return self

    def update(self, dt, resources=None):
        for o in self.objs: o.update(dt, resources)

    def draw(self, screen, camera_offset=None, resources=None):
        for o in self.objs: o.draw(screen, camera_offset, resources)

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

    def register_prefab(self, name, obj):
        self.prefabs[name] = obj
        return self

    def spawn(self, prefab_name, x, y):
        if prefab_name not in self.prefabs:
            if self.engine: self.engine.log(f"PREFAB: '{prefab_name}' not found", (255, 100, 50))
            return None
        new_obj = self.prefabs[prefab_name].clone()
        new_obj.pos = pygame.math.Vector2(x, y)
        if new_obj.body:
            new_obj.body.position = (x, y)
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

    def update(self, dt):
        res = self.engine.resources if self.engine else None
        for g in self.groups.values(): 
            g.update(dt, res)
        for o in self.loose_objs: 
            o.update(dt, res)

    def draw(self, screen, camera=None, resources=None):
        cam_off = camera.offset if camera else None
        all_objs = []
        for g in self.groups.values():
            all_objs.extend(g.objs)
        all_objs.extend(self.loose_objs)
        all_objs.sort(key=lambda o: getattr(o, 'layer', 0))
        for o in all_objs:
            o.draw(screen, cam_off, resources)

class SDKEngine:
    def __init__(self):
        self.logs = []
        self.max_logs = 35
        self.cache_dir = "cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        log_filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.current_log_file = os.path.join(self.cache_dir, log_filename)
        self.log("Booting SDK-Engine v1.3.1...", (150, 255, 255))
        self.setup_env()
        self.cfg = self.load_cfg("config.cfg")
        self.validate_cfg()
        self.events = {}
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.is_fullscreen = False
        self.window_mode_size = (self.cfg.get("width", 800), self.cfg.get("height", 600))
        win_title = self.cfg.get("title", "SDK-Engine")
        self.set_window(self.window_mode_size[0], self.window_mode_size[1], win_title, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        
        self.font = pygame.font.SysFont("Consolas", 16)
        
        self.physics_space = pymunk.Space()
        self.physics_space.gravity = (0, self.cfg.get("gravity", 900))
        
        self.audio = {
            "sounds": {},
            "load": self.load_sound,
            "play": self.play_sound,
            "generate": self.generate_sound
        }
        self.resources = ResourceManager()
        self.resources.engine = self
        self.camera = Camera(self.window_mode_size[0], self.window_mode_size[1])
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
            "sin_wave": lambda amp, freq, t: amp * math.sin(freq * t),
            "trajectory": lambda x0, y0, v, ang, t, g=900: (x0 + v * math.cos(ang) * t, y0 + v * math.sin(ang) * t + 0.5 * g * t**2),
            "exp_decay": lambda a, b, decay, dt: b + (a - b) * math.exp(-decay * dt)
        }
        self.on("update", lambda s: self.camera.update(s["dt"]), priority=100)
        self.on("update", lambda s: self.objects.update(s["dt"]))
        self.on("update", lambda s: self.ui.update(s["dt"]))
        self.on("draw", lambda s: self.objects.draw(s["screen"], s["camera"], s["resources"]))
        self.on("draw", lambda s: self.ui.draw(s["screen"]))

    def validate_cfg(self):
        required = {
            "width": 800, "height": 600, "fps": 60, "gravity": 900, 
            "title": "SDK-Engine", "debug": True, "smoothing": False
        }
        needs_save = False
        for k, v in required.items():
            if k not in self.cfg:
                self.log(f"CFG: Missing '{k}' parameter, set to default ({v})", (255, 255, 50))
                self.cfg[k] = v
                needs_save = True
        if needs_save:
            self.save_cfg()

    def set_window(self, w, h, title=None, flags=0):
        if title is None: title = self.cfg.get("title", "SDK-Engine")
        self.screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption(title)
        if hasattr(self, 'state'): self.state["screen"] = self.screen
        self.log(f"Window: {w}x{h}, Title: '{title}'", (200, 255, 200))

    def log(self, text, color=(255, 255, 255)):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_string = f"[{timestamp}] {text}"
        self.logs.append((log_string, color))
        if len(self.logs) > self.max_logs: self.logs.pop(0)
        print(log_string)
        try:
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(log_string + "\n")
        except: pass

    def setup_env(self):
        if not os.path.exists("mods"): os.makedirs("mods")
        if not os.path.exists("assets"): os.makedirs("assets")
        if not os.path.exists("config.cfg"):
            with open("config.cfg", "w") as f:
                f.write("debug = true\nwidth = 800\nheight = 600\nfps = 60\ngravity = 900\ntitle = SDK-Engine\n")
            self.log("I/O: Generated config.cfg", (100, 255, 100))

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
                    if isinstance(v, bool): f.write(f"{k} = {'true' if v else 'false'}\n")
                    else: f.write(f"{k} = {v}\n")
            self.log("CFG: Saved", (100, 255, 100))
        except: pass

    def load_sound(self, name, path):
        try:
            sound = pygame.mixer.Sound(path)
            self.audio["sounds"][name] = sound
        except Exception as e: self.log(f"AUDIO Error: {e}", (255, 50, 50))

    def play_sound(self, name, volume=1.0):
        if name in self.audio["sounds"]:
            sound = self.audio["sounds"][name]
            sound.set_volume(volume)
            sound.play()

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
                if sub in self.events[name]:
                    self.events[name].remove(sub)

    def load_mods(self):
        if not os.path.exists("mods"): return
        files = os.listdir("mods")
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
            except Exception as e: self.log(f"MOD Error [{name}]: {e}", (255, 50, 50))

    def render_ui(self):
        if not self.cfg.get("debug", True): return
        for i, (txt, col) in enumerate(self.logs):
            self.screen.blit(self.font.render(txt, True, col), (10, 10 + i*18))

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
            for child in el.children: walk(child)
        for root in self.ui.roots.values(): walk(root)

    def _ui_dispatch_input_event(self, event):
        def walk(el):
            if isinstance(el, UIInput) and el._active: el.handle_event(event)
            for child in el.children: walk(child)
        for root in self.ui.roots.values(): walk(root)

    def _ui_dispatch_click(self, element, mpos):
        if not element.visible: return False
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
        physics_steps = 2
        fps_cap = self.cfg.get("fps", 60)
        fixed_dt = 1.0 / fps_cap
        step_dt = fixed_dt / physics_steps
        while self.state["running"]:
            self.state["dt"] = self.clock.tick(fps_cap) / 1000.0
            self.state["time"] += self.state["dt"]
            for _ in range(physics_steps):
                self.physics_space.step(step_dt)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.state["running"] = False
                elif e.type == pygame.VIDEORESIZE:
                    if not self.is_fullscreen:
                        self.window_mode_size = (e.w, e.h)
                        self.screen = pygame.display.set_mode((e.w, e.h), pygame.RESIZABLE)
                        self.state["screen"] = self.screen
                        self.camera.size = pygame.math.Vector2(e.w, e.h)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F11:
                        self.is_fullscreen = not self.is_fullscreen
                        if self.is_fullscreen:
                            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                        else:
                            self.screen = pygame.display.set_mode(self.window_mode_size, pygame.RESIZABLE)
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
        pygame.quit()

if __name__ == "__main__":
    SDKEngine().run()