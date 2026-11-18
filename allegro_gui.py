"""
GUI do monitorowania paczek Allegro (wersja 2).
Wrzuć ten plik do tego samego folderu co allegro.py i uruchom:  python allegro_gui.py
Wymaga w allegro.py: carrier_label, waiting_in_locker (jak w ostatnich wersjach).
"""
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from collections import Counter
from datetime import datetime
from tkinter import messagebox, ttk

import allegro  # Twój skrypt: klucze, token, funkcje API
import updater
from app_info import APP_VERSION, UPDATE_MANIFEST_URL

# ---------------- USTAWIENIA GUI ----------------
LOCKER_ALERT_DAYS = 3        # od ilu dni paczka w automacie jest "zalegająca"
DEFAULT_AUTO_MINUTES = 10    # domyślny interwał auto-odświeżania
AUTO_ON_START = True         # True = auto-odświeżanie włączone od razu po otwarciu
# ------------------------------------------------

BG = "#1b1c21"
PANEL = "#25262d"
FG = "#e8e8ec"
MUTED = "#8b8d98"
ACCENT = "#4f8cff"

STATUS_ORDER = ["NEW", "PROCESSING", "READY_FOR_SHIPMENT",
                "SENT", "READY_FOR_PICKUP", "PICKED_UP"]

TRACK_PRIORITY = ["PENDING", "IN_TRANSIT", "RELEASED_FOR_DELIVERY", "OUT_FOR_DELIVERY",
                  "AVAILABLE_FOR_PICKUP", "READY_FOR_PICKUP", "NOTICE_LEFT",
                  "DELIVERED", "PICKED_UP"]

# statusy dostępne w menu ręcznej zmiany
MANUAL_STATUSES = ["NEW", "PROCESSING", "READY_FOR_SHIPMENT",
                   "SENT", "READY_FOR_PICKUP", "PICKED_UP"]

ALL = "Wszystkie"
ALL_CARRIERS = "Wszyscy"
ZALEGAJACE = f"Zalegające (≥{LOCKER_ALERT_DAYS} dni w automacie)"
NOT_SENT = "Jeszcze nie wysłane"


# Polskie nazwy statusów trackingu (własny słownik, niezależny od allegro.py)
PL = {
    "PENDING": "Oczekuje",
    "IN_TRANSIT": "W drodze",
    "RELEASED_FOR_DELIVERY": "Przekazana do doręczenia",
    "OUT_FOR_DELIVERY": "W doręczeniu",
    "AVAILABLE_FOR_PICKUP": "Do odbioru",
    "READY_FOR_PICKUP": "Do odbioru",
    "NOTICE_LEFT": "Awizo",
    "DELIVERED": "Odebrane",
    "PICKED_UP": "Odebrane",
    "ISSUE": "Problem z przesyłką",
    "RETURNED": "Zwrócona do nadawcy",
}


# Ikona okna wbudowana w kod (PNG 48/32/16 px)
ICONS_B64 = [
    "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",
]


