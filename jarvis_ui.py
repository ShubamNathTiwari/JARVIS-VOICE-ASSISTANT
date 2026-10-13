import json
import math
import queue
import random
import sys
import threading
import time
import tkinter as tk

import jarvis

SETTINGS_FILE = "ui_settings.json"

# ---------- BASE COLORS ----------
BG = "#060a13"
BG_RGB = (6, 10, 19)
PANEL = "#0d1424"
PANEL_RGB = (13, 20, 36)
BORDER = "#1a2540"
TEXT = "#d6e4ff"
DIM = "#6b7a99"
BTN = "#131d33"
BTN_HOVER = "#1c2a4a"

# ---------- THEMES (colors are R, G, B) ----------
THEMES = {
    "Arc Reactor": {"accent": (0, 229, 255), "starting": (150, 120, 255),
                    "sleeping": (30, 111, 255), "listening": (0, 229, 255),
                    "thinking": (255, 179, 0), "speaking": (0, 255, 157),
                    "muted": (255, 77, 109)},
    "Stark Gold":  {"accent": (255, 196, 61), "starting": (255, 140, 60),
                    "sleeping": (166, 112, 28), "listening": (255, 196, 61),
                    "thinking": (255, 120, 60), "speaking": (255, 236, 150),
                    "muted": (255, 77, 109)},
    "Matrix":      {"accent": (0, 255, 120), "starting": (120, 255, 200),
                    "sleeping": (10, 110, 60), "listening": (0, 255, 120),
                    "thinking": (190, 255, 60), "speaking": (120, 255, 180),
                    "muted": (255, 77, 109)},
    "Violet":      {"accent": (178, 128, 255), "starting": (120, 140, 255),
                    "sleeping": (90, 60, 170), "listening": (178, 128, 255),
                    "thinking": (255, 140, 214), "speaking": (110, 231, 255),
                    "muted": (255, 77, 109)},
}

# (long label, short label used in mini mode)
LABELS = {
    "starting":  ("CALIBRATING MICROPHONE", "CALIBRATING"),
    "sleeping":  ('SLEEPING  -  say "Jarvis"', "SLEEPING"),
    "listening": ("LISTENING", "LISTENING"),
    "thinking":  ("THINKING", "THINKING"),
    "speaking":  ("SPEAKING", "SPEAKING"),
    "muted":     ("MIC MUTED  -  type your commands", "MUTED"),
}

# Quick-action buttons: (button text, command sent to Jarvis)
QUICK = [
    ("Time", "What time is it?"),
    ("YouTube", "Open YouTube"),
    ("Notepad", "Open notepad"),
    ("1-min timer", "Set a timer for 1 minute"),
    ("Joke", "Tell me a joke"),
]


def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


def mix(c1, c2, t):
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


# Messages from the Jarvis thread to the window travel through this queue
events = queue.Queue()
jarvis.ui_state = lambda s: events.put(("state", s))
jarvis.ui_log = lambda who, text: events.put(("log", who, text))


