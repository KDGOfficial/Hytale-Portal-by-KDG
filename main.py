import tkinter as tk
from tkinter import messagebox, scrolledtext
import requests
import feedparser
from datetime import datetime
import threading
import re
import webbrowser
import webview # pip install pywebview
import multiprocessing
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import quote_plus
import time
from io import BytesIO
from PIL import Image, ImageTk # pip install Pillow

# --- НАСТРОЙКИ ---
HYTALE_API_URL = "https://hytale.com/api/blog/post/published"
RELEASE_DATE = datetime(2026, 1, 13, 0, 0, 0)
CACHE_FILE = "news_cache_v3.json" # Кэш

APP_NAME = "KDG Hytale Portal"
APP_VERSION = "1.0.0-KDG"

CHANNELS_DATA = [
    {"name": "Hytale (Official)", "url": "https://www.youtube.com/@Hytale", "id": "UCgQN2C6x-1AobLFMpewpAZw"},
    {"name": "Jetik Hytale", "url": "https://www.youtube.com/@jetikhytale", "id": "UCwPAi_m6sL9zy_R64_XiHww"},
    {"name": "Zifirsky", "url": "https://www.youtube.com/@Zifirsky", "id": None},
]

# ----------------- ДИЗАЙН (стиль Hytale) -----------------
HYTALE_STYLE = {
    'bg': '#030b14',        # почти ночное небо
    'card_bg': '#0c1520',   # глубокий темный
    'text': '#e7f4ff',
    'accent': '#f3d983',    # золотистый
    'link': '#a8e0ff',
    'date': '#a1b7d0',
    'video_bg': '#091721',
    'panel': '#0a1b2a'
}

# ----------------- УТИЛИТЫ -----------------

def launch_browser_process(title, url):
    """Запуск webview в отдельном процессе — позволяет проигрывать видео внутри нативного браузера.
    webview будет открываться как отдельное окно приложения, но выглядит "встроено" в рабочий процесс.
    """
    try:
        webview.create_window(title, url, width=1280, height=720, resizable=True)
        webview.start()
    except Exception as e:
        print('Ошибка запуска webview:', e)

class HytaleApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} — v{APP_VERSION}")
        self.root.geometry("820x820")
        self.root.configure(bg=HYTALE_STYLE['bg'])

        self.colors = HYTALE_STYLE
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        self.news_cache = self.load_cache()
        self.translator = None
        self.image_refs = [] # держим объекты PhotoImage

        # Попытка инициализировать googletrans (необязательно)
        try:
            from googletrans import Translator
            try:
                self.translator = Translator(service_urls=['translate.googleapis.com'])
            except:
                self.translator = Translator()
        except:
            self.translator = None

        # --- Header (стилизованный) ---
        header = tk.Canvas(root, height=140, bg=self.colors['bg'], highlightthickness=0)
        header.pack(fill='x')
        header.create_rectangle(0, 0, 820, 140, fill=self.colors['bg'], outline='')
        try:
            logo = Image.open('logo.png')
            ratio = logo.width / logo.height
            target_h = 110
            logo = logo.resize((int(target_h * ratio), target_h), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(logo)
            header.create_image(410, 70, image=self.logo_photo, tags='logo')
        except Exception:
            header.create_text(410, 60, text='HYTALE', font=('Cinzel', 40, 'bold'), fill=self.colors['accent'], tags='logo')
        self.header_tagline = header.create_text(410, 125, text='Новости, видео и многое другое!', font=('Segoe UI', 12, 'italic'), fill=self.colors['date'])
        self.header_line = header.create_line(100, 140, 720, 140, fill=self.colors['accent'], width=2)
        name_lbl = tk.Label(root, text=APP_NAME, bg=self.colors['bg'], fg=self.colors['accent'], font=('Cinzel', 16, 'bold'))
        name_lbl.pack(pady=(6, 0))
        self.header_canvas = header
        self.root.bind('<Configure>', self._adjust_header)

        # Таймер релиза
        self.timer_lbl = tk.Label(root, text='...', font=('Courier New', 14, 'bold'), bg=self.colors['bg'], fg=self.colors['accent'])
        self.timer_lbl.pack(pady=(6, 4))

        # Разделы
        self.create_section('📰 Новости Hytale.com ', 'news_container')
        self.create_section('📺 Свежие видео', 'yt_container')

        self.refresh_btn = tk.Button(root, text='🔄 ОБНОВИТЬ', command=self.start_update,
                                     bg=self.colors['accent'], fg='#111', font=('Segoe UI', 10, 'bold'), relief='flat', padx=14, pady=7)
        self.refresh_btn.pack(pady=12)
        self.clear_cache_btn = tk.Button(root, text='🧹 ОЧИСТИТЬ КЭШ', command=self.clear_cache,
                                         bg=self.colors['card_bg'], fg=self.colors['text'], font=('Arial', 9), relief='ridge', bd=1)
        self.clear_cache_btn.pack(pady=(0,8))

        footer = tk.Frame(root, bg=self.colors['bg'])
        footer.pack(side='bottom', fill='x')
        self.status_bar = tk.Label(footer, text='Готов', bg=self.colors['card_bg'], fg=self.colors['date'], anchor='w')
        self.status_bar.pack(side='left', fill='x', expand=True)
        version_lbl = tk.Label(footer, text=f'Version {APP_VERSION}', bg=self.colors['bg'], fg=self.colors['date'])
        version_lbl.pack(side='right', padx=8)
        attribution = tk.Label(footer, text='Created by KDG', bg=self.colors['bg'], fg=self.colors['accent'], cursor='hand2')
        attribution.pack(side='right', padx=12)
        attribution.bind('<Button-1>', lambda e: self._open_link('https://bio.link/kdg_info'))

        self.update_timer()
        self.start_update()

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_cache(self):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.news_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения кэша: {e}")

    def clear_cache(self):
        self.news_cache = {}
        if os.path.exists(CACHE_FILE):
            try:
                os.remove(CACHE_FILE)
            except Exception as e:
                messagebox.showerror('Ошибка', f'Не удалось удалить кэш: {e}')
                return
        self.status_bar.config(text='Кэш очищен')

    # --- Парсер — как у вас был, без изменений логики ---
    def fetch_news_content_structured(self, url):
        cached = self.news_cache.get(url)
        if isinstance(cached, dict) and cached.get('blocks'):
            return cached['blocks']
        if isinstance(cached, list):
            return cached
        try:
            self.root.after(0, lambda: self.status_bar.config(text=f"Загрузка статьи..."))
            r = requests.get(url, headers=self.headers, timeout=12)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            article = soup.find('div', class_=re.compile('post-body|content|article-body')) or soup.find('article') or soup.find('main')
            structured = []
            if article:
                for e in article.find_all(['script','style','nav','header','footer','aside']): e.decompose()
                for element in article.find_all(['p','h1','h2','h3','img','figure','iframe','div','ul','ol']):
                    if element.name == 'iframe' and 'youtube' in element.get('src',''):
                        src = element.get('src')
                        m = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', src)
                        if m:
                            vid = m.group(1)
                            structured.append({'type':'video','src':f'https://www.youtube.com/embed/{vid}'})
                        else:
                            structured.append({'type':'video','src':src})
                    elif element.name == 'img':
                        src = element.get('src')
                        if src: structured.append({'type':'img','src':src})
                    elif element.name == 'figure':
                        img = element.find('img')
                        if img and img.get('src'):
                            structured.append({'type':'img','src':img.get('src')})
                            figcap = element.find('figcaption')
                            if figcap and figcap.get_text(strip=True):
                                structured.append({'type':'text','content':f"[Подпись: {figcap.get_text(strip=True)}]", 'style':'caption'})
                    elif element.name in ['p','h1','h2','h3','ul','ol']:
                        text = element.get_text(strip=True)
                        if text and len(text) > 6:
                            style = 'header' if element.name.startswith('h') else 'normal'
                            structured.append({'type':'text','content':text,'style':style})
            else:
                structured = [{'type':'text','content':'Не удалось извлечь содержимое статьи.','style':'error'}]
            self.news_cache[url] = {'blocks': structured}
            self.save_cache()
            return structured
        except Exception as e:
            print('Ошибка загрузки новости:', e)
            return [{'type':'text','content':f'Ошибка загрузки: {e}','style':'error'}]

    # --- Перевод ---
    def translate_text(self, text):
        if not text or not text.strip(): return text
        if self.translator:
            try:
                if getattr(self.translator.detect(text),'lang','') == 'ru': return text
            except: pass
            try:
                res = self.translator.translate(text, dest='ru')
                if getattr(res, 'text', None): return res.text
            except: pass
        try:
            return self._translate_via_googleapi(text)
        except:
            return text

    def _translate_blocks(self, blocks):
        translated = []
        for b in blocks:
            if b['type'] == 'text':
                translated.append({'type':'text','content':self.translate_text(b['content']),'style':b.get('style','normal')})
            else:
                translated.append(b)
        return translated

    def _translate_via_googleapi(self, text):
        if not text: return text
        try:
            q = quote_plus(text)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ru&dt=t&q={q}"
            r = requests.get(url, headers={'User-Agent': self.headers['User-Agent']}, timeout=10)
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return ''.join([s[0] for s in data[0] if s and s[0]])
        except: pass
        return text

    # --- Просмотр статьи (как у вас) ---
    def open_news_window(self, url, title):
        def load():
            data = self.fetch_news_content_structured(url)
            self.root.after(0, lambda: self.status_bar.config(text='Перевод...'))
            cached = self.news_cache.get(url)
            translated = None
            if isinstance(cached, dict):
                translated = cached.get('translated')
            if not translated:
                translated = self._translate_blocks(data)
                if isinstance(cached, dict):
                    cached['translated'] = translated
                    cached['blocks'] = data
                else:
                    self.news_cache[url] = {'blocks': data, 'translated': translated}
                self.save_cache()
            self.root.after(0, lambda: self._create_news_window(title, translated, url))
            self.root.after(0, lambda: self.status_bar.config(text='Готово'))
        threading.Thread(target=load, daemon=True).start()

    def _create_news_window(self, title, content_blocks, original_url):
        w = tk.Toplevel(self.root)
        w.title(title)
        w.geometry('1000x820')
        w.configure(bg=self.colors['bg'])
        # header
        hf = tk.Frame(w, bg=self.colors['card_bg'])
        hf.pack(fill='x', padx=8, pady=8)
        tk.Label(hf, text=title, font=('Arial', 14, 'bold'), bg=self.colors['card_bg'], fg=self.colors['text']).pack(anchor='w', padx=8, pady=6)
        tk.Label(hf, text=original_url, font=('Arial', 9), bg=self.colors['card_bg'], fg=self.colors['link'], cursor='hand2').pack(anchor='w', padx=8)

        # scroll area
        main = tk.Frame(w, bg=self.colors['bg'])
        main.pack(fill='both', expand=True, padx=8, pady=4)
        canvas = tk.Canvas(main, bg=self.colors['card_bg'], highlightthickness=0)
        sb = tk.Scrollbar(main, orient='vertical', command=canvas.yview)
        frame = tk.Frame(canvas, bg=self.colors['card_bg'])
        frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0,0), window=frame, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        def _on_mousewheel(event):
            if hasattr(event, 'delta') and event.delta:
                canvas.yview_scroll(-int(event.delta / 120), 'units')
            elif getattr(event, 'num', None) == 4:
                canvas.yview_scroll(-1, 'units')
            elif getattr(event, 'num', None) == 5:
                canvas.yview_scroll(1, 'units')

        canvas.bind('<Enter>', lambda e: canvas.focus_set())
        canvas.bind('<MouseWheel>', _on_mousewheel)
        canvas.bind('<Button-4>', _on_mousewheel)
        canvas.bind('<Button-5>', _on_mousewheel)

        self._render_content_blocks(frame, content_blocks, w)

    def _open_link(self, url):
        try:
            webbrowser.open_new_tab(url)
            self.status_bar.config(text='Открыт KDG-профиль')
        except Exception as exc:
            messagebox.showerror('Ошибка', f'Не удалось открыть ссылку: {exc}')

    def _render_content_blocks(self, parent, blocks, window):
        for block in blocks:
            if block['type'] == 'text':
                self._render_text_block(parent, block)
            elif block['type'] == 'img':
                self._render_image_block(parent, block, window)
            elif block['type'] == 'video':
                self._render_video_block(parent, block)

    def _render_text_block(self, parent, block):
        f = tk.Frame(parent, bg=self.colors['card_bg'])
        f.pack(fill='x', padx=12, pady=6)
        fonts = {'header':('Arial', 13, 'bold'), 'caption':('Arial', 9, 'italic'), 'error':('Arial', 11), 'normal':('Arial', 11)}
        colors = {'header':self.colors['accent'], 'caption':self.colors['text'], 'error':'#ff6b6b', 'normal':self.colors['text']}
        tk.Label(f, text=block['content'], font=fonts.get(block.get('style','normal')), fg=colors.get(block.get('style','normal')), bg=self.colors['card_bg'], wraplength=880, justify='left').pack()

    def _render_image_block(self, parent, block, window):
        f = tk.Frame(parent, bg=self.colors['card_bg'])
        f.pack(fill='x', padx=12, pady=8)
        ph = tk.Label(f, text='🖼️ Загрузка...', bg=self.colors['card_bg'], fg=self.colors['date'])
        ph.pack()
        threading.Thread(target=self._download_and_display_image, args=(block['src'], f, ph, window), daemon=True).start()

    def _download_and_display_image(self, url, frame, placeholder, window):
        try:
            if url.startswith('/'):
                url = 'https://hytale.com' + url
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert('RGBA')
            target_w = 880
            if img.width > target_w:
                wpercent = (target_w / float(img.width))
                hsize = int((float(img.height) * float(wpercent)))
                img = img.resize((target_w, hsize), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            def upd():
                placeholder.destroy()
                lbl = tk.Label(frame, image=photo, bg=self.colors['card_bg'])
                lbl.image = photo
                self.image_refs.append(photo)
                lbl.pack(pady=6)
            window.after(0, upd)
        except Exception as e:
            def err():
                placeholder.config(text=f'Ошибка: {e}', fg='#ff6b6b')
            window.after(0, err)

    def _render_video_block(self, parent, block):
        # Create a frame with a distinct background and border
        f = tk.Frame(parent, bg=self.colors['video_bg'], bd=1, relief='groove')
        f.pack(fill='x', padx=12, pady=8, ipady=4)
        
        # Make the entire frame clickable
        def open_video(event):
            import webbrowser
            webbrowser.open(block['src'])
            
        f.bind('<Button-1>', open_video)
        
        # Add a header with video icon and title
        header = tk.Frame(f, bg=self.colors['video_bg'])
        header.pack(fill='x', padx=8, pady=4)
        
        # Make header clickable too
        header.bind('<Button-1>', open_video)
        
        # Video icon and title
        tk.Label(header, 
                text='🎥 ВИДЕО (нажмите для просмотра)', 
                font=('Arial', 10, 'bold'), 
                fg=self.colors['accent'], 
                bg=self.colors['video_bg'],
                cursor='hand2').pack(side='left')
        
        # Add the video URL as a clickable link
        url_frame = tk.Frame(f, bg=self.colors['video_bg'])
        url_frame.pack(fill='x', pady=(0, 4))
        url_frame.bind('<Button-1>', open_video)
        
        # Truncate long URLs for display
        display_url = block['src']
        if len(display_url) > 60:
            display_url = display_url[:30] + '...' + display_url[-25:]
            
        url_label = tk.Label(url_frame, 
                           text=display_url, 
                           font=('Arial', 8), 
                           fg=self.colors['link'], 
                           bg=self.colors['video_bg'],
                           cursor='hand2')
        url_label.pack()
        url_label.bind('<Button-1>', open_video)

    # --- Видео и превью в основном окне для каналов YouTube ---
    def open_in_app_viewer(self, url, title, is_youtube=False):
        if is_youtube:
            # извлекаем id
            m = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url)
            vid = m.group(1) if m else None
            if vid:
                embed = f'https://www.youtube.com/embed/{vid}?autoplay=1&rel=0'
                self.status_bar.config(text=f'Открытие видео: {title}')
                # Запускаем webview в отдельном процессе, чтобы не блокировать Tk
                p = multiprocessing.Process(target=launch_browser_process, args=(title, embed))
                p.start()
            else:
                # если это уже embed-ссылка
                p = multiprocessing.Process(target=launch_browser_process, args=(title, url))
                p.start()
        else:
            self.open_news_window(url, title)

    def create_section(self, title, container_name):
        frame = tk.Frame(self.root, bg=self.colors['bg'])
        frame.pack(fill='both', padx=16, pady=(8,0))
        tk.Label(frame, text=title, font=('Arial', 12, 'bold'), bg=self.colors['bg'], fg=self.colors['text']).pack(anchor='w', pady=(2,6))
        container = tk.Frame(frame, bg=self.colors['card_bg'])
        container.pack(fill='both', expand=True)
        setattr(self, container_name, container)

    def _adjust_header(self, event=None):
        if not hasattr(self, 'header_canvas'): return
        width = max(self.root.winfo_width(), 400)
        line_y = 140
        tagline_y = 125
        logo_x = width//2
        self.header_canvas.coords(self.header_line, 100, line_y, max(220, width-100), line_y)
        self.header_canvas.coords(self.header_tagline, width//2, tagline_y)
        self.header_canvas.coords('logo', logo_x, 70)

    def update_timer(self):
        now = datetime.now()
        rem = RELEASE_DATE - now
        if rem.total_seconds() > 0:
            d = rem.days
            h, rems = divmod(rem.seconds, 3600)
            m, s = divmod(rems, 60)
            txt = f'Ранний доступ: {d} дн. {h:02}:{m:02}:{s:02}'
            color = self.colors['accent']
        else:
            txt = '🚀 ИГРА ВЫШЛА! 🚀'
            color = '#00e676'
        self.timer_lbl.config(text=txt, fg=color)
        self.root.after(1000, self.update_timer)

    def get_real_channel_id(self, url):
        try:
            r = requests.get(url, headers=self.headers, timeout=5)
            match = re.search(r'"channelId":"(UC[\w-]{22})"', r.text)
            if match: return match.group(1)
            match_alt = re.search(r'https://www.youtube.com/channel/(UC[\w-]{22})', r.text)
            if match_alt: return match_alt.group(1)
        except: pass
        return None

    def start_update(self):
        self.refresh_btn.config(state='disabled', text='Загрузка...')
        self.status_bar.config(text='Обновление данных...')
        threading.Thread(target=self.fetch_all_data, daemon=True).start()

    def fetch_all_data(self):
        self.clear_frame(self.news_container)
        self.clear_frame(self.yt_container)
        # --- Hytale news ---
        try:
            r = requests.get(HYTALE_API_URL, headers=self.headers, timeout=10)
            if r.status_code == 200:
                posts = r.json()
                for post in posts[:4]:
                    title = post.get('title','No Title')
                    slug = post.get('slug','')
                    dt = datetime.fromisoformat(post.get('publishedAt','').replace('Z','+00:00'))
                    url = f"https://hytale.com/news/{dt.year}/{dt.strftime('%m')}/{slug}"
                    self.add_item(self.news_container, f"{dt.strftime('%d.%m')} | {title}", url, self.colors['link'], is_youtube=False)
            else:
                self.add_error(self.news_container, f"Сайт недоступен (Код {r.status_code})")
        except Exception as e:
            self.add_error(self.news_container, f"Ошибка доступа к API Hytale: {e}")

        # --- YouTube channels ---
        for ch in CHANNELS_DATA:
            try:
                current_id = ch.get('id')
                if current_id:
                    rss_url = f'https://www.youtube.com/feeds/videos.xml?channel_id={current_id}'
                else:
                    rss_url = None
                feed = None
                if rss_url:
                    xml = requests.get(rss_url, headers=self.headers, timeout=6)
                    feed = feedparser.parse(xml.content)
                if not feed or not feed.entries:
                    new_id = self.get_real_channel_id(ch['url'])
                    if new_id:
                        ch['id'] = new_id
                        xml = requests.get(f'https://www.youtube.com/feeds/videos.xml?channel_id={new_id}', headers=self.headers, timeout=6)
                        feed = feedparser.parse(xml.content)

                if feed and feed.entries:
                    video = feed.entries[0]
                    # Получаем ID видео
                    m = re.search(r'v=([0-9A-Za-z_-]{11})', video.link)
                    vid = m.group(1) if m else None
                    self.add_item(self.yt_container, f"[{ch['name']}] {video.title}", video.link, self.colors['text'], is_youtube=True, youtube_id=vid)
                else:
                    self.add_error(self.yt_container, f"{ch['name']}: Видео не найдены")
            except Exception as e:
                self.add_error(self.yt_container, f"{ch['name']}: Ошибка загрузки: {e}")

        self.root.after(0, lambda: self.refresh_btn.config(state='normal', text='🔄 ОБНОВИТЬ'))
        self.root.after(0, lambda: self.status_bar.config(text=f"Обновлено: {datetime.now().strftime('%H:%M:%S')}") )

    def clear_frame(self, frame):
        for w in frame.winfo_children(): w.destroy()

    def add_item(self, container, text, url, color, is_youtube=False, youtube_id=None):
        row = tk.Frame(container, bg=self.colors['card_bg'])
        row.pack(fill='x', pady=6, padx=6)
        if is_youtube and youtube_id:
            # Превью миниатюры
            thumb_url = f'https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg'
            thumb_label = tk.Label(row, text='Загрузка превью...', bg=self.colors['card_bg'], fg=self.colors['date'])
            thumb_label.pack(side='left', padx=(4,8))
            # Загружаем изображение в фоне
            def load_thumb():
                try:
                    r = requests.get(thumb_url, timeout=8)
                    r.raise_for_status()
                    img = Image.open(BytesIO(r.content)).convert('RGBA')
                    target_h = 84
                    w = int(img.width * (target_h / img.height))
                    img = img.resize((w, target_h), Image.Resampling.LANCZOS)
                    ph = ImageTk.PhotoImage(img)
                    def set_ui():
                        thumb_label.config(image=ph, text='')
                        thumb_label.image = ph
                        self.image_refs.append(ph)
                    self.root.after(0, set_ui)
                except Exception as e:
                    def err():
                        thumb_label.config(text='❌', fg='#ff6b6b')
                    self.root.after(0, err)
            threading.Thread(target=load_thumb, daemon=True).start()

            txt_frame = tk.Frame(row, bg=self.colors['card_bg'])
            txt_frame.pack(fill='x', expand=True, side='left')
            lbl = tk.Label(txt_frame, text=text, font=('Arial', 10, 'bold'), fg=color, bg=self.colors['card_bg'], cursor='hand2', wraplength=540, justify='left')
            lbl.pack(anchor='w')
            sub = tk.Label(txt_frame, text=url, font=('Arial', 8), fg=self.colors['date'], bg=self.colors['card_bg'])
            sub.pack(anchor='w')
            play = tk.Button(row, text='▶', bg=self.colors['accent'], fg='#111', command=lambda: self.open_in_app_viewer(url, text, is_youtube=True))
            play.pack(side='right', padx=8)
            lbl.bind('<Button-1>', lambda e: self.open_in_app_viewer(url, text, is_youtube=True))
        else:
            lbl = tk.Label(row, text=text, font=('Arial', 11), fg=color, bg=self.colors['card_bg'], cursor='hand2', wraplength=740, justify='left')
            lbl.pack(fill='x', padx=6, pady=6)
            lbl.bind('<Button-1>', lambda e: self.open_in_app_viewer(url, text, is_youtube=False))

    def add_error(self, container, msg):
        tk.Label(container, text=f'⚠️ {msg}', fg='#ff6b6b', bg=self.colors['card_bg'], font=('Arial', 9)).pack(anchor='w', padx=8, pady=4)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = HytaleApp(root)
    root.mainloop()