def resource_path(name):
    """Ścieżka do pliku obok skryptu albo wewnątrz .exe (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def best_tracking(codes):
    """Najbardziej zaawansowany status trackingu jednej paczki, po polsku."""
    plain = [c for c in codes if not c.startswith(("DESC:", "TS:"))]
    if not plain:
        return "brak danych"
    best = max(plain, key=lambda c: TRACK_PRIORITY.index(c) if c in TRACK_PRIORITY else -1)
    return PL.get(best, best)


def locker_wait(all_codes):
    fn = getattr(allegro, "waiting_in_locker", None)
    if not fn:
        return None
    try:
        return fn(all_codes)
    except Exception:
        return None


def carrier_of(form, shipments):
    fn = getattr(allegro, "carrier_label", None)
    if not fn:
        return "-"
    try:
        return fn(form, shipments) or "-"
    except Exception:
        return "-"


def fmt_wait(td):
    if td is None:
        return ""
    days, hours = td.days, td.seconds // 3600
    return f"{days} dni {hours} godz." if days else f"{hours} godz."


def load_config():
    """Dane logowania z config.json obok programu (nadpisują wartości z allegro.py).
    Dzięki temu w pliku .exe nie ma żadnych kluczy, a aktualizacje można bezpiecznie publikować."""
    base = updater.app_dir()
    path = os.path.join(base, "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        for key in ("CLIENT_ID", "CLIENT_SECRET", "SANDBOX", "DRY_RUN", "POLL_INTERVAL_SEC"):
            if key in cfg:
                setattr(allegro, key, cfg[key])
        sb = bool(getattr(allegro, "SANDBOX", False))
        allegro.AUTH_HOST = "allegro.pl.allegrosandbox.pl" if sb else "allegro.pl"
        allegro.API_HOST = "api.allegro.pl.allegrosandbox.pl" if sb else "api.allegro.pl"
        allegro.API = f"https://{allegro.API_HOST}"
    # plik z tokenem zawsze obok programu (a nie w folderze, z którego go uruchomiono)
    allegro.TOKEN_FILE = os.path.join(base, os.path.basename(getattr(allegro, "TOKEN_FILE", "allegro_token.json")))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Allegro – monitor paczek  v{APP_VERSION}")
        self._set_icon()
        self.geometry("1240x720")
        self.minsize(980, 520)
        self.configure(bg=BG)

        self.q = queue.Queue()
        self.scanning = False
        self.all_rows = []
        self.counts = Counter()
        self.at_me = Counter()
        self.iid_map = {}
        self.sort_col = "wait"
        self.sort_rev = True
        self.next_at = None

        self._style()
        self._build()

        self.after(100, self._poll_queue)
        self.after(1000, self._tick)
        self.after(300, self.start_scan)
        self.after(4000, lambda: self.check_updates(manual=False))

    def _set_icon(self):
        try:
            self._icons = [tk.PhotoImage(data=d) for d in ICONS_B64]
            self.iconphoto(True, *self._icons)
        except Exception as e:  # noqa: BLE001
            print("Nie udało się ustawić ikony okna:", e)

    # ---------- wygląd ----------
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                    bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL, font=("Segoe UI", 10))
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("TCheckbutton", background=BG, foreground=FG)
        s.map("TCheckbutton", background=[("active", BG)], foreground=[("active", FG)])
        s.configure("TButton", background=ACCENT, foreground="white", padding=(14, 6),
                    borderwidth=0, font=("Segoe UI", 10, "bold"))
        s.map("TButton", background=[("active", "#6aa0ff"), ("disabled", "#3a3d48")],
              foreground=[("disabled", MUTED)])
        s.configure("Ghost.TButton", background="#30323b", foreground=FG, padding=(10, 6), borderwidth=0)
        s.map("Ghost.TButton", background=[("active", "#3b3e49")])
        s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL, bordercolor=PANEL)
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG)
        s.configure("TSpinbox", fieldbackground=PANEL, foreground=FG, arrowcolor=FG)
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG,
                    arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)],
              foreground=[("readonly", FG)], background=[("readonly", PANEL)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                    rowheight=28, borderwidth=0)
        s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        s.configure("Treeview.Heading", background="#30323b", foreground=FG,
                    font=("Segoe UI", 10, "bold"), relief="flat", padding=6)
        s.map("Treeview.Heading", background=[("active", "#3b3e49")])
        s.configure("Vertical.TScrollbar", background="#30323b", troughcolor=BG,
                    arrowcolor=FG, bordercolor=BG)

    # ---------- budowa okna ----------
    def _build(self):
        # --- pasek sterowania ---
        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")

        self.btn = ttk.Button(top, text="⟳  Skanuj teraz", command=self.start_scan)
        self.btn.pack(side="left")

        self.auto_var = tk.BooleanVar(value=AUTO_ON_START)
        ttk.Checkbutton(top, text="Auto co", variable=self.auto_var,
                        command=self._auto_toggled).pack(side="left", padx=(16, 2))
        self.auto_min = tk.StringVar(value=str(DEFAULT_AUTO_MINUTES))
        ttk.Spinbox(top, from_=1, to=240, width=4, textvariable=self.auto_min,
                    command=self._auto_toggled).pack(side="left")
        ttk.Label(top, text="min").pack(side="left", padx=(4, 0))
        self.countdown = ttk.Label(top, text="", style="Muted.TLabel")
        self.countdown.pack(side="left", padx=10)
        ttk.Button(top, text="⬆ Aktualizacje", style="Ghost.TButton",
                   command=lambda: self.check_updates(manual=True)).pack(side="left", padx=(6, 0))
        ttk.Label(top, text=f"v{APP_VERSION}", style="Muted.TLabel").pack(side="left", padx=8)

        self.apply_var = tk.BooleanVar(value=not allegro.DRY_RUN)
        ttk.Checkbutton(top, text="Zapisuj zmiany statusów w Allegro",
                        variable=self.apply_var, command=self._apply_toggled).pack(side="right")

        # --- karty z liczbami ---
        cards = ttk.Frame(self, padding=(12, 6, 12, 2))
        cards.pack(fill="x")
        self.card_vals = {}
        for key, title in [("all", "Wszystkie zamówienia"),
                           ("notsent", NOT_SENT),
                           ("sent", "W drodze"),
                           ("pickup", "Do odbioru"),
                           ("alert", f"Zalegają ≥{LOCKER_ALERT_DAYS} dni")]:
            f, val = self._make_card(cards, title)
            f.pack(side="left", padx=(0, 10))
            self.card_vals[key] = val
        self.card_vals["alert"].configure(fg="#ff8f99")

        # --- jeszcze nie wysłane wg kuriera ---
        self.carrier_bar = ttk.Frame(self, padding=(12, 6, 12, 0))
        self.carrier_bar.pack(fill="x")

        # --- szukanie i filtry ---
        bar = ttk.Frame(self, padding=(12, 8, 12, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="Szukaj:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._render())
        ttk.Entry(bar, textvariable=self.search_var, width=26).pack(side="left", padx=(6, 18))

        ttk.Label(bar, text="Status:").pack(side="left")
        self.filter_map = {allegro.STATUS_PL[s]: s for s in STATUS_ORDER}
        self.filter_var = tk.StringVar(value=ALL)
        cb = ttk.Combobox(bar, textvariable=self.filter_var, state="readonly", width=32,
                          values=[ALL, NOT_SENT, ZALEGAJACE] + list(self.filter_map.keys()))
        cb.pack(side="left", padx=(6, 18))
        cb.bind("<<ComboboxSelected>>", lambda e: self._render())

        ttk.Label(bar, text="Kurier:").pack(side="left")
        self.carrier_var = tk.StringVar(value=ALL_CARRIERS)
        self.carrier_cb = ttk.Combobox(bar, textvariable=self.carrier_var, state="readonly",
                                       width=14, values=[ALL_CARRIERS])
        self.carrier_cb.pack(side="left", padx=6)
        self.carrier_cb.bind("<<ComboboxSelected>>", lambda e: self._render())

        self.change_btn = ttk.Button(bar, text="✎  Zmień status zaznaczonych",
                                     command=self._popup_at_button)
        self.change_btn.pack(side="right")

        # --- tabela ---
        mid = ttk.Frame(self, padding=(12, 0, 12, 0))
        mid.pack(fill="both", expand=True)

        cols = ("order", "carrier", "waybill", "status", "tracking", "wait", "change")
        self.headings = {
            "order": "Zamówienie", "carrier": "Kurier", "waybill": "Numer listu",
            "status": "Status w Allegro", "tracking": "Tracking",
            "wait": "W automacie", "change": "Zmiana",
        }
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        widths = {"order": 290, "carrier": 80, "waybill": 210, "status": 120,
                  "tracking": 160, "wait": 120, "change": 150}
        for c in cols:
            self.tree.heading(c, text=self.headings[c], command=lambda c=c: self._sort_by(c))
            self.tree.column(c, width=widths[c], anchor="w")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.tag_configure("alert", background="#5a2227", foreground="#ffb8bd")
        self.tree.tag_configure("pickup", background="#1f3d2c", foreground="#aee8c3")
        self.tree.tag_configure("sent", foreground="#9ecbff")
        self.tree.tag_configure("idle", foreground=MUTED)
        self.tree.bind("<Double-1>", self._copy_waybill)
        self.tree.bind("<Button-3>", self._on_right_click)

        # menu zmiany statusu
        self.menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT,
                            activeforeground="white", bd=0, font=("Segoe UI", 10))
        self.menu.add_command(label="Ustaw status w Allegro:", state="disabled")
        self.menu.add_separator()
        for st in MANUAL_STATUSES:
            self.menu.add_command(label=allegro.STATUS_PL.get(st, st),
                                  command=lambda st=st: self._change_status(st))

        self.status = ttk.Label(self, text="", style="Muted.TLabel", padding=(12, 6, 12, 10))
        self.status.pack(fill="x")

        self._update_heading_arrows()

    @staticmethod
    def _make_card(parent, title):
        f = tk.Frame(parent, bg=PANEL, padx=18, pady=8)
        val = tk.Label(f, text="–", bg=PANEL, fg=FG, font=("Segoe UI", 22, "bold"))
        val.pack(anchor="w")
        tk.Label(f, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        return f, val

    # ---------- akcje ----------
    def _apply_toggled(self):
        if self.apply_var.get():
            ok = messagebox.askyesno(
                "Uwaga",
                "Włączasz zapisywanie zmian: skrypt będzie naprawdę przestawiał statusy "
                "zamówień w Allegro (tylko do przodu).\n\nNa pewno?")
            if not ok:
                self.apply_var.set(False)

    def _auto_toggled(self):
        if self.auto_var.get():
            self.next_at = time.time() + self._interval()
        else:
            self.next_at = None
            self.countdown.config(text="")

    def _interval(self):
        try:
            return max(1, int(self.auto_min.get())) * 60
        except ValueError:
            return DEFAULT_AUTO_MINUTES * 60

    def _tick(self):
        if self.auto_var.get() and self.next_at and not self.scanning:
            left = int(self.next_at - time.time())
            if left <= 0:
                self.start_scan()
            else:
                self.countdown.config(text=f"następny skan za {left // 60}:{left % 60:02d}")
        self.after(1000, self._tick)

    def _copy_waybill(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return  # dwuklik na nagłówku nic nie kopiuje
        iid = self.tree.identify_row(event.y)
        r = self.iid_map.get(iid)
        if not r:
            return
        if self.tree.identify_column(event.x) == "#1":   # kolumna "Zamówienie"
            text, what = r["oid"], "numer zamówienia"
        else:
            text, what = r["waybill"], "numer listu"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.config(text=f"Skopiowano {what}: {text}")

    def _sort_by(self, col):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col, self.sort_rev = col, (col == "wait")
        self._update_heading_arrows()
        self._render()

    def _update_heading_arrows(self):
        for c, name in self.headings.items():
            arrow = ""
            if c == self.sort_col:
                arrow = "  ▼" if self.sort_rev else "  ▲"
            self.tree.heading(c, text=name + arrow)

    # ---------- skanowanie ----------
    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.btn.config(state="disabled")
        self.countdown.config(text="")
        self.status.config(text="Skanowanie…")
        threading.Thread(target=self._worker, args=(self.apply_var.get(),), daemon=True).start()

    def _worker(self, apply_changes):
        try:
            allegro.DRY_RUN = not apply_changes
            rows, counts, at_me, changed, n = [], Counter(), Counter(), 0, 0
            for current in allegro.PRE_SENT_STATUSES + ["SENT", "READY_FOR_PICKUP"]:
                for form in allegro.orders_with_status(current):
                    n += 1
                    self.q.put(("progress", n))
                    oid = form["id"]
                    counts[current] += 1
                    shipments = allegro.shipments_of(oid)
                    all_codes = allegro.collect_codes(shipments, oid) if shipments else None

                    carrier = carrier_of(form, shipments)
                    waybill = ", ".join(str(s.get("waybill") or "?") for s in shipments)
                    tracking, wait, target = "brak przesyłki", None, None

                    if all_codes:
                        tracking = ", ".join(best_tracking(c) for c in all_codes)
                        target = allegro.classify(all_codes)
                        if target == "READY_FOR_PICKUP" or current == "READY_FOR_PICKUP":
                            wait = locker_wait(all_codes)

                    change = ""
                    if target and allegro.RANK[target] > allegro.RANK[current]:
                        change = target
                        if apply_changes:
                            allegro.set_status(oid, target)
                        counts[current] -= 1
                        counts[target] += 1
                        changed += 1

                    eff = change or current
                    if eff in allegro.PRE_SENT_STATUSES:
                        at_me[carrier] += 1

                    alert = wait is not None and wait.days >= LOCKER_ALERT_DAYS
                    if alert:
                        tag = "alert"
                    elif eff == "READY_FOR_PICKUP":
                        tag = "pickup"
                    elif eff == "SENT":
                        tag = "sent"
                    elif not all_codes:
                        tag = "idle"
                    else:
                        tag = ""

                    change_txt = ""
                    if change:
                        change_txt = f"→ {allegro.STATUS_PL.get(change, change)}"
                        change_txt += " ✓" if apply_changes else " (podgląd)"

                    rows.append({
                        "oid": oid, "carrier": carrier, "waybill": waybill,
                        "current": current, "eff": eff, "tracking": tracking,
                        "wait": wait, "alert": alert, "tag": tag,
                        "change_txt": change_txt,
                    })
            self.q.put(("done", rows, counts, at_me, changed))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", str(e)))

    # ---------- aktualizacje programu ----------
    def check_updates(self, manual):
        if not manual and not updater.is_frozen():
            return  # przy uruchamianiu z .py nie sprawdzamy automatycznie
        if not UPDATE_MANIFEST_URL or "TWOJ_LOGIN" in UPDATE_MANIFEST_URL:
            if manual:
                messagebox.showinfo("Aktualizacje", "Adres aktualizacji nie jest ustawiony (plik app_info.py).")
            return
        if manual:
            self.status.config(text="Sprawdzam aktualizacje…")
        threading.Thread(target=self._check_worker, args=(manual,), daemon=True).start()

    def _check_worker(self, manual):
        try:
            self.q.put(("upd_found", updater.check(UPDATE_MANIFEST_URL, APP_VERSION), manual))
        except Exception as e:  # noqa: BLE001
            self.q.put(("upd_check_err", str(e), manual))

    def _on_update_check(self, m, manual):
        if not m:
            if manual:
                self.status.config(text=f"Masz najnowszą wersję ({APP_VERSION}).")
                messagebox.showinfo("Aktualizacje", f"Masz najnowszą wersję ({APP_VERSION}).")
            return
        if not updater.is_frozen():
            if manual:
                messagebox.showinfo("Aktualizacje", f"Dostępna wersja {m['version']}.\n"
                                    "Automatyczna aktualizacja działa tylko w wersji .exe.")
            return
        if self.scanning:                       # nie przerywamy skanu
            self.after(30000, lambda: self.check_updates(manual=False))
            return
        text = f"Jest nowa wersja programu: {m['version']} (masz {APP_VERSION})."
        notes = (m.get("notes") or "").strip()
        if notes:
            text += f"\n\nCo nowego:\n{notes}"
        text += "\n\nPobrać i zainstalować teraz? Program zamknie się i uruchomi ponownie."
        if messagebox.askyesno("Dostępna aktualizacja", text):
            self._download_update(m)

    def _download_update(self, m):
        win = tk.Toplevel(self)
        win.title("Aktualizacja")
        win.configure(bg=BG)
        win.geometry("380x130")
        win.resizable(False, False)
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: None)   # nie zamykamy w trakcie pobierania
        ttk.Label(win, text=f"Pobieranie wersji {m['version']}…").pack(pady=(18, 8))
        self.upd_bar = ttk.Progressbar(win, length=320, mode="determinate", maximum=100)
        self.upd_bar.pack()
        self.upd_lbl = ttk.Label(win, text="", style="Muted.TLabel")
        self.upd_lbl.pack(pady=8)
        win.grab_set()
        self.upd_win = win
        threading.Thread(target=self._download_worker, args=(m,), daemon=True).start()

    def _download_worker(self, m):
        try:
            path = updater.download(m, progress=lambda d, t: self.q.put(("upd_progress", d, t)))
            self.q.put(("upd_ready", path))
        except Exception as e:  # noqa: BLE001
            self.q.put(("upd_fail", str(e)))

    def _upd_progress(self, done, total):
        mb = lambda x: f"{x / 1048576:.1f}"
        if total:
            self.upd_bar["value"] = done * 100 / total
            self.upd_lbl.config(text=f"{mb(done)} / {mb(total)} MB")
        else:
            self.upd_lbl.config(text=f"{mb(done)} MB")

    def _upd_close(self):
        win = getattr(self, "upd_win", None)
        if win is not None:
            win.destroy()
            self.upd_win = None

    def _upd_apply(self, path):
        self.upd_lbl.config(text="Instaluję i uruchamiam ponownie…")
        self.update_idletasks()
        try:
            updater.apply_and_restart(path)
        except Exception as e:  # noqa: BLE001
            self._upd_close()
            messagebox.showerror("Aktualizacja nie powiodła się", str(e))
            return
        self.destroy()
        os._exit(0)

    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.status.config(text=f"Skanowanie… sprawdzono {msg[1]} zamówień")
                elif kind == "done":
                    _, rows, counts, at_me, changed = msg
                    self.all_rows, self.counts, self.at_me = rows, counts, at_me
                    self._finish_scan(changed)
                elif kind == "manual_done":
                    _, new_status, ok, fail = msg
                    self._manual_finished(new_status, ok, fail)
                elif kind == "upd_found":
                    self._on_update_check(msg[1], msg[2])
                elif kind == "upd_check_err":
                    if msg[2]:
                        messagebox.showerror("Aktualizacje", f"Nie udało się sprawdzić aktualizacji:\n{msg[1]}")
                elif kind == "upd_progress":
                    self._upd_progress(msg[1], msg[2])
                elif kind == "upd_ready":
                    self._upd_apply(msg[1])
                elif kind == "upd_fail":
                    self._upd_close()
                    messagebox.showerror("Aktualizacja nie powiodła się", msg[1])
                elif kind == "error":
                    self.scanning = False
                    self.btn.config(state="normal")
                    self.status.config(text=f"Błąd: {msg[1]}")
                    messagebox.showerror("Błąd skanowania", msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish_scan(self, changed):
        self.scanning = False
        self.btn.config(state="normal")
        names = sorted({r["carrier"] for r in self.all_rows})
        self.carrier_cb.configure(values=[ALL_CARRIERS] + names)
        if self.carrier_var.get() not in [ALL_CARRIERS] + names:
            self.carrier_var.set(ALL_CARRIERS)
        self._render()
        self._render_cards()
        mode = "zapisano" if self.apply_var.get() else "do zmiany (podgląd)"
        self.status.config(
            text=f"Ostatni skan: {datetime.now():%H:%M:%S}   |   "
                 f"Sprawdzono: {len(self.all_rows)}   |   Zmian {mode}: {changed}   |   "
                 f"Dwuklik kopiuje numer zamówienia lub listu (zależnie od kolumny)")
        if self.auto_var.get():
            self.next_at = time.time() + self._interval()

    # ---------- wyświetlanie ----------
    def _render(self):
        f = self.filter_var.get()
        c = self.carrier_var.get()
        q = self.search_var.get().strip().lower()
        rows = []
        for r in self.all_rows:
            if f == ZALEGAJACE and not r["alert"]:
                continue
            if f == NOT_SENT and r["eff"] not in allegro.PRE_SENT_STATUSES:
                continue
            if f in self.filter_map and r["eff"] != self.filter_map[f]:
                continue
            if c != ALL_CARRIERS and r["carrier"] != c:
                continue
            if q and q not in f"{r['waybill']} {r['oid']} {r['carrier']}".lower():
                continue
            rows.append(r)

        def key(r):
            col = self.sort_col
            if col == "wait":
                return r["wait"].total_seconds() if r["wait"] is not None else -1
            return {
                "order": r["oid"], "carrier": r["carrier"].lower(),
                "waybill": r["waybill"], "status": allegro.RANK[r["eff"]],
                "tracking": r["tracking"].lower(), "change": r["change_txt"],
            }[col]

        rows.sort(key=key, reverse=self.sort_rev)

        self.tree.delete(*self.tree.get_children())
        self.iid_map = {}
        for r in rows:
            iid = self.tree.insert("", "end", tags=(r["tag"],), values=(
                r["oid"], r["carrier"], r["waybill"],
                allegro.STATUS_PL.get(r["current"], r["current"]),
                r["tracking"], fmt_wait(r["wait"]), r["change_txt"],
            ))
            self.iid_map[iid] = r

    # ---------- ręczna zmiana statusu ----------
    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _popup_at_button(self):
        if not self.tree.selection():
            messagebox.showinfo("Zmiana statusu",
                                "Najpierw zaznacz zamówienie w tabeli "
                                "(Ctrl lub Shift + klik zaznacza kilka).")
            return
        b = self.change_btn
        try:
            self.menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            self.menu.grab_release()

    def _change_status(self, new_status):
        rows = [self.iid_map[i] for i in self.tree.selection() if i in self.iid_map]
        if not rows:
            return
        name = allegro.STATUS_PL.get(new_status, new_status)
        if not messagebox.askyesno(
                "Zmiana statusu",
                f"Ustawić status \"{name}\" w Allegro dla {len(rows)} zamówień?\n\n"
                "Zmiana jest zapisywana naprawdę i działa niezależnie od przełącznika "
                "„Zapisuj zmiany statusów”."):
            return
        self.status.config(text="Zmieniam status…")
        threading.Thread(target=self._change_worker, args=(rows, new_status),
                         daemon=True).start()

    def _change_worker(self, rows, new_status):
        ok, fail = [], []
        for r in rows:
            try:
                resp = allegro.api("PUT", f"/order/checkout-forms/{r['oid']}/fulfillment",
                                   json={"status": new_status})
                if resp.status_code in (200, 204):
                    ok.append(r["oid"])
                else:
                    fail.append((r["oid"], f"{resp.status_code} {resp.text[:150]}"))
            except Exception as e:  # noqa: BLE001
                fail.append((r["oid"], str(e)))
        self.q.put(("manual_done", new_status, ok, fail))

    def _manual_finished(self, new_status, ok, fail):
        done = set(ok)
        for r in self.all_rows:
            if r["oid"] in done:
                r["current"] = r["eff"] = new_status
                r["change_txt"] = ""
                r["alert"] = r["alert"] and new_status == "READY_FOR_PICKUP"
                if r["alert"]:
                    r["tag"] = "alert"
                elif new_status == "READY_FOR_PICKUP":
                    r["tag"] = "pickup"
                elif new_status == "SENT":
                    r["tag"] = "sent"
                else:
                    r["tag"] = ""
        # przeliczenie liczników z aktualnych wierszy
        self.counts = Counter(r["eff"] for r in self.all_rows)
        self.at_me = Counter(r["carrier"] for r in self.all_rows
                             if r["eff"] in allegro.PRE_SENT_STATUSES)
        self._render()
        self._render_cards()
        name = allegro.STATUS_PL.get(new_status, new_status)
        self.status.config(text=f"Zmieniono status na {name}: {len(ok)} OK, błędów: {len(fail)}")
        if fail:
            lines = "\n".join(f"{oid[:8]}…: {err}" for oid, err in fail[:8])
            messagebox.showerror("Nie udało się zmienić części zamówień", lines)

    def _render_cards(self):
        c = self.counts
        not_sent = sum(c[s] for s in allegro.PRE_SENT_STATUSES)
        alerts = sum(1 for r in self.all_rows if r["alert"])
        self.card_vals["all"].config(text=str(sum(c.values())))
        self.card_vals["notsent"].config(text=str(not_sent))
        self.card_vals["sent"].config(text=str(c["SENT"]))
        self.card_vals["pickup"].config(text=str(c["READY_FOR_PICKUP"]))
        self.card_vals["alert"].config(text=str(alerts))

        for w in self.carrier_bar.winfo_children():
            w.destroy()
        if self.at_me:
            tk.Label(self.carrier_bar, text=f"{NOT_SENT} wg kuriera:", bg=BG, fg=MUTED,
                     font=("Segoe UI", 10)).pack(side="left", padx=(0, 10))
            for name, n in self.at_me.most_common():
                tk.Label(self.carrier_bar, text=f"{name}: {n}",
                         bg=PANEL, fg=FG,
                         padx=10, pady=3, font=("Segoe UI", 10, "bold")
                         ).pack(side="left", padx=(0, 8))


if __name__ == "__main__":
    try:
        load_config()
    except Exception as e:  # noqa: BLE001
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Błąd config.json", str(e)); sys.exit(1)
    cid = str(getattr(allegro, "CLIENT_ID", "") or "")
    if not cid or "WPISZ" in cid.upper():
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Brak konfiguracji",
                             "Nie znaleziono danych logowania do Allegro.\n\n"
                             "Połóż obok programu plik config.json (wzór: config.example.json)\n"
                             "i wpisz w nim CLIENT_ID oraz CLIENT_SECRET.")
        sys.exit(1)
    App().mainloop()
