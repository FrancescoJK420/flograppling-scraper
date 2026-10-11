"""
FloGrappling batch downloader (GUI)

Requisiti: Python 3, ffmpeg nel PATH, `pip install requests`
Uso: python flo_downloader.py
"""
import html
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse

import requests

API = 'https://api.flograppling.com/api/right-rail/videos/{}'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


# ----------------------------- logica download -----------------------------

def get_video_id(url):
    url = url.strip().strip('"\'')
    if url.isdigit():
        return url
    m = re.search(r'[?&]playing=(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    raise ValueError('ID video non trovato nel link')


def safe_name(text):
    return re.sub(r'[\\/:*?"<>|]+', '', text).strip()[:120]


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
}


def clean_title(t):
    t = html.unescape(t or '').strip()
    return re.sub(r'\s*[-|]\s*FloGrappling.*$', '', t, flags=re.I).strip()


def page_title(url, video_id):
    """Ripiego: legge il titolo dalla pagina. Ritorna (titolo, motivo_errore)."""
    candidates = []
    if url.startswith('http'):
        candidates.append(url)
    candidates.append(f'https://www.flograppling.com/video/{video_id}')
    reasons = []
    for u in candidates:
        try:
            r = requests.get(u, headers=HEADERS, timeout=30)
            r.raise_for_status()
            m = (re.search(r'<title[^>]*>(.*?)</title>', r.text, re.S | re.I)
                 or re.search(r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)', r.text, re.I))
            t = clean_title(m.group(1)) if m else ''
            if len(t) > 3:
                return t, ''
            reasons.append('pagina senza titolo')
        except Exception as e:
            reasons.append(f'{type(e).__name__}: {e}'[:90])
    return '', ' | '.join(reasons)


def fetch_info(video_id, url=''):
    r = requests.get(API.format(video_id), timeout=30)
    r.raise_for_status()
    data = r.json().get('data')
    source = data.get('source_video') if data else None
    if not source or not source.get('playlist'):
        raise RuntimeError('Nessun video disponibile (ID errato o a pagamento)')

    # 1) titolo dai campi del video stesso (non dipende dalla pagina web)
    for key in ('seo_page_title', 'title', 'short_title'):
        t = clean_title(source.get(key))
        if len(t) > 3:
            return source['playlist'], t, ''
    # 2) ripiego: titolo letto dalla pagina
    title, reason = page_title(url, video_id)
    return source['playlist'], title, reason


def to_seconds(h, m, s):
    return int(h) * 3600 + int(m) * 60 + float(s)


# La durata serve per la percentuale; la leggiamo con ffprobe (incluso in ffmpeg).
def probe_duration(url):
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, '-v', 'error', '-allowed_segment_extensions', 'ALL',
             '-extension_picky', '0', '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', url],
            capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW,
        ).stdout.strip()
        return float(out)
    except Exception:
        return None


def audio_mean_volume(path):
    """Volume medio dell'audio in dB, oppure None se non c'è audio."""
    try:
        p = subprocess.run(
            ['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-vn',
             '-af', 'volumedetect', '-f', 'null', '-'],
            capture_output=True, text=True, errors='replace',
            creationflags=NO_WINDOW, timeout=300,
        )
        m = re.search(r'mean_volume:\s*(-?[\d.]+|-inf) dB', p.stderr)
        if not m:
            return None
        return -100.0 if m.group(1) == '-inf' else float(m.group(1))
    except Exception:
        return None


