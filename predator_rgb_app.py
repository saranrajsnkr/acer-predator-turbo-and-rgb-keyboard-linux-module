#!/usr/bin/env python3
"""
Acer Predator RGB Keyboard Controller — Linux GUI Application

A modern desktop application for controlling the RGB keyboard backlight
on Acer Predator laptops. Provides all hardware and software lighting
modes with full customization through an intuitive graphical interface.

Requirements:
    pip3 install customtkinter
    Kernel module: acer-predator-turbo-and-rgb-keyboard-linux-module

Usage:
    sudo python3 predator_rgb_app.py
"""

import customtkinter as ctk
import threading
import os
import sys
import colorsys
import math
import random
import tkinter as tk
from tkinter import colorchooser
from time import sleep, time

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants & Theme
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAYLOAD_SIZE = 16
CHARACTER_DEVICE = "/dev/acer-gkbbl-0"
PAYLOAD_SIZE_STATIC = 4
CHARACTER_DEVICE_STATIC = "/dev/acer-gkbbl-static-0"
NUM_ZONES = 4

APP_NAME = "Predator RGB Controller"
APP_VERSION = "2.0"

# Premium dark theme palette
ACCENT       = "#00E676"     # Vibrant green
ACCENT_HOVER = "#00C853"
ACCENT_DIM   = "#0A3D1F"
ACCENT_GLOW  = "#00E67633"   # Translucent accent for glow effects

BG_BASE      = "#080B0E"     # Deepest background
BG_SURFACE   = "#111518"     # Surface layer
BG_ELEVATED  = "#1A1F24"     # Elevated cards
BG_HOVER     = "#252B31"     # Hover states

TEXT_HEAD     = "#F0F4F8"     # Headings
TEXT_PRIMARY  = "#CDD5DE"     # Body text
TEXT_DIM      = "#6B7B8D"     # Dimmed labels
TEXT_MUTED    = "#3D4A56"     # Very subtle

BORDER        = "#1E2830"     # Subtle borders
BORDER_ACCENT = "#00E67640"   # Accented border

DANGER        = "#FF5252"
DANGER_HOVER  = "#E04848"
WARNING       = "#FFB300"
INFO          = "#448AFF"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Hardware I/O
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_running = False
_animation_thread = None
_sim_mode = False


def _check_device_access():
    global _sim_mode
    if not os.path.exists(CHARACTER_DEVICE):
        _sim_mode = True
        return
    try:
        with open(CHARACTER_DEVICE, 'rb'):
            _sim_mode = False
    except PermissionError:
        _sim_mode = True


def _write_dynamic(mode, speed, brightness, direction=1, red=0, green=0, blue=0):
    if _sim_mode: return
    payload = [0]*PAYLOAD_SIZE
    payload[0], payload[1], payload[2] = mode, speed, brightness
    payload[3] = 8 if mode == 3 else 0
    payload[4], payload[5], payload[6], payload[7], payload[9] = direction, red, green, blue, 1
    try:
        with open(CHARACTER_DEVICE, 'wb') as f: f.write(bytes(payload))
    except (PermissionError, FileNotFoundError): pass


def _write_static_zone(zone_id, red, green, blue, brightness=100):
    if _sim_mode: return
    ps = [0]*PAYLOAD_SIZE_STATIC
    ps[0], ps[1], ps[2], ps[3] = 1 << (zone_id-1), red, green, blue
    try:
        with open(CHARACTER_DEVICE_STATIC, 'wb') as f: f.write(bytes(ps))
    except (PermissionError, FileNotFoundError): return
    pd = [0]*PAYLOAD_SIZE; pd[2], pd[9] = brightness, 1
    try:
        with open(CHARACTER_DEVICE, 'wb') as f: f.write(bytes(pd))
    except (PermissionError, FileNotFoundError): pass


def _write_all_zones(colors, brightness=100):
    if _sim_mode: return
    for zid in range(1, 5):
        r, g, b = colors[zid-1]
        ps = [0]*PAYLOAD_SIZE_STATIC
        ps[0], ps[1], ps[2], ps[3] = 1 << (zid-1), int(r), int(g), int(b)
        try:
            with open(CHARACTER_DEVICE_STATIC, 'wb') as f: f.write(bytes(ps))
        except (PermissionError, FileNotFoundError): return
    pd = [0]*PAYLOAD_SIZE; pd[2], pd[9] = brightness, 1
    try:
        with open(CHARACTER_DEVICE, 'wb') as f: f.write(bytes(pd))
    except (PermissionError, FileNotFoundError): pass


def _clamp(v, lo=0, hi=255): return max(lo, min(hi, int(v)))
def _hue_to_rgb(h):
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return (int(r*255), int(g*255), int(b*255))
def _smooth_color(prev, curr, a=0.3):
    return (int(prev[0]*(1-a)+curr[0]*a), int(prev[1]*(1-a)+curr[1]*a), int(prev[2]*(1-a)+curr[2]*a))