class JarvisUI:
    def __init__(self, root):
        self.root = root
        root.title("J.A.R.V.I.S")
        root.geometry("600x900")
        root.minsize(520, 760)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=0)   # orb
        root.rowconfigure(3, weight=1)   # conversation panel grows

        settings = self.load_settings()
        self.theme_name = settings.get("theme", "Arc Reactor")
        if self.theme_name not in THEMES:
            self.theme_name = "Arc Reactor"
        self.theme = THEMES[self.theme_name]

        self.state = "starting"
        self.color = self.theme["starting"]
        self.level = 0.0
        self.t = 0.0
        self.think_start = None
        self.last_dt = None
        self.mini = False
        self.normal_geometry = None
        # particle = [x, y, speed, size, twinkle phase], x and y are fractions 0..1
        self.particles = [[random.random(), random.random(),
                           0.0005 + random.random() * 0.0015,
                           random.random() * 1.8 + 0.6,
                           random.random() * 6.28] for _ in range(36)]

        # ===== row 0: header =====
        self.header = tk.Frame(root, bg=BG)
        self.header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 0))
        self.title_lbl = tk.Label(self.header, text="J.A.R.V.I.S", bg=BG,
                                  font=("Segoe UI", 22, "bold"))
        self.title_lbl.pack(side="left")
        tk.Label(self.header, text="PERSONAL VOICE ASSISTANT", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(12, 0), pady=(10, 0))
        self.mini_btn = self.make_button(self.header, "Mini mode  F3", self.toggle_mini, small=True)
        self.mini_btn.pack(side="right")
        self.theme_btn = self.make_button(self.header, f"Theme: {self.theme_name}  F2",
                                          self.cycle_theme, small=True)
        self.theme_btn.pack(side="right", padx=8)

        # ===== row 1: the orb =====
        self.canvas = tk.Canvas(root, width=560, height=340, bg=BG, highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Double-Button-1>", lambda e: self.toggle_mini())

        # ===== row 2: quick-action buttons =====
        self.chips = tk.Frame(root, bg=BG)
        self.chips.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 8))
        for label, cmd in QUICK:
            self.make_button(self.chips, label, lambda c=cmd: self.quick(c),
                             small=True).pack(side="left", padx=(0, 6))

        # ===== row 3: conversation panel =====
        self.log_frame = tk.Frame(root, bg=BORDER, padx=1, pady=1)
        self.log_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.log = tk.Text(self.log_frame, bg=PANEL, fg=TEXT, relief="flat", wrap="word",
                           padx=14, pady=10, borderwidth=0, highlightthickness=0,
                           font=("Segoe UI", 11), state="disabled", cursor="arrow")
        self.log.pack(fill="both", expand=True)

        # ===== row 4: typing box, buttons, status =====
        self.bottom = tk.Frame(root, bg=BG)
        self.bottom.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 12))

        row = tk.Frame(self.bottom, bg=BORDER, padx=1, pady=1)
        row.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(row, bg=PANEL)
        inner.pack(fill="x")
        self.entry = tk.Entry(inner, bg=PANEL, fg=TEXT, relief="flat",
                              font=("Segoe UI", 12), borderwidth=0)
        self.entry.pack(side="left", fill="x", expand=True, padx=(14, 6), ipady=10)
        self.entry.bind("<Return>", self.send_typed)
        self.send_btn = self.make_button(inner, "Send", self.send_typed, accent=True)
        self.send_btn.pack(side="right", padx=6, pady=6)

        buttons = tk.Frame(self.bottom, bg=BG)
        buttons.pack(fill="x")
        self.mute_btn = self.make_button(buttons, "Mute mic  F4", self.toggle_mute)
        self.mute_btn.pack(side="left")
        self.make_button(buttons, "Clear  F5", self.clear_log).pack(side="left", padx=8)
        self.top_var = tk.BooleanVar(value=False)
        tk.Checkbutton(buttons, text="Always on top", variable=self.top_var,
                       command=self.toggle_top, bg=BG, fg=DIM, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 9), borderwidth=0,
                       highlightthickness=0).pack(side="left", padx=6)
        self.make_button(buttons, "Quit", self.close, danger=True).pack(side="right")
        self.clock = tk.Label(buttons, text="", bg=BG, fg=DIM, font=("Segoe UI", 9))
        self.clock.pack(side="right", padx=14)

        self.status = tk.Label(self.bottom, text="", bg=BG, fg=DIM,
                               font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", pady=(10, 0))
        tk.Label(self.bottom,
                 text="Double-click the orb for mini mode   |   Esc leaves mini mode",
                 bg=BG, fg="#3d4a66", font=("Segoe UI", 8), anchor="w").pack(fill="x")

        # keyboard shortcuts
        root.bind("<F2>", lambda e: self.cycle_theme())
        root.bind("<F3>", lambda e: self.toggle_mini())
        root.bind("<F4>", lambda e: self.toggle_mute())
        root.bind("<F5>", lambda e: self.clear_log())
        root.bind("<Escape>", lambda e: self.toggle_mini() if self.mini else None)

        self.apply_theme()
        self.update_status()
        self.entry.focus_set()
        self.animate()
        self.poll()
        self.tick()

    # ---------- settings ----------
    def load_settings(self):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"theme": self.theme_name}, f)
        except Exception:
            pass

    # ---------- buttons ----------
    def make_button(self, parent, text, command, accent=False, danger=False, small=False):
        normal = "#0a3a46" if accent else BTN
        hover = "#0f5666" if accent else ("#ff4d6d" if danger else BTN_HOVER)
        b = tk.Button(parent, text=text, command=command, bg=normal, fg=TEXT,
                      activebackground=hover, activeforeground="white",
                      relief="flat", padx=10 if small else 16, pady=4 if small else 5,
                      borderwidth=0, font=("Segoe UI", 9 if small else 10),
                      cursor="hand2")
        b._normal, b._hover = normal, hover
        b.bind("<Enter>", lambda e: b.configure(bg=b._hover))
        b.bind("<Leave>", lambda e: b.configure(bg=b._normal))
        return b

    # ---------- themes ----------
    def apply_theme(self):
        th = self.theme
        accent = hexc(th["accent"])
        green = hexc(th["speaking"])
        self.title_lbl.configure(fg=accent)
        self.entry.configure(insertbackground=accent)
        self.send_btn._normal = hexc(mix(BG_RGB, th["accent"], 0.28))
        self.send_btn._hover = hexc(mix(BG_RGB, th["accent"], 0.48))
        self.send_btn.configure(bg=self.send_btn._normal)

        you_bg = hexc(mix(PANEL_RGB, th["accent"], 0.20))
        jv_bg = hexc(mix(PANEL_RGB, th["speaking"], 0.16))
        bold = ("Segoe UI", 8, "bold")
        t = self.log
        t.tag_configure("you_name", foreground=accent, font=bold, justify="right",
                        rmargin=10, spacing1=10)
        t.tag_configure("you_text", background=you_bg, foreground=TEXT, justify="right",
                        lmargin1=70, lmargin2=70, rmargin=10)
        t.tag_configure("jarvis_name", foreground=green, font=bold, justify="left",
                        lmargin1=10, lmargin2=10, spacing1=10)
        t.tag_configure("jarvis_text", background=jv_bg, foreground=TEXT, justify="left",
                        lmargin1=10, lmargin2=10, rmargin=70)
        t.tag_configure("sys", foreground=DIM, font=("Segoe UI", 9, "italic"),
                        justify="center", spacing1=6)

    def cycle_theme(self):
        names = list(THEMES)
        self.theme_name = names[(names.index(self.theme_name) + 1) % len(names)]
        self.theme = THEMES[self.theme_name]
        self.theme_btn.configure(text=f"Theme: {self.theme_name}  F2")
        self.apply_theme()
        self.save_settings()

    # ---------- actions ----------
    def send_typed(self, event=None):
        text = self.entry.get().strip()
        if text:
            jarvis.TYPED.put(text)
            self.entry.delete(0, "end")

    def quick(self, command):
        jarvis.TYPED.put(command)

    def toggle_mute(self):
        if jarvis.MUTED.is_set():
            jarvis.MUTED.clear()
            self.mute_btn.configure(text="Mute mic  F4")
        else:
            jarvis.MUTED.set()
            self.mute_btn.configure(text="Unmute mic  F4")

    def toggle_top(self):
        self.root.attributes("-topmost", self.top_var.get())

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def toggle_mini(self):
        if not self.mini:                          # go small
            self.normal_geometry = self.root.geometry()
            for w in (self.header, self.chips, self.log_frame, self.bottom):
                w.grid_remove()
            self.root.rowconfigure(1, weight=1)
            self.root.rowconfigure(3, weight=0)
            self.canvas.configure(width=280, height=290)
            self.root.minsize(240, 250)
            self.root.geometry("300x310")
            self.root.attributes("-topmost", True)
            self.mini = True
        else:                                      # go back to full size
            self.root.minsize(520, 760)
            if self.normal_geometry:
                self.root.geometry(self.normal_geometry)
            self.canvas.configure(width=560, height=340)
            self.root.rowconfigure(1, weight=0)
            self.root.rowconfigure(3, weight=1)
            for w in (self.header, self.chips, self.log_frame, self.bottom):
                w.grid()
            self.root.attributes("-topmost", self.top_var.get())
            self.mini = False

    # ---------- the animation (about 30 frames per second) ----------
    def animate(self):
        self.t += 0.033
        t, c, st = self.t, self.canvas, self.state
        w = max(c.winfo_width(), 200)
        h = max(c.winfo_height(), 200)
        sc = min(w, h) / 340.0                 # scale everything to the canvas size
        cx, cy = w / 2, (h - 34) / 2
        R = 72 * sc

        self.color = mix(self.color, self.theme[st], 0.1)   # smooth color change
        col = self.color

        if st == "speaking":
            self.level += (random.random() - self.level) * 0.35
        else:
            self.level += ((0.15 if st in ("sleeping", "muted") else 0.4) - self.level) * 0.1
        slow = st in ("sleeping", "muted")
        breathe = 0.5 + 0.5 * math.sin(t * (1.2 if slow else 3.0))
        pulse = 1 + 0.03 * breathe + 0.06 * self.level

        c.delete("orb")

        # floating particles (background)
        for p in self.particles:
            p[1] -= p[2] * (1 + 3 * self.level)
            if p[1] < 0:
                p[1], p[0] = 1.0, random.random()
            tw = 0.5 + 0.5 * math.sin(t * 2 + p[4])
            x, y, r = p[0] * w, p[1] * h, p[3] * sc
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=hexc(mix(BG_RGB, col, 0.15 + 0.45 * tw)),
                          outline="", tags="orb")

        core = R * 0.85 * pulse

        # HUD ring: tick marks that rotate slowly
        hud = core + 84 * sc
        rot = t * 0.25
        for i in range(72):
            a = 2 * math.pi * i / 72 + rot
            long_tick = (i % 6 == 0)
            r1, r2 = hud, hud + (9 if long_tick else 4) * sc
            c.create_line(cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                          cx + r2 * math.cos(a), cy + r2 * math.sin(a),
                          fill=hexc(mix(BG_RGB, col, 0.55 if long_tick else 0.22)),
                          width=2 if long_tick else 1, tags="orb")
        rr = hud - 10 * sc
        for k in range(3):                      # arcs turning the opposite way
            c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr,
                         start=(-t * 40 + k * 120) % 360, extent=50, style="arc",
                         outline=hexc(mix(BG_RGB, col, 0.5)), width=2, tags="orb")

        # soft glow
        for i in range(16, 0, -1):
            r = R * pulse + i * 5 * sc
            k = 0.30 * (1 - i / 17) ** 2 * (0.6 + self.level)
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=hexc(mix(BG_RGB, col, k)), outline="", tags="orb")

        # glowing core
        for i in range(12):
            r = core * (1 - i / 12)
            shade = mix(mix(BG_RGB, col, 0.35), mix(col, (255, 255, 255), 0.7), i / 12)
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=hexc(shade), outline="", tags="orb")
        c.create_oval(cx - core, cy - core, cx + core, cy + core,
                      outline=hexc(col), width=2, tags="orb")

        # effects for each state
        ring_r = core + 14 * sc
        if st == "listening":
            for k in range(3):
                p = (t * 0.6 + k / 3) % 1
                r = ring_r + p * 60 * sc
                c.create_oval(cx - r, cy - r, cx + r, cy + r,
                              outline=hexc(mix(col, BG_RGB, p)), width=2, tags="orb")
        elif st in ("thinking", "starting"):
            for k in range(3):
                r = ring_r + (6 + k * 14) * sc
                c.create_arc(cx - r, cy - r, cx + r, cy + r,
                             start=(t * (160 + k * 50) + k * 120) % 360, extent=80,
                             style="arc", outline=hexc(col), width=4, tags="orb")
        elif st == "speaking":
            n = 56
            for i in range(n):
                a = 2 * math.pi * i / n
                ln = (6 + 40 * abs(math.sin(t * 7 + i * 0.9)) * (0.35 + 0.65 * self.level)) * sc
                c.create_line(cx + ring_r * math.cos(a), cy + ring_r * math.sin(a),
                              cx + (ring_r + ln) * math.cos(a), cy + (ring_r + ln) * math.sin(a),
                              fill=hexc(col), width=3, capstyle="round", tags="orb")
        else:   # sleeping or muted: a calm ring
            c.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r,
                          outline=hexc(mix(col, BG_RGB, 0.55)), width=2, tags="orb")

        label = LABELS[st][1 if self.mini else 0]
        c.create_text(cx, h - 18, text=label, fill=hexc(col),
                      font=("Segoe UI", 10 if self.mini else 12, "bold"), tags="orb")
        if self.mini:
            c.create_text(cx, 12, text="double-click to expand", fill=DIM,
                          font=("Segoe UI", 8), tags="orb")

        self.root.after(33, self.animate)

    # ---------- receive messages from the Jarvis thread ----------
    def poll(self):
        try:
            while True:
                ev = events.get_nowait()
                if ev[0] == "state":
                    new = ev[1]
                    if new == "thinking" and self.state != "thinking":
                        self.think_start = time.time()
                    elif new == "speaking" and self.think_start:
                        self.last_dt = time.time() - self.think_start
                        self.think_start = None
                    self.state = new
                    self.update_status()
                elif ev[0] == "log":
                    self.add_message(ev[1], ev[2])
                elif ev[0] == "quit":
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def update_status(self):
        text = "●  " + LABELS[self.state][1].capitalize()
        if self.last_dt is not None:
            text += f"     |     last answer ready in {self.last_dt:.1f}s"
        self.status.configure(text=text, fg=hexc(self.theme[self.state]))

    def add_message(self, who, text):
        t = self.log
        t.configure(state="normal")
        if who == "System":
            t.insert("end", text + "\n", "sys")
        else:
            tag = "you" if who == "You" else "jarvis"
            stamp = time.strftime("%I:%M %p")
            t.insert("end", f"{who.upper()}   {stamp}\n", tag + "_name")
            t.insert("end", f" {text} \n", tag + "_text")
        t.see("end")
        t.configure(state="disabled")

    def tick(self):
        self.clock.configure(text=time.strftime("%I:%M %p   %a, %d %b"))
        self.root.after(1000, self.tick)

    def close(self):
        jarvis.STOP.set()
        self.root.destroy()

    # ---------- start Jarvis in the background ----------
    def start(self):
        def work():
            try:
                jarvis.run()
            except Exception as e:
                events.put(("log", "System", f"Error: {e}"))
                return                       # keep the window open so you can read it
            events.put(("quit",))            # said "goodbye": close the window
        threading.Thread(target=work, daemon=True).start()

    # ---------- demo mode: preview everything, uses no API quota ----------
    def demo(self):
        states = ["sleeping", "listening", "thinking", "speaking", "muted"]
        self.demo_i = getattr(self, "demo_i", -1) + 1
        s = states[self.demo_i % len(states)]
        events.put(("state", s))
        if s == "listening":
            self.add_message("You", "Jarvis, what is machine learning?")
        if s == "speaking":
            self.add_message("Jarvis", "Machine learning is how computers learn patterns from data.")
        self.root.after(3000, self.demo)


if __name__ == "__main__":
    try:                                      # sharper text on high-DPI Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app = JarvisUI(root)
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        app.demo()
    else:
        app.start()
    root.mainloop()