import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
import requests
import feedparser
from datetime import datetime
import threading
import re
import webbrowser
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import quote_plus
import time
from io import BytesIO
from PIL import Image, ImageTk
import pygame
from mutagen import File as MutagenFile                     

                   
HYTALE_API_URL = "https://hytale.com/api/blog/post/published"
RELEASE_DATE = datetime(2026, 1, 13, 0, 0, 0)
CACHE_FILE = "news_cache_v3.json"      

APP_NAME = "KDG Hytale Portal"
APP_VERSION = "1.2.0-KDG"

CHANNELS_DATA = [
    {"name": "Hytale (Official)", "url": "https://www.youtube.com/@Hytale", "id": "UCgQN2C6x-1AobLFMpewpAZw"},
    {"name": "Jetik Hytale", "url": "https://www.youtube.com/@jetikhytale", "id": "UCwPAi_m6sL9zy_R64_XiHww"},
    {"name": "Zifirsky", "url": "https://www.youtube.com/@Zifirsky", "id": None},
]

def extract_youtube_id(url):
    if not url:
        return None
    patterns = [
        r'youtu\.be/([0-9A-Za-z_-]{11})',
        r'/(?:embed|shorts)/([0-9A-Za-z_-]{11})',
        r'v=([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def normalize_youtube_url(url):
    vid = extract_youtube_id(url)
    if vid:
        return f'https://www.youtube.com/watch?v={vid}'
    return url

HYTALE_STYLE = {
    'bg': '#030b14',                           
    'card_bg': '#0c1520',                    
    'text': '#e7f4ff',
    'accent': '#f3d983',                
    'link': '#a8e0ff',
    'date': '#a1b7d0',
    'video_bg': '#091721',
    'panel': '#0a1b2a'
}

                                             

class HytaleApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} — v{APP_VERSION}")
        self.root.geometry("1200x900")
        self.root.minsize(1024, 720)
        self.root.state('zoomed')
        self.root.configure(bg=HYTALE_STYLE['bg'])

        self.colors = HYTALE_STYLE
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        self.news_cache = self.load_cache()
        self.translator = None
        self.image_refs = []                            
        # Music player related
        self.music_folder = os.path.join(os.getcwd(), 'Music')
        self.music_files = []
        self.music_index = 0
        # Using pygame for audio playback
        self.pygame_available = False
        self.is_muted = False
        self._is_paused = False
        self.favorites_file = 'music_favorites.json'
        self.favorites = set()
        self._last_playing_state = False
        self._volume = 0.21  # Default volume set to 21%

                                                              
        try:
            from googletrans import Translator
            try:
                self.translator = Translator(service_urls=['translate.googleapis.com'])
            except:
                self.translator = Translator()
        except:
            self.translator = None

                                        
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

                       
        self.timer_lbl = tk.Label(root, text='...', font=('Courier New', 14, 'bold'), bg=self.colors['bg'], fg=self.colors['accent'])
        self.timer_lbl.pack(pady=(6, 4))

                 
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

        # Initialize music player asynchronously so it doesn't block UI
        threading.Thread(target=self._init_music_player, daemon=True).start()

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
                
        hf = tk.Frame(w, bg=self.colors['card_bg'])
        hf.pack(fill='x', padx=8, pady=8)
        tk.Label(hf, text=title, font=('Arial', 14, 'bold'), bg=self.colors['card_bg'], fg=self.colors['text']).pack(anchor='w', padx=8, pady=6)
        tk.Label(hf, text=original_url, font=('Arial', 9), bg=self.colors['card_bg'], fg=self.colors['link'], cursor='hand2').pack(anchor='w', padx=8)

                     
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
        frame.bind('<MouseWheel>', _on_mousewheel)
        frame.bind('<Button-4>', _on_mousewheel)
        frame.bind('<Button-5>', _on_mousewheel)
        w.bind('<MouseWheel>', _on_mousewheel)
        w.bind('<Button-4>', _on_mousewheel)
        w.bind('<Button-5>', _on_mousewheel)

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
                                                              
        f = tk.Frame(parent, bg=self.colors['video_bg'], bd=1, relief='groove')
        f.pack(fill='x', padx=12, pady=8, ipady=4)
        
                                         
        def open_video(event):
            import webbrowser
            webbrowser.open(block['src'])
            
        f.bind('<Button-1>', open_video)
        
                                                
        header = tk.Frame(f, bg=self.colors['video_bg'])
        header.pack(fill='x', padx=8, pady=4)
        
                                   
        header.bind('<Button-1>', open_video)
        
                              
        tk.Label(header, 
                text='🎥 ВИДЕО (нажмите для просмотра)', 
                font=('Arial', 10, 'bold'), 
                fg=self.colors['accent'], 
                bg=self.colors['video_bg'],
                cursor='hand2').pack(side='left')
        
                                               
        url_frame = tk.Frame(f, bg=self.colors['video_bg'])
        url_frame.pack(fill='x', pady=(0, 4))
        url_frame.bind('<Button-1>', open_video)
        
                                        
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

                                                                
    def open_in_app_viewer(self, url, title, is_youtube=False):
        target_url = url
        if is_youtube:
            target_url = normalize_youtube_url(url)
            self.status_bar.config(text=f'Открытие видео: {title}')
            try:
                webbrowser.open_new_tab(target_url)
            except Exception as exc:
                messagebox.showerror('Ошибка', f'Не удалось открыть видео: {exc}')
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
                                       
                    m = re.search(r'v=([0-9A-Za-z_-]{11})', video.link)
                    vid = m.group(1) if m else None
                    self.add_item(self.yt_container, f"[{ch['name']}] {video.title}", video.link, self.colors['text'], is_youtube=True, youtube_id=vid)
                else:
                    self.add_error(self.yt_container, f"{ch['name']}: Видео не найдены")
            except Exception as e:
                self.add_error(self.yt_container, f"{ch['name']}: Ошибка загрузки: {e}")

        self.root.after(0, lambda: self.refresh_btn.config(state='normal', text='🔄 ОБНОВИТЬ'))
        self.root.after(0, lambda: self.status_bar.config(text=f"Обновлено: {datetime.now().strftime('%H:%M:%S')}") )

    # ------------------------ Music Player -----------------------------
    def _init_music_player(self):
        # Initialize pygame embedded audio backend (pygame + mutagen)
        try:
            # Initialize pygame mixer
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            
            # Set default volume to 21%
            self._volume = 0.21
            self._prev_volume = self._volume  # Initialize previous volume
            pygame.mixer.music.set_volume(self._volume)
            
            self.pygame_available = True
            self._is_paused = True  # Start paused until user interacts
            self.is_muted = False
            
            print('pygame mixer initialized with 21% volume')
            
            # Create music folder if it doesn't exist
            if not os.path.exists(self.music_folder):
                try:
                    os.makedirs(self.music_folder)
                except Exception as e:
                    print(f'Error creating music folder: {e}')
            
            # Scan for music files and load favorites
            self._scan_music_files()
            self._load_favorites()
            
            # Autoplay first track if available
            if self.music_files:
                self.music_index = 0
                self._play_index(self.music_index, set_volume=21)
            
            # Add player controls to the main window
            self._add_main_player_controls()
            
        except Exception as e:
            print('pygame/mutagen init failed:', e)
            self.pygame_available = False
            self.status_bar.config(text='Аудио недоступно. Установите pygame и mutagen для воспроизведения музыки.')
            # Disable buttons if they exist
            if hasattr(self, 'mute_btn'):
                self.mute_btn.config(state='disabled')
            if hasattr(self, 'open_player_btn'):
                self.open_player_btn.config(state='disabled')
            return

    def _scan_music_files(self):
        exts = ('.mp3', '.ogg', '.wav', '.flac', '.aac', '.m4a')
        files = []
        try:
            for fname in sorted(os.listdir(self.music_folder)):
                if fname.lower().endswith(exts):
                    files.append(os.path.join(self.music_folder, fname))
        except Exception as e:
            print('Error scanning music folder:', e)
        self.music_files = files
        return files

    def _load_favorites(self):
        try:
            if os.path.exists(self.favorites_file):
                with open(self.favorites_file, 'r', encoding='utf-8') as f:
                    favs = json.load(f)
                    if isinstance(favs, list):
                        self.favorites = set(favs)
        except Exception as e:
            print('Failed to load favorites:', e)

    # settings handling removed (pygame-only player)

    def _save_favorites(self):
        try:
            with open(self.favorites_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.favorites), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('Failed to save favorites:', e)

    def _add_main_player_controls(self):
        # Add music player controls to the main window
        controls_frame = tk.Frame(self.root, bg=self.colors['bg'])
        controls_frame.pack(fill='x', padx=10, pady=5)
        
        # Mute/Unmute button
        self.mute_btn = tk.Button(controls_frame, text=' Музыка: Вкл', 
                                 command=self._toggle_mute,
                                 bg=self.colors['card_bg'], fg=self.colors['text'],
                                 relief='flat', font=('Segoe UI', 9))
        self.mute_btn.pack(side='left', padx=5)
        
        # Open player button
        self.open_player_btn = tk.Button(controls_frame, text='🎵 Открыть плеер', 
                                        command=self.open_player_window,
                                        bg=self.colors['accent'], fg='#111',
                                        relief='flat', font=('Segoe UI', 9, 'bold'))
        self.open_player_btn.pack(side='right', padx=5)
        
        # Set initial states
        if not self.pygame_available:
            self.mute_btn.config(state='disabled')
            self.open_player_btn.config(state='disabled')
            
    def _toggle_mute(self):
        if not self.pygame_available or not self.music_files:
            return
            
        if not hasattr(self, '_prev_volume'):
            self._prev_volume = self._volume
            
        if not self.is_muted:
            # If not muted, stop the music and store the current track
            if pygame.mixer.music.get_busy() and not self._is_paused:
                self._last_playing_index = self.music_index
                pygame.mixer.music.stop()
                self._is_paused = True
            self.is_muted = True
            self.mute_btn.config(text='🔇 Музыка: Выкл')
        else:
            # If muted, resume playback from the last track
            self.is_muted = False
            self.mute_btn.config(text='🔊 Музыка: Вкл')
            if hasattr(self, '_last_playing_index') and self._last_playing_index is not None:
                self._play_index(self._last_playing_index)
            else:
                self._play_index(0)

    def _play_index(self, index, set_volume=None):
        if not self.pygame_available or not self.music_files: 
            return
            
        if index < 0 or index >= len(self.music_files): 
            return
            
        self.music_index = index
        path = self.music_files[index]
        
        try:
            # Stop any currently playing music
            pygame.mixer.music.stop()
            
            # Load the new track
            pygame.mixer.music.load(path)
            
            # Set volume (default to 21% if not specified)
            if set_volume is not None:
                try:
                    self._volume = max(0.0, min(1.0, float(set_volume) / 100.0))
                except (ValueError, TypeError):
                    self._volume = 0.21
            
            # Apply volume and start playback
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
            self._is_paused = False
            
            # Update UI
            self._update_ui_after_play()
            
            # Update volume display if player window is open
            if hasattr(self, '_player_vol_scale'):
                self._player_vol_scale.set(int(self._volume * 100))
            if hasattr(self, '_player_vol_pct'):
                self._player_vol_pct.config(text=f"{int(self._volume * 100)}%")
            
        except Exception as e:
            print(f'Playback error: {e}')
            self.status_bar.config(text=f'Ошибка воспроизведения: {str(e)}')
    
    def _update_ui_after_play(self):
        """Update UI elements after changing tracks"""
        if hasattr(self, '_player_play_button'):
            self._player_play_button.config(text='⏸')
        
        if hasattr(self, '_player_lbl') and self.music_files:
            self._player_lbl.config(text=os.path.basename(self.music_files[self.music_index]))
        
        # Update listbox selection
        if hasattr(self, '_player_listbox_all'):
            self._select_current_in_lists()

    def _play_next(self):
        if not self.music_files: return
        self.music_index = (self.music_index + 1) % len(self.music_files)
        self._play_index(self.music_index)

    def _play_prev(self):
        if not self.music_files: return
        self.music_index = (self.music_index - 1) % len(self.music_files)
        self._play_index(self.music_index)

    def _toggle_play_pause(self, btn=None):
        if not self.pygame_available or not self.music_files:
            return
            
        try:
            if self._is_paused:
                # If paused, unpause
                pygame.mixer.music.unpause()
                self._is_paused = False
                if btn:
                    btn.config(text='⏸')
                self.status_bar.config(text='Воспроизведение')
            else:
                # If playing, pause
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.pause()
                    self._is_paused = True
                    if btn:
                        btn.config(text='▶')
                    self.status_bar.config(text='Пауза')
                else:
                    # If stopped, start playing current track
                    self._play_index(self.music_index)
        except Exception as e:
            print(f'Error in _toggle_play_pause: {e}')
            self.status_bar.config(text=f'Ошибка: {str(e)}')

    def open_player_window(self, event=None):
        """Complete player window with playlist, favorites, controls, volume, and seek."""
        if not self.pygame_available:
            messagebox.showerror('Ошибка', 'pygame и mutagen не установлены.')
            return
        if not self.music_files:
            messagebox.showinfo('Музыка', 'В папке Music нет треков.')
            return

        w = tk.Toplevel(self.root)
        w.title('Плеер')
        w.geometry('800x400')
        w.configure(bg=self.colors['bg'])

        # Track name label
        track_lbl = tk.Label(w, text=os.path.basename(self.music_files[self.music_index]),
                            bg=self.colors['card_bg'], fg=self.colors['text'], font=('Cinzel', 13, 'bold'))
        track_lbl.pack(fill='x', padx=8, pady=(8, 4))

        # Control buttons
        btn_frame = tk.Frame(w, bg=self.colors['card_bg'])
        btn_frame.pack(pady=6)

        def on_prev():
            self._play_prev()
            track_lbl.config(text=os.path.basename(self.music_files[self.music_index]))
            _refresh_lists()

        def on_play_pause():
            self._toggle_play_pause(play_btn)
            track_lbl.config(text=os.path.basename(self.music_files[self.music_index]))

        def on_next():
            self._play_next()
            track_lbl.config(text=os.path.basename(self.music_files[self.music_index]))
            _refresh_lists()

        tk.Button(btn_frame, text='⏮', command=on_prev, bg=self.colors['card_bg'],
                 fg=self.colors['text'], width=3, font=('Arial', 11, 'bold'), relief='flat').pack(side='left', padx=4)

        play_btn = tk.Button(btn_frame, text='⏸', command=on_play_pause, bg=self.colors['accent'],
                            fg='#111', width=4, font=('Arial', 12, 'bold'), relief='flat')
        play_btn.pack(side='left', padx=4)

        tk.Button(btn_frame, text='⏭', command=on_next, bg=self.colors['card_bg'],
                 fg=self.colors['text'], width=3, font=('Arial', 11, 'bold'), relief='flat').pack(side='left', padx=4)

        # Favorite button
        def toggle_fav():
            if self.music_files:
                path = self.music_files[self.music_index]
                if path in self.favorites:
                    self.favorites.remove(path)
                else:
                    self.favorites.add(path)
                self._save_favorites()
                fav_btn.config(text='★' if path in self.favorites else '☆')
                _refresh_lists()

        fav_btn = tk.Button(btn_frame, text='★' if self.music_files and self.music_files[self.music_index] in self.favorites else '☆',
                           command=toggle_fav, bg=self.colors['card_bg'], fg=self.colors['text'],
                           width=3, font=('Arial', 11), relief='flat')
        fav_btn.pack(side='left', padx=4)

        # Main container
        main_frame = tk.Frame(w, bg=self.colors['bg'])
        main_frame.pack(fill='both', expand=True, padx=8, pady=6)

        # LEFT: Playlist tabs
        left_frame = tk.Frame(main_frame, bg=self.colors['card_bg'])
        left_frame.pack(side='left', fill='y', padx=(0, 8))

        notebook = ttk.Notebook(left_frame)
        notebook.pack(fill='both', expand=True, padx=4, pady=4)

        all_tab = tk.Frame(notebook, bg=self.colors['card_bg'])
        fav_tab = tk.Frame(notebook, bg=self.colors['card_bg'])
        notebook.add(all_tab, text='Все')
        notebook.add(fav_tab, text='Избранное')

        listbox_all = tk.Listbox(all_tab, bg=self.colors['video_bg'], fg=self.colors['text'],
                                highlightthickness=0, bd=0, activestyle='none')
        listbox_all.pack(fill='both', expand=True, padx=4, pady=4)

        listbox_fav = tk.Listbox(fav_tab, bg=self.colors['video_bg'], fg=self.colors['text'],
                                highlightthickness=0, bd=0, activestyle='none')
        listbox_fav.pack(fill='both', expand=True, padx=4, pady=4)

        def _refresh_lists():
            listbox_all.delete(0, tk.END)
            listbox_fav.delete(0, tk.END)
            for path in self.music_files:
                name = os.path.basename(path)
                display = f"★ {name}" if path in self.favorites else name
                listbox_all.insert(tk.END, display)
                if path in self.favorites:
                    listbox_fav.insert(tk.END, name)

        def _on_listbox_play(event, lb):
            sel = lb.curselection()
            if not sel:
                return
            idx = sel[0]
            if lb is listbox_all:
                self.music_index = idx
            else:
                # Find by name in fav
                name = lb.get(idx)
                for i, p in enumerate(self.music_files):
                    if os.path.basename(p) == name:
                        self.music_index = i
                        break
            self._play_index(self.music_index)
            track_lbl.config(text=os.path.basename(self.music_files[self.music_index]))
            fav_btn.config(text='★' if self.music_files[self.music_index] in self.favorites else '☆')
            _refresh_lists()

        listbox_all.bind('<Double-Button-1>', lambda e: _on_listbox_play(e, listbox_all))
        listbox_fav.bind('<Double-Button-1>', lambda e: _on_listbox_play(e, listbox_fav))
        _refresh_lists()

        # RIGHT: Controls
        right_frame = tk.Frame(main_frame, bg=self.colors['card_bg'])
        right_frame.pack(side='left', fill='both', expand=True)

        # Volume
        vol_frame = tk.Frame(right_frame, bg=self.colors['card_bg'])
        vol_frame.pack(fill='x', padx=8, pady=4)
        tk.Label(vol_frame, text='Громкость:', bg=self.colors['card_bg'], fg=self.colors['text']).pack(side='left')

        vol_scale = tk.Scale(vol_frame, from_=0, to=100, orient='horizontal', bg=self.colors['card_bg'],
                            fg=self.colors['text'], length=200)
        vol_scale.set(int(self._volume * 100))
        vol_scale.pack(side='left', padx=8)

        vol_pct_lbl = tk.Label(vol_frame, text=f"{int(self._volume * 100)}%",
                              bg=self.colors['card_bg'], fg=self.colors['text'], width=3)
        vol_pct_lbl.pack(side='left')
        
        # Store volume controls for external access
        self._player_vol_scale = vol_scale
        self._player_vol_pct = vol_pct_lbl

        def _on_vol_change(v):
            pct = int(float(v))
            self._set_volume(pct)

        vol_scale.config(command=_on_vol_change)

        # Seek bar
        time_frame = tk.Frame(right_frame, bg=self.colors['card_bg'])
        time_frame.pack(fill='x', padx=8, pady=4)

        time_left = tk.Label(time_frame, text='00:00', bg=self.colors['card_bg'], fg=self.colors['text'], width=5)
        time_left.pack(side='left')

        seek_var = tk.DoubleVar()
        seek_scale = ttk.Scale(time_frame, from_=0, to=1000, orient='horizontal', variable=seek_var)
        seek_scale.pack(side='left', fill='x', expand=True, padx=6)

        time_right = tk.Label(time_frame, text='00:00', bg=self.colors['card_bg'], fg=self.colors['text'], width=5)
        time_right.pack(side='left')

        seek_dragging = [False]

        def _on_seek_press(e):
            seek_dragging[0] = True

        def _on_seek_release(e):
            if seek_dragging[0]:
                seek_dragging[0] = False
                pct = seek_var.get() / 1000.0
                self._seek_to_pct(pct)

        seek_scale.bind('<ButtonPress-1>', _on_seek_press)
        seek_scale.bind('<ButtonRelease-1>', _on_seek_release)

        def _update_ui():
            """Update seek bar and time labels."""
            if seek_dragging[0]:
                w.after(200, _update_ui)
                return

            length_ms = self._get_current_length_ms()
            pos_ms = 0

            try:
                if self.pygame_available and pygame.mixer.music.get_busy():
                    pos_ms = int(pygame.mixer.music.get_pos() or 0)
            except:
                pass

            if length_ms > 0:
                pct = (pos_ms / length_ms) * 1000
                seek_var.set(min(max(int(pct), 0), 1000))
                time_left.config(text=self._ms_to_str(pos_ms))
                time_right.config(text=self._ms_to_str(length_ms))

                # Auto-advance near end
                if pos_ms > 0 and (length_ms - pos_ms) < 500:
                    self._play_next()
                    track_lbl.config(text=os.path.basename(self.music_files[self.music_index]))
                    _refresh_lists()

            w.after(200, _update_ui)

        _update_ui()

    def _ms_to_str(self, ms):
        """Convert milliseconds to 'MM:SS' format."""
        if not ms or ms <= 0:
            return '00:00'
        s = int(ms // 1000)
        m, s = divmod(s, 60)
        return f'{m:02}:{s:02}'

    def _get_current_length_ms(self):
        """Get current track length in milliseconds using mutagen."""
        try:
            if not self.music_files:
                return 0
            path = self.music_files[self.music_index]
            audio = MutagenFile(path)
            if audio and getattr(audio, 'info', None):
                return int(audio.info.length * 1000)
        except Exception:
            pass
        return 0

    def _get_volume_percent(self):
        """Get current volume as percentage."""
        try:
            if self.pygame_available:
                return int(self.pygame.mixer.music.get_volume() * 100)
        except Exception:
            pass
        return int(self._volume * 100)

    def _set_volume(self, percent):
        """Set volume by percentage (0-100)."""
        p = max(0, min(100, int(percent)))
        self._volume = p / 100.0
        try:
            if self.pygame_available:
                pygame.mixer.music.set_volume(self._volume)  # Fixed: Use pygame directly, not self.pygame
            self.status_bar.config(text=f'Громкость: {p}%')
            
            # Update volume in player window if open
            if hasattr(self, '_player_vol_scale') and self._player_vol_scale.get() != p:
                self._player_vol_scale.set(p)
            if hasattr(self, '_player_vol_pct'):
                self._player_vol_pct.config(text=f"{p}%")
                
        except Exception as e:
            print(f'Volume error: {e}')

    def _seek_to_pct(self, pct):
        """Seek to position (0-1 percentage of track)."""
        if not self.pygame_available or not self.music_files:
            return

        try:
            length_ms = self._get_current_length_ms()
            if length_ms <= 0:
                return

            pos_sec = (pct * length_ms) / 1000.0

            try:
                # Stop current playback
                pygame.mixer.music.stop()
                # Load and seek
                pygame.mixer.music.load(self.music_files[self.music_index])
                pygame.mixer.music.play(loops=0, start=pos_sec)
                
                # Restore state
                pygame.mixer.music.set_volume(self._volume)
                if self._is_paused:
                    pygame.mixer.music.pause()

                self.status_bar.config(text=f'Перемотка: {self._ms_to_str(int(pct * length_ms))}')
            except Exception as e:
                print(f'Seek error: {e}')
        except Exception as e:
            print(f'Error in _seek_to_pct: {e}')

    def clear_frame(self, frame):
        for w in frame.winfo_children(): w.destroy()

    def add_item(self, container, text, url, color, is_youtube=False, youtube_id=None):
        row = tk.Frame(container, bg=self.colors['card_bg'])
        row.pack(fill='x', pady=6, padx=6)
        if is_youtube:
            vid = youtube_id or extract_youtube_id(url)
            
            normalized_url = normalize_youtube_url(url)
            thumb_label = tk.Label(row, text='Загрузка превью...', bg=self.colors['card_bg'], fg=self.colors['date'])
            thumb_label.pack(side='left', padx=(4,8))
                                                        
            def load_thumb():
                try:
                    if not vid:
                        raise ValueError('ID отсутствует')
                    thumb_url = f'https://img.youtube.com/vi/{vid}/hqdefault.jpg'
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
            play = tk.Button(row, text='▶', bg=self.colors['accent'], fg='#111', command=lambda: self.open_in_app_viewer(normalized_url, text, is_youtube=True))
            play.pack(side='right', padx=8)
            lbl.bind('<Button-1>', lambda e: self.open_in_app_viewer(normalized_url, text, is_youtube=True))
        else:
            lbl = tk.Label(row, text=text, font=('Arial', 11), fg=color, bg=self.colors['card_bg'], cursor='hand2', wraplength=740, justify='left')
            lbl.pack(fill='x', padx=6, pady=6)
            lbl.bind('<Button-1>', lambda e: self.open_in_app_viewer(url, text, is_youtube=False))

    def add_error(self, container, msg):
        tk.Label(container, text=f'⚠️ {msg}', fg='#ff6b6b', bg=self.colors['card_bg'], font=('Arial', 9)).pack(anchor='w', padx=8, pady=4)

if __name__ == '__main__':
    root = tk.Tk()
    app = HytaleApp(root)
    root.mainloop()