def _boost_saturation(r, g, b, f=1.5):
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    nr, ng, nb = colorsys.hsv_to_rgb(h, min(1, s*f), min(1, max(0.15, v)))
    return (int(nr*255), int(ng*255), int(nb*255))
def _intensity_to_hue(i):
    if i < 0.5: return 0.6 - (i*2)*0.3
    t = (i-0.5)*2
    if t < 0.7: return 0.3 - (t/0.7)*0.3
    return 1.0 - (1.0-t)/0.3*0.05
def _get_pulse_monitor():
    import subprocess
    try:
        r = subprocess.run(['pactl','get-default-sink'], capture_output=True, text=True, timeout=5)
        if r.returncode == 0: return f"{r.stdout.strip()}.monitor"
    except: pass
    try:
        r = subprocess.run(['pactl','list','short','sources'], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for l in r.stdout.strip().split('\n'):
                if '.monitor' in l:
                    parts = l.split('\t')
                    if len(parts) >= 2: return parts[1]
    except: pass
    return None
def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def rgb_to_hex(r, g, b): return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Software Animation Engines (run in daemon threads)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _anim_rainbow(speed, brt, cb):
    global _running
    h = 0.0
    while _running:
        colors = [_hue_to_rgb((h + z/4) % 1.0) for z in range(4)]
        _write_all_zones(colors, brt); cb(colors)
        h = (h + 0.02) % 1.0; sleep(speed)

def _anim_strobe(r, g, b, freq, brt, cb):
    global _running
    on, off = (r,g,b), (0,0,0)
    while _running:
        _write_all_zones([on]*4, brt); cb([on]*4); sleep(freq)
        if not _running: break
        _write_all_zones([off]*4, 0); cb([off]*4); sleep(freq)

def _anim_police(speed, brt, cb):
    global _running
    R, B, O = (255,0,0), (0,0,255), (0,0,0)
    while _running:
        for cols, br in [([R,R,B,B], brt), ([O]*4, 0), ([B,B,R,R], brt), ([O]*4, 0)]:
            if not _running: break
            _write_all_zones(cols, br); cb(cols)
            sleep(speed if br else speed*0.3)

def _anim_campfire(speed, brt, cb):
    global _running
    palette = [(255,60,0),(255,100,0),(255,140,0),(255,40,0),(255,80,10),(200,30,0),(255,120,20),(255,160,30)]
    while _running:
        colors = [(_clamp(c[0]+random.randint(-20,20)), _clamp(c[1]+random.randint(-15,15)),
                   _clamp(c[2]+random.randint(-5,5))) for c in [random.choice(palette) for _ in range(4)]]
        _write_all_zones(colors, _clamp(brt+random.randint(-30,10),30,100)); cb(colors)
        sleep(speed + random.uniform(-0.03, 0.05))

def _anim_sparkle(speed, brt, cb):
    global _running
    cur = [(0,0,0)]*4
    while _running:
        z = random.randint(0,3)
        cur[z] = (random.randint(100,255), random.randint(100,255), random.randint(100,255))
        _write_all_zones(cur, brt); cb(list(cur)); sleep(speed)
        if not _running: break
        cur[z] = tuple(max(0, c-80) for c in cur[z])

def _anim_gradient(c1, c2, speed, brt, cb):
    global _running
    t = 0.0
    while _running:
        colors = [(_clamp(c1[0]+(c2[0]-c1[0])*((math.sin(t+z*0.8)+1)/2)),
                   _clamp(c1[1]+(c2[1]-c1[1])*((math.sin(t+z*0.8)+1)/2)),
                   _clamp(c1[2]+(c2[2]-c1[2])*((math.sin(t+z*0.8)+1)/2))) for z in range(4)]
        _write_all_zones(colors, brt); cb(colors); t += 0.08; sleep(speed)

def _anim_dualwave(c1, c2, speed, brt, cb):
    global _running
    s = 0
    while _running:
        colors = []
        for z in range(4):
            w = (math.sin((s+z*2)*0.3)+1)/2
            colors.append((_clamp(c1[0]*(1-w)+c2[0]*w), _clamp(c1[1]*(1-w)+c2[1]*w), _clamp(c1[2]*(1-w)+c2[2]*w)))
        _write_all_zones(colors, brt); cb(colors); s += 1; sleep(speed)

def _anim_pulse(r, g, b, speed, brt, cb):
    global _running
    t = 0.0
    while _running:
        i = (math.sin(t)+1)/2
        color = (_clamp(r*i), _clamp(g*i), _clamp(b*i))
        _write_all_zones([color]*4, _clamp(max(brt*i,1),0,100)); cb([color]*4)
        t += 0.1; sleep(speed)

def _anim_ambient(speed, brt, region, sat, smooth, cb):
    global _running
    try: from PIL import ImageGrab
    except ImportError: return
    prev = [(0,0,0)]*4
    while _running:
        try:
            ss = ImageGrab.grab(); w, h = ss.size
            ys = int(h*0.6) if region == "bottom" else (0 if region == "top" else 0)
            ye = h if region == "bottom" else (int(h*0.4) if region == "top" else h)
            sw = w//4
            colors = []
            for z in range(4):
                avg = ss.crop((z*sw, ys, (z+1)*sw if z < 3 else w, ye)).resize((1,1)).getpixel((0,0))
                r, g, b = avg[0], avg[1], avg[2]
                if sat != 1.0: r, g, b = _boost_saturation(r, g, b, sat)
                colors.append((_clamp(r), _clamp(g), _clamp(b)))
            sm = [_smooth_color(prev[i], colors[i], smooth) for i in range(4)]
            prev = sm; _write_all_zones(sm, brt); cb(sm)
        except: pass
        sleep(speed)

def _anim_music(sens, brt, smooth, cb):
    global _running
    try:
        import numpy as np; import pyaudio
    except ImportError: return
    mon = _get_pulse_monitor()
    if not mon: return
    os.environ['PULSE_SOURCE'] = mon
    dn = open(os.devnull, 'w'); oe = os.dup(2); os.dup2(dn.fileno(), 2)
    pa = pyaudio.PyAudio(); os.dup2(oe, 2); dn.close()
    RATE, CHUNK = 44100, 2048
    try: stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
    except: pa.terminate(); return
    pl, pc, pk = 0.0, (0,0,50), 0.01
    try:
        while _running:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                samp = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                rms = np.sqrt(np.mean(samp**2))
                fft = np.abs(np.fft.rfft(samp*np.hanning(len(samp))))/(CHUNK/2)
                fr = RATE/CHUNK
                bass = np.mean(fft[max(1,int(20/fr)):min(CHUNK//2,int(300/fr))+1])
                raw = (rms/32768*0.4 + bass/100*0.6)*sens
                if raw > pk: pk = raw
                else: pk *= 0.995
                pk = max(pk, 0.001)
                n = min(1.0, raw/pk)
                sm = pl*smooth + n*(1-smooth); pl = sm
                hue = _intensity_to_hue(sm)
                cr, cg, cb_ = colorsys.hsv_to_rgb(hue, 0.6+sm*0.4, 0.03+(sm**1.5)*0.97)
                color = _smooth_color(pc, (_clamp(cr*255), _clamp(cg*255), _clamp(cb_*255)), 1-smooth)
                pc = color
                _write_all_zones([color]*4, _clamp(brt*(0.1+sm*0.9), 5, 100)); cb([color]*4)
            except IOError: continue
    finally: stream.stop_stream(); stream.close(); pa.terminate()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Premium GUI Widgets
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class KeyboardPreview(ctk.CTkFrame):
    """Animated visual keyboard zone preview."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.zone_frames = []
        self.zone_labels = []
        # Outer container with accent border glow
        outer = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=20,
                              border_width=1, border_color=BORDER)
        outer.pack(fill="x", padx=4, pady=4)
        # Header row
        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(14, 6))
        ctk.CTkLabel(hdr, text="⌨", font=ctk.CTkFont(size=16)).pack(side="left")
        ctk.CTkLabel(hdr, text="KEYBOARD ZONES", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_DIM).pack(side="left", padx=(8, 0))
        # Zone grid
        grid = ctk.CTkFrame(outer, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(4, 16))
        for i in range(4): grid.columnconfigure(i, weight=1)
        zone_colors = ["#FF4444", "#44FF44", "#4488FF", "#FF44FF"]
        for i in range(4):
            # Zone card
            card = ctk.CTkFrame(grid, fg_color=BG_BASE, corner_radius=12, height=70,
                                 border_width=1, border_color=BORDER)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            card.grid_propagate(False)
            inner = ctk.CTkFrame(card, fg_color=zone_colors[i], corner_radius=10, height=50)
            inner.pack(fill="both", expand=True, padx=4, pady=4)
            lbl = ctk.CTkLabel(inner, text=f"ZONE {i+1}",
                                font=ctk.CTkFont(size=10, weight="bold"),
                                text_color="#000000")
            lbl.pack(expand=True)
            self.zone_frames.append(inner)
            self.zone_labels.append(lbl)

    def update_zones(self, colors):
        for i, (r, g, b) in enumerate(colors):
            hx = rgb_to_hex(r, g, b)
            try:
                self.zone_frames[i].configure(fg_color=hx)
                lum = 0.299*r + 0.587*g + 0.114*b
                self.zone_labels[i].configure(text_color="#000000" if lum > 100 else "#FFFFFF")
            except: pass

    def set_all(self, r, g, b):
        self.update_zones([(r,g,b)]*4)


class ColorButton(ctk.CTkFrame):
    """Premium color picker with swatch preview."""
    def __init__(self, parent, label="Color", color="#FFFFFF", **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.color = color
        row = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=10,
                            border_width=1, border_color=BORDER, height=44)
        row.pack(fill="x"); row.pack_propagate(False)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13),
                      text_color=TEXT_DIM).pack(side="left", padx=14)
        self.swatch = ctk.CTkButton(row, text="", width=32, height=26, corner_radius=6,
                                     fg_color=color, hover_color=color, border_width=2,
                                     border_color=BORDER, command=self._pick)
        self.swatch.pack(side="right", padx=10)
        self.hex_lbl = ctk.CTkLabel(row, text=color.upper(),
                                     font=ctk.CTkFont(size=11, family="Courier"),
                                     text_color=TEXT_MUTED)
        self.hex_lbl.pack(side="right", padx=(0, 4))

    def _pick(self):
        result = colorchooser.askcolor(color=self.color, title="Choose Color")
        if result and result[1]:
            self.color = result[1]
            self.swatch.configure(fg_color=self.color, hover_color=self.color)
            self.hex_lbl.configure(text=self.color.upper())

    def get_rgb(self): return hex_to_rgb(self.color)


class Slider(ctk.CTkFrame):
    """Premium labeled slider with live value display."""
    def __init__(self, parent, label, lo=0, hi=100, default=50, suffix="",
                 steps=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.suffix = suffix
        # Container
        card = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=10,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label, font=ctk.CTkFont(size=13),
                      text_color=TEXT_DIM).pack(side="left")
        self._fmt_default = default
        self.val_lbl = ctk.CTkLabel(top, text=self._fmt(default),
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     text_color=ACCENT)
        self.val_lbl.pack(side="right")
        skw = {"from_": lo, "to": hi, "command": self._slide,
               "fg_color": BG_BASE, "progress_color": ACCENT,
               "button_color": ACCENT, "button_hover_color": ACCENT_HOVER,
               "height": 18, "corner_radius": 9}
        if steps: skw["number_of_steps"] = steps
        self.slider = ctk.CTkSlider(inner, **skw)
        self.slider.set(default)
        self.slider.pack(fill="x", pady=(6, 0))

    def _fmt(self, v):
        if self.suffix in ("s", "x"):
            return f"{v:.2f}{self.suffix}"
        return f"{int(v)}{self.suffix}"

    def _slide(self, v):
        self.val_lbl.configure(text=self._fmt(v))

    def get(self): return self.slider.get()


class ZonePicker(ctk.CTkFrame):
    """Zone selector with toggle switches."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.vars = []
        card = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=10,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(inner, text="Target Zones", font=ctk.CTkFont(size=13),
                      text_color=TEXT_DIM).pack(anchor="w", pady=(0, 6))
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        colors = ["#FF4444", "#44FF44", "#4488FF", "#FF44FF"]
        for i in range(4):
            v = ctk.BooleanVar(value=True); self.vars.append(v)
            ctk.CTkSwitch(row, text=f"Zone {i+1}", variable=v,
                           font=ctk.CTkFont(size=12),
                           fg_color=TEXT_MUTED, progress_color=colors[i],
                           button_color=TEXT_HEAD, button_hover_color=ACCENT,
                           text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 14))

    def get_selected(self):
        return [i+1 for i, v in enumerate(self.vars) if v.get()]


class DirPicker(ctk.CTkFrame):
    """Direction selector."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.var = ctk.IntVar(value=1)
        card = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=10,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(inner, text="Direction", font=ctk.CTkFont(size=13),
                      text_color=TEXT_DIM).pack(anchor="w", pady=(0, 6))
        row = ctk.CTkFrame(inner, fg_color="transparent"); row.pack(fill="x")
        for txt, val in [("→  Right to Left", 1), ("←  Left to Right", 2)]:
            ctk.CTkRadioButton(row, text=txt, variable=self.var, value=val,
                                font=ctk.CTkFont(size=12), fg_color=ACCENT,
                                hover_color=ACCENT_HOVER, border_color=TEXT_MUTED,
                                text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 20))

    def get(self): return self.var.get()


class RegionPicker(ctk.CTkFrame):
    """Screen region selector using radio buttons."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.var = ctk.StringVar(value="bottom")
        card = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=10,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(inner, text="Sample Region", font=ctk.CTkFont(size=13),
                      text_color=TEXT_DIM).pack(anchor="w", pady=(0, 6))
        row = ctk.CTkFrame(inner, fg_color="transparent"); row.pack(fill="x")
        for txt, val in [("⬇ Bottom 40%", "bottom"), ("⬜ Full Screen", "full"), ("⬆ Top 40%", "top")]:
            ctk.CTkRadioButton(row, text=txt, variable=self.var, value=val,
                                font=ctk.CTkFont(size=12), fg_color=ACCENT,
                                hover_color=ACCENT_HOVER, border_color=TEXT_MUTED,
                                text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 16))

    def get(self): return self.var.get()


class SidebarBtn(ctk.CTkButton):
    """Sidebar navigation button."""
    def __init__(self, parent, text, icon, mode_id, on_click, **kw):
        self.mode_id = mode_id
        super().__init__(parent, text=f" {icon}   {text}", anchor="w",
                         font=ctk.CTkFont(size=13),
                         fg_color="transparent", hover_color=BG_HOVER,
                         text_color=TEXT_DIM, height=40, corner_radius=10,
                         command=lambda: on_click(mode_id), **kw)

    def set_active(self, active):
        if active:
            self.configure(fg_color=ACCENT_DIM, text_color=ACCENT,
                            border_color=ACCENT, border_width=0)
        else:
            self.configure(fg_color="transparent", text_color=TEXT_DIM,
                            border_width=0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Application
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PredatorRGBApp(ctk.CTk):
    MODES = [
        ("hw_static",    "Static",         "💡", "hardware"),
        ("hw_breathing", "Breathing",      "🫁", "hardware"),
        ("hw_neon",      "Neon",           "💜", "hardware"),
        ("hw_wave",      "Wave",           "🌊", "hardware"),
        ("hw_shifting",  "Shifting",       "↔️",  "hardware"),
        ("hw_zoom",      "Zoom",           "🔍", "hardware"),
        ("sw_rainbow",   "Rainbow Cycle",  "🌈", "software"),
        ("sw_strobe",    "Color Strobe",   "⚡", "software"),
        ("sw_police",    "Police Siren",   "🚨", "software"),
        ("sw_campfire",  "Campfire",       "🔥", "software"),
        ("sw_sparkle",   "Random Sparkle", "✨", "software"),
        ("sw_gradient",  "Gradient Sweep", "🎨", "software"),
        ("sw_dualwave",  "Dual-Color Wave","🌊", "software"),
        ("sw_pulse",     "Custom Pulse",   "💫", "software"),
        ("sw_ambient",   "Ambient Display","🖥️",  "software"),
        ("sw_music",     "Music Visualizer","🎵", "software"),
    ]

    def __init__(self):
        super().__init__()
        _check_device_access()
        self.title(APP_NAME)
        self.geometry("1020x720")
        self.minsize(900, 640)
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG_BASE)
        self.current_mode = None
        self.sidebar_btns = {}
        self.panels = {}
        self._widgets = {}
        self._build()
        self._select("hw_static")

    def _build(self):
        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=BG_SURFACE, height=56, corner_radius=0,
                            border_width=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        # Logo + title
        logo_f = ctk.CTkFrame(hdr, fg_color="transparent")
        logo_f.pack(side="left", padx=20)
        ctk.CTkLabel(logo_f, text="🎮", font=ctk.CTkFont(size=24)).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(logo_f, text="PREDATOR",
                      font=ctk.CTkFont(size=18, weight="bold"),
                      text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(logo_f, text=" RGB",
                      font=ctk.CTkFont(size=18, weight="bold"),
                      text_color=TEXT_HEAD).pack(side="left")

        # Version badge
        ctk.CTkLabel(logo_f, text=f" v{APP_VERSION}",
                      font=ctk.CTkFont(size=10),
                      text_color=TEXT_MUTED).pack(side="left", padx=(6, 0), pady=(4, 0))

        # Status
        status_f = ctk.CTkFrame(hdr, fg_color="transparent")
        status_f.pack(side="right", padx=20)
        if _sim_mode:
            dot_color = WARNING
            status_text = "⚠  Preview Mode — run with sudo for hardware"
        else:
            dot_color = ACCENT
            status_text = "●  Device Connected"
        self.status_lbl = ctk.CTkLabel(status_f, text=status_text,
                                        font=ctk.CTkFont(size=11),
                                        text_color=dot_color)
        self.status_lbl.pack()

        # Thin accent line under header
        ctk.CTkFrame(self, fg_color=ACCENT_DIM, height=1, corner_radius=0).pack(fill="x")

        # ── Body ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # ── Sidebar ──
        sidebar = ctk.CTkFrame(body, fg_color=BG_SURFACE, width=230, corner_radius=0)
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)

        scroll = ctk.CTkScrollableFrame(sidebar, fg_color="transparent",
                                         scrollbar_button_color=BORDER,
                                         scrollbar_button_hover_color=TEXT_MUTED)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Hardware section
        ctk.CTkLabel(scroll, text="── HARDWARE ──",
                      font=ctk.CTkFont(size=10, weight="bold"),
                      text_color=TEXT_MUTED).pack(pady=(6, 6))
        for mid, name, icon, cat in self.MODES:
            if cat != "hardware": continue
            btn = SidebarBtn(scroll, name, icon, mid, self._select)
            btn.pack(fill="x", pady=2); self.sidebar_btns[mid] = btn

        # Software section
        ctk.CTkLabel(scroll, text="── SOFTWARE ──",
                      font=ctk.CTkFont(size=10, weight="bold"),
                      text_color=TEXT_MUTED).pack(pady=(18, 6))
        for mid, name, icon, cat in self.MODES:
            if cat != "software": continue
            btn = SidebarBtn(scroll, name, icon, mid, self._select)
            btn.pack(fill="x", pady=2); self.sidebar_btns[mid] = btn

        # ── Content ──
        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True)

        self.kb_preview = KeyboardPreview(self.content)
        self.kb_preview.pack(fill="x", padx=12, pady=(12, 6))

        self.panel_box = ctk.CTkFrame(self.content, fg_color="transparent")
        self.panel_box.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        # ── Footer ──
        foot = ctk.CTkFrame(self, fg_color=BG_SURFACE, height=64, corner_radius=0)
        foot.pack(fill="x", side="bottom"); foot.pack_propagate(False)
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x", side="bottom")

        bf = ctk.CTkFrame(foot, fg_color="transparent")
        bf.pack(expand=True)

        self.btn_apply = ctk.CTkButton(
            bf, text="▶   APPLY", font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=BG_BASE,
            width=160, height=42, corner_radius=12, command=self._apply)
        self.btn_apply.pack(side="left", padx=8, pady=11)

        self.btn_stop = ctk.CTkButton(
            bf, text="■   STOP", font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=DANGER, hover_color=DANGER_HOVER, text_color="#FFFFFF",
            width=160, height=42, corner_radius=12, command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8, pady=11)

        self.btn_off = ctk.CTkButton(
            bf, text="⏻   LIGHTS OFF", font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=BG_ELEVATED, hover_color=BG_HOVER, text_color=TEXT_DIM,
            width=160, height=42, corner_radius=12,
            border_width=1, border_color=BORDER, command=self._off)
        self.btn_off.pack(side="left", padx=8, pady=11)

        # Build panels
        self._build_panels()

    def _build_panels(self):
        for mid, name, icon, cat in self.MODES:
            panel = ctk.CTkScrollableFrame(self.panel_box, fg_color=BG_ELEVATED,
                                            corner_radius=16,
                                            border_width=1, border_color=BORDER,
                                            scrollbar_button_color=BORDER)
            # Title
            tf = ctk.CTkFrame(panel, fg_color="transparent")
            tf.pack(fill="x", padx=20, pady=(20, 4))
            ctk.CTkLabel(tf, text=f"{icon}", font=ctk.CTkFont(size=28)).pack(side="left")
            ctk.CTkLabel(tf, text=f"  {name}", font=ctk.CTkFont(size=22, weight="bold"),
                          text_color=TEXT_HEAD).pack(side="left")
            # Badge
            badge_bg = ACCENT_DIM if cat == "hardware" else "#161640"
            badge_fg = ACCENT if cat == "hardware" else INFO
            ctk.CTkLabel(tf, text=f" {cat.upper()} ", font=ctk.CTkFont(size=9, weight="bold"),
                          text_color=badge_fg, fg_color=badge_bg,
                          corner_radius=6, height=22).pack(side="right")
            # Separator
            ctk.CTkFrame(panel, fg_color=BORDER, height=1).pack(fill="x", padx=20, pady=(14, 18))
            # Controls
            cf = ctk.CTkFrame(panel, fg_color="transparent")
            cf.pack(fill="both", expand=True, padx=20, pady=(0, 20))
            self._add_controls(mid, cf)
            self.panels[mid] = panel

    def _desc(self, p, text):
        ctk.CTkLabel(p, text=text, font=ctk.CTkFont(size=13), text_color=TEXT_PRIMARY,
                      wraplength=520, justify="left").pack(anchor="w", pady=(0, 14))

    def _note(self, p, text):
        nf = ctk.CTkFrame(p, fg_color="#1A1400", corner_radius=8, border_width=1, border_color="#3D3000")
        nf.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(nf, text=text, font=ctk.CTkFont(size=11), text_color=WARNING,
                      justify="left").pack(padx=12, pady=8, anchor="w")

    def _add_controls(self, mid, p):
        w = {}
        sp = 8  # spacing

        if mid == "hw_static":
            self._desc(p, "Set a solid, static color for individual keyboard zones. Pick zones and a color.")
            w['zones'] = ZonePicker(p); w['zones'].pack(fill="x", pady=(0, sp))
            w['color'] = ColorButton(p, "Static Color", "#00E676"); w['color'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "hw_breathing":
            self._desc(p, "Smooth fade-in / fade-out breathing animation with your chosen color.")
            w['color'] = ColorButton(p, "Breath Color", "#FF00FF"); w['color'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Speed", 0, 9, 4, "", steps=9); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "hw_neon":
            self._desc(p, "Auto-cycling neon color animation driven by keyboard firmware.")
            w['speed'] = Slider(p, "Speed", 0, 9, 3, "", steps=9); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "hw_wave":
            self._desc(p, "A colorful wave animation that rolls across the keyboard.")
            w['speed'] = Slider(p, "Speed", 0, 9, 5, "", steps=9); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))
            w['direction'] = DirPicker(p); w['direction'].pack(fill="x", pady=(0, sp))

        elif mid == "hw_shifting":
            self._desc(p, "Colors shift across zones with a directional sweep animation.")
            w['color'] = ColorButton(p, "Shift Color", "#0088FF"); w['color'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Speed", 0, 9, 5, "", steps=9); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))
            w['direction'] = DirPicker(p); w['direction'].pack(fill="x", pady=(0, sp))

        elif mid == "hw_zoom":
            self._desc(p, "A zoom/burst animation effect radiating from the center outward.")
            w['color'] = ColorButton(p, "Zoom Color", "#00FF00"); w['color'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Speed", 0, 9, 7, "", steps=9); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_rainbow":
            self._desc(p, "Smooth rainbow hues rotate across all 4 zones — each zone shows a different part of the spectrum, cycling continuously.")
            w['speed'] = Slider(p, "Frame Delay", 0.01, 0.2, 0.05, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_strobe":
            self._desc(p, "Rapid on/off strobing of a solid color across all zones. Intense and party-ready.")
            w['color'] = ColorButton(p, "Strobe Color", "#FFFFFF"); w['color'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Flash Rate", 0.02, 0.5, 0.1, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_police":
            self._desc(p, "Alternating red and blue flashes across zones — police siren effect with blackout gaps.")
            w['speed'] = Slider(p, "Flash Speed", 0.05, 0.5, 0.15, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_campfire":
            self._desc(p, "Warm orange/red/yellow flickering across zones — cozy campfire ambience.")
            w['speed'] = Slider(p, "Flicker Rate", 0.03, 0.2, 0.08, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_sparkle":
            self._desc(p, "Random zones light up with random bright colors — a sparkling glitter effect.")
            w['speed'] = Slider(p, "Sparkle Rate", 0.02, 0.2, 0.06, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_gradient":
            self._desc(p, "Smooth gradient transition sweeping back and forth between two chosen colors.")
            w['color1'] = ColorButton(p, "Start Color", "#FF0000"); w['color1'].pack(fill="x", pady=(0, sp))
            w['color2'] = ColorButton(p, "End Color", "#0000FF"); w['color2'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Sweep Speed", 0.01, 0.2, 0.05, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_dualwave":
            self._desc(p, "A wave-like pattern alternating between two colors across the keyboard zones.")
            w['color1'] = ColorButton(p, "Color A", "#FF0000"); w['color1'].pack(fill="x", pady=(0, sp))
            w['color2'] = ColorButton(p, "Color B", "#00FF00"); w['color2'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Wave Speed", 0.03, 0.3, 0.1, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_pulse":
            self._desc(p, "Smooth breathing/pulse with custom color. Uses sine-wave easing for natural pulsation.")
            w['color'] = ColorButton(p, "Pulse Color", "#00FFFF"); w['color'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Pulse Speed", 0.01, 0.1, 0.03, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_ambient":
            self._desc(p, "Mirrors your screen colors onto the keyboard in real-time — an Ambilight-style effect where each zone reflects a vertical strip of your display.")
            self._note(p, "📦 Requires: pip3 install Pillow")
            w['region'] = RegionPicker(p); w['region'].pack(fill="x", pady=(0, sp))
            w['saturation'] = Slider(p, "Saturation Boost", 0.5, 3.0, 1.5, "x"); w['saturation'].pack(fill="x", pady=(0, sp))
            w['speed'] = Slider(p, "Update Rate", 0.02, 0.2, 0.05, "s"); w['speed'].pack(fill="x", pady=(0, sp))
            w['smoothing'] = Slider(p, "Smoothing", 0.0, 0.95, 0.3, ""); w['smoothing'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        elif mid == "sw_music":
            self._desc(p, "The entire keyboard reacts to system audio in real-time! Brightness pulses with beat energy. Colors shift dynamically: blue (calm) → green → red/magenta (intense beats).")
            self._note(p, "📦 Requires: pip3 install numpy pyaudio\n📦 System: sudo apt install portaudio19-dev")
            w['sensitivity'] = Slider(p, "Sensitivity", 0.1, 5.0, 1.5, "x"); w['sensitivity'].pack(fill="x", pady=(0, sp))
            w['smoothing'] = Slider(p, "Smoothing", 0.0, 0.95, 0.4, ""); w['smoothing'].pack(fill="x", pady=(0, sp))
            w['brightness'] = Slider(p, "Brightness", 0, 100, 100, "%"); w['brightness'].pack(fill="x", pady=(0, sp))

        self._widgets[mid] = w

    def _select(self, mid):
        for m, btn in self.sidebar_btns.items(): btn.set_active(m == mid)
        for m, pan in self.panels.items():
            if m == mid: pan.pack(fill="both", expand=True)
            else: pan.pack_forget()
        self.current_mode = mid

    def _preview_cb(self, colors):
        try: self.after(0, lambda c=colors: self.kb_preview.update_zones(c))
        except: pass

    def _apply(self):
        global _running, _animation_thread
        self._stop(); sleep(0.1)
        mid = self.current_mode
        w = self._widgets.get(mid, {})
        cb = self._preview_cb

        # Hardware modes (instant, no thread)
        if mid == "hw_static":
            zones, (r,g,b), brt = w['zones'].get_selected(), w['color'].get_rgb(), int(w['brightness'].get())
            for z in zones: _write_static_zone(z, r, g, b, brt)
            self.kb_preview.set_all(r, g, b)
            self._status("✓  Static applied", ACCENT); return
        if mid == "hw_breathing":
            r,g,b = w['color'].get_rgb()
            _write_dynamic(1, int(w['speed'].get()), int(w['brightness'].get()), red=r, green=g, blue=b)
            self.kb_preview.set_all(r, g, b); self._status("✓  Breathing active", ACCENT); return
        if mid == "hw_neon":
            _write_dynamic(2, int(w['speed'].get()), int(w['brightness'].get()))
            self._status("✓  Neon active", ACCENT); return
        if mid == "hw_wave":
            _write_dynamic(3, int(w['speed'].get()), int(w['brightness'].get()), direction=w['direction'].get())
            self._status("✓  Wave active", ACCENT); return
        if mid == "hw_shifting":
            r,g,b = w['color'].get_rgb()
            _write_dynamic(4, int(w['speed'].get()), int(w['brightness'].get()), direction=w['direction'].get(), red=r, green=g, blue=b)
            self._status("✓  Shifting active", ACCENT); return
        if mid == "hw_zoom":
            r,g,b = w['color'].get_rgb()
            _write_dynamic(5, int(w['speed'].get()), int(w['brightness'].get()), red=r, green=g, blue=b)
            self._status("✓  Zoom active", ACCENT); return

        # Software modes (threaded)
        _running = True
        target, args = None, ()

        if mid == "sw_rainbow":  target, args = _anim_rainbow, (w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_strobe":
            r,g,b = w['color'].get_rgb()
            target, args = _anim_strobe, (r,g,b, w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_police": target, args = _anim_police, (w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_campfire": target, args = _anim_campfire, (w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_sparkle": target, args = _anim_sparkle, (w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_gradient":
            target, args = _anim_gradient, (w['color1'].get_rgb(), w['color2'].get_rgb(), w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_dualwave":
            target, args = _anim_dualwave, (w['color1'].get_rgb(), w['color2'].get_rgb(), w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_pulse":
            r,g,b = w['color'].get_rgb()
            target, args = _anim_pulse, (r,g,b, w['speed'].get(), int(w['brightness'].get()), cb)
        elif mid == "sw_ambient":
            target, args = _anim_ambient, (w['speed'].get(), int(w['brightness'].get()), w['region'].get(), w['saturation'].get(), w['smoothing'].get(), cb)
        elif mid == "sw_music":
            target, args = _anim_music, (w['sensitivity'].get(), int(w['brightness'].get()), w['smoothing'].get(), cb)

        if target:
            _animation_thread = threading.Thread(target=target, args=args, daemon=True)
            _animation_thread.start()
            self.btn_apply.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            name = next((n for m,n,_,_ in self.MODES if m == mid), mid)
            self._status(f"▶  {name} running...", ACCENT)

    def _stop(self):
        global _running, _animation_thread
        _running = False
        if _animation_thread and _animation_thread.is_alive():
            _animation_thread.join(timeout=2)
        _animation_thread = None
        self.btn_apply.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._status("■  Stopped", TEXT_DIM)

    def _off(self):
        self._stop()
        _write_all_zones([(0,0,0)]*4, 0)
        self.kb_preview.update_zones([(0,0,0)]*4)
        self._status("⏻  Lights off", TEXT_MUTED)

    def _status(self, text, color):
        try: self.status_lbl.configure(text=text, text_color=color)
        except: pass

    def destroy(self):
        global _running; _running = False
        super().destroy()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    if os.geteuid() != 0:
        print(f"\n  {'━'*50}")
        print(f"   🎮  {APP_NAME} v{APP_VERSION}")
        print(f"  {'━'*50}")
        print(f"\n   ⚠  Starting in PREVIEW MODE (UI only)")
        print(f"   For hardware control: sudo python3 predator_rgb_app.py\n")
    app = PredatorRGBApp()
    app.mainloop()

if __name__ == "__main__":
    main()