class Downloader:
    def __init__(self, ui_queue, out_dir):
        self.q = ui_queue
        self.out_dir = out_dir
        self.stop_event = threading.Event()
        self.procs = set()
        self.lock = threading.Lock()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            for p in list(self.procs):
                try:
                    p.terminate()
                except Exception:
                    pass

    def update(self, idx, status, progress=None):
        self.q.put((idx, status, progress))

    def run_one(self, idx, url):
        if self.stop_event.is_set():
            self.update(idx, 'Annullato')
            return
        output = None
        try:
            video_id = get_video_id(url)
            self.update(idx, 'Recupero link...')
            playlist, title, reason = fetch_info(video_id, url)
            note = '' if title else f' (titolo non letto: {reason})'

            name = safe_name(title) or video_id
            output = os.path.join(self.out_dir, name + '.mp4')
            if os.path.exists(output):
                self.update(idx, 'Già presente', 100)
                return

            tmp = output + '.part.mp4'
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-progress', 'pipe:1', '-nostats',
                '-allowed_segment_extensions', 'ALL',
                '-extension_picky', '0',
                '-i', playlist,
                '-map', '0:v:0', '-map', '0:a:0',
                '-bsf:a', 'aac_adtstoasc',
                '-c', 'copy',
                tmp,
            ]
            self.update(idx, 'Download...' + note, 0)
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors='replace', creationflags=NO_WINDOW,
            )
            with self.lock:
                self.procs.add(proc)

            duration = probe_duration(playlist)
            last_lines = []
            for line in proc.stdout:
                line = line.strip()
                last_lines = (last_lines + [line])[-5:]
                m = re.match(r'out_time_(?:us|ms)=(\d+)', line)
                if m:
                    # out_time_ms e out_time_us sono entrambi in microsecondi
                    if duration:
                        pct = min(99, int(int(m.group(1)) / 1e6 / duration * 100))
                        self.update(idx, 'Download...' + note, pct)
            proc.wait()
            with self.lock:
                self.procs.discard(proc)

            if self.stop_event.is_set():
                self.update(idx, 'Annullato')
                self._cleanup(tmp)
                return
            if proc.returncode != 0:
                self._cleanup(tmp)
                raise RuntimeError('ffmpeg: ' + ' | '.join(last_lines))

            os.replace(tmp, output)
            mean = audio_mean_volume(output)
            if mean is None or mean < -50:
                label = 'senza audio' if mean is None else f'audio quasi muto, medio {mean:.0f} dB'
                self.update(idx, f'Completato ({label})', 100)
            else:
                self.update(idx, 'Completato', 100)
        except Exception as e:
            self.update(idx, f'Errore: {e}')

    @staticmethod
    def _cleanup(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


# --------------------------------- interfaccia ---------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('FloGrappling Downloader')
        self.geometry('900x620')
        self.minsize(760, 520)
        self.q = queue.Queue()
        self.downloader = None
        self.executor = None
        self.rows = []

        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Downloads'))
        self.workers = tk.IntVar(value=3)

        self._build()
        self.after(150, self._poll)

    def _build(self):
        pad = {'padx': 10, 'pady': 5}

        ttk.Label(self, text='Incolla i link (uno per riga):').pack(anchor='w', **pad)
        frame = ttk.Frame(self)
        frame.pack(fill='x', padx=10)
        self.text = tk.Text(frame, height=8, wrap='none')
        sb = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side='left', fill='x', expand=True)
        sb.pack(side='right', fill='y')

        opts = ttk.Frame(self)
        opts.pack(fill='x', **pad)
        ttk.Label(opts, text='Cartella:').pack(side='left')
        ttk.Entry(opts, textvariable=self.out_dir).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(opts, text='Sfoglia...', command=self._choose_dir).pack(side='left')
        ttk.Label(opts, text='   Download simultanei:').pack(side='left')
        ttk.Spinbox(opts, from_=1, to=8, width=3, textvariable=self.workers).pack(side='left', padx=5)

        btns = ttk.Frame(self)
        btns.pack(fill='x', **pad)
        self.start_btn = ttk.Button(btns, text='Avvia download', command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(btns, text='Ferma tutto', command=self.stop, state='disabled')
        self.stop_btn.pack(side='left', padx=8)
        ttk.Button(btns, text='Apri cartella', command=self._open_dir).pack(side='left')

        cols = ('n', 'link', 'stato', 'perc')
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=12)
        for c, t, w in (('n', '#', 40), ('link', 'Link', 420), ('stato', 'Stato', 300), ('perc', '%', 60)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w' if c != 'perc' else 'e')
        self.tree.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        self.summary = ttk.Label(self, text='')
        self.summary.pack(anchor='w', padx=10, pady=(0, 8))

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    def _open_dir(self):
        d = self.out_dir.get()
        if os.path.isdir(d):
            if sys.platform.startswith('win'):
                os.startfile(d)
            elif sys.platform == 'darwin':
                subprocess.run(['open', d])
            else:
                subprocess.run(['xdg-open', d])

    def start(self):
        if not shutil.which('ffmpeg'):
            messagebox.showerror('ffmpeg mancante',
                                 'ffmpeg non è installato o non è nel PATH.\n'
                                 'Installalo con: winget install Gyan.FFmpeg')
            return
        raw = self.text.get('1.0', 'end')
        urls = re.findall(r'https?://[^\s"\'<>]+', raw)
        urls += [t for t in raw.split() if t.isdigit()]  # anche solo ID numerici
        urls = list(dict.fromkeys(urls))  # toglie i duplicati mantenendo l'ordine
        if not urls:
            messagebox.showinfo('Nessun link', 'Incolla almeno un link.')
            return
        out = self.out_dir.get()
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as e:
            messagebox.showerror('Cartella non valida', str(e))
            return

        self.tree.delete(*self.tree.get_children())
        self.rows = []
        for i, u in enumerate(urls):
            iid = self.tree.insert('', 'end', values=(i + 1, u, 'In coda', ''))
            self.rows.append(iid)

        self.downloader = Downloader(self.q, out)
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(self.workers.get())))
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        for i, u in enumerate(urls):
            self.executor.submit(self.downloader.run_one, i, u)
        threading.Thread(target=self._wait_done, daemon=True).start()

    def _wait_done(self):
        self.executor.shutdown(wait=True)
        self.q.put(('done', None, None))

    def stop(self):
        if self.downloader:
            self.downloader.stop()
        self.stop_btn.config(state='disabled')

    def _poll(self):
        try:
            while True:
                idx, status, prog = self.q.get_nowait()
                if idx == 'done':
                    self.start_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self._summary()
                    continue
                iid = self.rows[idx]
                vals = list(self.tree.item(iid, 'values'))
                vals[2] = status
                if prog is not None:
                    vals[3] = f'{prog}%'
                self.tree.item(iid, values=vals)
                self._summary()
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _summary(self):
        ok = err = 0
        for iid in self.rows:
            s = self.tree.item(iid, 'values')[2]
            if s.startswith('Completato') or s == 'Già presente':
                ok += 1
            elif s.startswith('Errore'):
                err += 1
        self.summary.config(text=f'Completati: {ok}   Errori: {err}   Totale: {len(self.rows)}')


if __name__ == '__main__':
    try:
        App().mainloop()
    except Exception:
        import traceback
        traceback.print_exc()
        input('\nErrore all\'avvio. Premi Invio per chiudere...')