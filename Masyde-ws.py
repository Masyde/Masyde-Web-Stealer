# Copyright © 2025 Masyde
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import re
import asyncio
import logging
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile
import cssbeautifier
import jsbeautifier
import cssmin
import jsmin
import httpx
from parsel import Selector
from tqdm import tqdm
import aiofiles
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
import esprima
from collections import Counter
import tkinter as tk
from tkinter import ttk, scrolledtext
from threading import Thread
import sys
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('masyde.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class WebsiteProcessor:
    def __init__(self, url, input_dir="downloaded_site", crawl_depth=2, retries=3, include=None, exclude=None, use_browser=False, log_callback=None, keep_processed=True):
        self.url = url
        self.root_domain = urlparse(url).netloc if url else ""
        self.input_dir = Path(input_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.src_dir = self.input_dir / "src"
        self.output_dir = self.input_dir / "processed"
        self.crawl_depth = crawl_depth
        self.retries = retries
        self.include = include
        self.exclude = exclude
        self.use_browser = use_browser and async_playwright is not None
        self.visited_urls = set()
        self.redirects = {}
        self.sitemap = []
        self.analysis = {
            "keywords": [],
            "metadata": {},
            "hidden_elements": [],
            "inline_scripts": [],
            "api_endpoints": [],
            "frontend_frameworks": []
        }
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = None
        self.playwright = None
        self.log_callback = log_callback
        self.running = False
        self.keep_processed = keep_processed

    def log(self, message, level="info"):
        # Log messages with color coding
        if self.log_callback:
            color = {"info": "blue", "warning": "yellow", "error": "red"}.get(level, "green")
            self.log_callback(message, color)
        getattr(logger, level)(message)

    async def download_website(self):
        # Download website and assets
        self.running = True
        if not self.url:
            self.log("No URL provided.", "error")
            return False
        self.log(f"Starting download of {self.url}")
        try:
            self.client = httpx.AsyncClient(follow_redirects=False, timeout=30)
            if self.use_browser:
                try:
                    self.playwright = await async_playwright().start()
                except Exception as e:
                    self.log(f"Playwright failed: {e}. Falling back to HTTP.", "warning")
                    self.use_browser = False
            await self._crawl_page(self.url, depth=0)
            await self._save_sitemap()
            await self._save_analysis()
            await self._create_zip()
            self.log(f"Download complete. Files saved in '{self.input_dir}'")
            return True
        except Exception as e:
            self.log(f"Download failed: {e}", "error")
            return False
        finally:
            if self.client:
                await self.client.aclose()
            if self.playwright:
                await self.playwright.stop()
            self.running = False

    async def _crawl_page(self, url, depth):
        # Recursively crawl a page
        if not self.running or depth > self.crawl_depth or url in self.visited_urls:
            return
        if not self._filter_url(url):
            return
        self.visited_urls.add(url)
        self.sitemap.append(url)
        self.log(f"Crawling {url} (depth {depth})")

        final_url, content = await self._fetch_with_redirects(url)
        if not content:
            return

        try:
            selector = Selector(text=content)
            await self._save_file(final_url, content, content_type="text/html")
            self._analyze_content(selector, content, final_url)

            assets = []
            assets.extend(selector.xpath("//img/@src").getall())
            assets.extend(selector.xpath("//link[@rel='stylesheet']/@href").getall())
            assets.extend(selector.xpath("//script/@src").getall())
            links = selector.xpath("//a/@href").getall()

            tasks = []
            for asset_url in assets:
                absolute_url = urljoin(final_url, asset_url)
                tasks.append(self._download_asset(absolute_url))
            await asyncio.gather(*tasks, return_exceptions=True)

            for link in links:
                absolute_url = urljoin(final_url, link)
                parsed_url = urlparse(absolute_url)
                if parsed_url.netloc == self.root_domain:
                    await self._crawl_page(absolute_url, depth + 1)

        except Exception as e:
            self.log(f"Error processing {url}: {e}", "error")

    async def _fetch_with_redirects(self, url, attempt=1):
        # Fetch URL with redirect handling
        if not self.running:
            return url, None
        if attempt > self.retries:
            self.log(f"Max retries reached for {url}", "error")
            return url, None

        try:
            if self.use_browser:
                browser = await self.playwright.chromium.launch()
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                content = await page.content()
                await browser.close()
                return url, content

            response = await self.client.get(url)
            if response.status_code in (301, 302, 303, 307, 308):
                next_url = response.headers.get("location")
                if not next_url:
                    self.log(f"No redirect location for {url}", "warning")
                    return url, None
                absolute_next_url = urljoin(url, next_url)
                self.redirects[url] = absolute_next_url
                self.log(f"Redirect: {url} -> {absolute_next_url}")
                return await self._fetch_with_redirects(absolute_next_url, attempt)
            if response.status_code != 200:
                self.log(f"Failed to fetch {url}: {response.status_code}", "warning")
                return url, None
            return url, response.text
        except httpx.RequestError as e:
            self.log(f"Request error for {url}: {e}", "warning")
            await asyncio.sleep(2 ** attempt)
            return await self._fetch_with_redirects(url, attempt + 1)
        except Exception as e:
            self.log(f"Unexpected error for {url}: {e}", "error")
            if attempt < self.retries:
                await asyncio.sleep(2 ** attempt)
                return await self._fetch_with_redirects(url, attempt + 1)
            return url, None

    async def _download_asset(self, url):
        # Download an asset
        if not self.running:
            return
        if url in self.visited_urls or not self._filter_url(url):
            return
        self.visited_urls.add(url)

        for attempt in range(1, self.retries + 1):
            try:
                response = await self.client.get(url, follow_redirects=True)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "").lower()
                    is_binary = "text" not in content_type and "html" not in content_type
                    content = response.content if is_binary else response.text
                    await self._save_file(url, content, is_binary, content_type)
                    if "javascript" in content_type and not is_binary:
                        self._analyze_js(content, url)
                    break
                else:
                    self.log(f"Asset {url} failed: {response.status_code}", "warning")
            except httpx.RequestError as e:
                self.log(f"Asset {url} attempt {attempt} failed: {e}", "warning")
                if attempt < self.retries:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self.log(f"Unexpected error downloading {url}: {e}", "error")
                break

    def _filter_url(self, url):
        # Filter URLs by regex
        try:
            if self.include and not re.search(self.include, url):
                return False
            if self.exclude and re.search(self.exclude, url):
                return False
            return True
        except re.error as e:
            self.log(f"Invalid regex pattern: {e}", "error")
            return True

    async def _save_file(self, url, content, is_binary=False, content_type=""):
        # Save content to files
        try:
            parsed = urlparse(url)
            path = parsed.path.lstrip("/")
            ext = Path(path).suffix.lower()
            if not path:
                path = "index.html"
                ext = ".html"
            elif ext not in (".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg"):
                path = path.rstrip("/") + "/index.html"
                ext = ".html"

            if content_type.startswith("text/html"):
                subdir = "html"
                ext = ".html"
            elif content_type.startswith("text/css"):
                subdir = "css"
                ext = ".css"
            elif content_type.startswith("application/javascript") or content_type.startswith("text/javascript"):
                subdir = "js"
                ext = ".js"
            elif content_type.startswith("image/"):
                subdir = "images"
                ext = {".png": ".png", ".jpg": ".jpg", ".jpeg": ".jpeg", ".gif": ".gif", ".svg": ".svg"}.get(ext, ".png")
            else:
                subdir = "other"
                ext = ext or ".bin"

            input_path = self.input_dir / parsed.netloc / subdir / path
            input_path.parent.mkdir(parents=True, exist_ok=True)

            src_path = self.src_dir / path
            src_path.parent.mkdir(parents=True, exist_ok=True)

            mode = "wb" if is_binary else "w"
            encoding = None if is_binary else "utf-8"
            content_to_save = content if is_binary else content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content

            if not is_binary and isinstance(content_to_save, str):
                content_to_save = self._rewrite_urls(content_to_save, url)

            async with aiofiles.open(input_path, mode, encoding=encoding) as f:
                await f.write(content_to_save)
            async with aiofiles.open(src_path, mode, encoding=encoding) as f:
                await f.write(content_to_save)
            self.log(f"Saved {url} to {input_path} and {src_path}")
        except Exception as e:
            self.log(f"Error saving {url}: {e}", "error")

    def _rewrite_urls(self, content, base_url):
        # Rewrite URLs for offline use
        try:
            def replace_url(match):
                url = match.group(1) or match.group(2)
                abs_url = urljoin(base_url, url)
                parsed = urlparse(abs_url)
                rel_path = parsed.path.lstrip("/") or "index.html"
                return match.group(0).replace(url, f"/{rel_path}")

            content = re.sub(r'(?:href|src)="([^"]*)"', replace_url, content)
            content = re.sub(r"(?:href|src)='([^']*)'", replace_url, content)
            return content
        except Exception as e:
            self.log(f"Error rewriting URLs: {e}", "error")
            return content

    def _analyze_content(self, selector, content, url):
        # Analyze page content
        try:
            meta = selector.xpath("//meta[@name or @property]").getall()
            for m in meta:
                name = selector.xpath(".//@name|.//@property").get()
                value = selector.xpath(".//@content").get()
                if name and value:
                    self.analysis["metadata"][name] = value

            text = selector.xpath("//text()").getall()
            words = " ".join(text).lower().split()
            common_words = Counter(words).most_common(20)
            self.analysis["keywords"].extend([w for w, _ in common_words if len(w) > 3])

            hidden = selector.xpath("//*[contains(@style, 'display:none') or contains(@style, 'visibility:hidden')]").getall()
            self.analysis["hidden_elements"].extend(hidden)

            scripts = selector.xpath("//script[not(@src)]/text()").getall()
            self.analysis["inline_scripts"].extend(scripts)

            if "react" in content.lower():
                self.analysis["frontend_frameworks"].append("React")
            if "vue" in content.lower():
                self.analysis["frontend_frameworks"].append("Vue")
            if "angular" in content.lower():
                self.analysis["frontend_frameworks"].append("Angular")
        except Exception as e:
            self.log(f"Content analysis error for {url}: {e}", "error")

    def _analyze_js(self, content, url):
        # Analyze JavaScript
        try:
            api_matches = re.findall(r'[\'"](https?://[^\'"]*/api/[^\'"]*)[\'"]', content)
            for api_url in api_matches:
                try:
                    response = httpx.get(api_url, timeout=10)
                    self.analysis["api_endpoints"].append({
                        "url": api_url,
                        "status": response.status_code,
                        "response": response.text[:200] if response.status_code == 200 else ""
                    })
                except Exception:
                    pass

            try:
                tree = esprima.parseScript(content)
                for node in tree.body:
                    if node.type == "VariableDeclaration":
                        for decl in node.declarations:
                            decl.id.name = f"var_{decl.id.name}"
                content = str(tree)
            except Exception:
                pass
        except Exception as e:
            self.log(f"JS analysis error for {url}: {e}", "error")

    async def _save_sitemap(self):
        # Save sitemap
        try:
            sitemap_path = self.input_dir / "sitemap.txt"
            async with aiofiles.open(sitemap_path, "w", encoding="utf-8") as f:
                for url in self.sitemap:
                    await f.write(f"{url}\n")
            self.log(f"Sitemap saved to {sitemap_path}")
        except Exception as e:
            self.log(f"Error saving sitemap: {e}", "error")

    async def _save_analysis(self):
        # Save analysis report
        try:
            analysis_path = self.input_dir / "analysis.json"
            async with aiofiles.open(analysis_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self.analysis, indent=2))
            self.log(f"Analysis saved to {analysis_path}")
        except Exception as e:
            self.log(f"Error saving analysis: {e}", "error")

    async def _create_zip(self):
        # Create ZIP archive
        try:
            zip_path = self.input_dir / "site_archive.zip"
            with ZipFile(zip_path, "w") as zipf:
                for folder in [self.src_dir, self.output_dir]:
                    for root, _, files in os.walk(folder):
                        for file in files:
                            file_path = Path(root) / file
                            arcname = file_path.relative_to(self.input_dir)
                            zipf.write(file_path, arcname)
            self.log(f"ZIP saved to {zip_path}")
        except Exception as e:
            self.log(f"Error creating ZIP: {e}", "error")

    def beautify_html(self, content):
        # Beautify HTML
        try:
            content = re.sub(r'>\s+<', '>\n<', content)
            content = re.sub(r'^\s+', '', content, flags=re.MULTILINE)
            return content
        except Exception as e:
            self.log(f"HTML beautification error: {e}", "error")
            return content

    def minify_html(self, content):
        # Minify HTML
        try:
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r'>\s+<', '><', content)
            return content.strip()
        except Exception as e:
            self.log(f"HTML minification error: {e}", "error")
            return content

    def deobfuscate_html(self, content):
        # Deobfuscate HTML
        return self.beautify_html(content)

    def beautify_css(self, content):
        # Beautify CSS
        try:
            return cssbeautifier.beautify(content)
        except Exception as e:
            self.log(f"CSS beautification error: {e}", "error")
            return content

    def minify_css(self, content):
        # Minify CSS
        try:
            return cssmin.cssmin(content)
        except Exception as e:
            self.log(f"CSS minification error: {e}", "error")
            return content

    def deobfuscate_css(self, content):
        # Deobfuscate CSS
        return self.beautify_css(content)

    def beautify_js(self, content):
        # Beautify JavaScript
        try:
            options = {
                'indent_size': 2,
                'space_in_paren': True,
                'unescape_strings': True
            }
            return jsbeautifier.beautify(content, options)
        except Exception as e:
            self.log(f"JS beautification error: {e}", "error")
            return content

    def minify_js(self, content):
        # Minify JavaScript
        try:
            return jsmin.jsmin(content)
        except Exception as e:
            self.log(f"JS minification error: {e}", "error")
            return content

    def deobfuscate_js(self, content):
        # Deobfuscate JavaScript
        try:
            tree = esprima.parseScript(content)
            for node in tree.body:
                if node.type == "VariableDeclaration":
                    for decl in node.declarations:
                        decl.id.name = f"var_{decl.id.name}"
            return self.beautify_js(str(tree))
        except Exception as e:
            self.log(f"JS deobfuscation error: {e}", "error")
            return self.beautify_js(content)

    def process_file(self, file_path):
        # Process a file
        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except UnicodeDecodeError:
            self.log(f"Skipping binary file: {file_path}", "warning")
            return
        except Exception as e:
            self.log(f"Error reading {file_path}: {e}", "error")
            return

        try:
            if ext == '.html':
                beautified = self.beautify_html(content)
                minified = self.minify_html(content)
                deobfuscated = self.deobfuscate_html(content)
            elif ext == '.css':
                beautified = self.beautify_css(content)
                minified = self.minify_css(content)
                deobfuscated = self.deobfuscate_css(content)
            elif ext == '.js':
                beautified = self.beautify_js(content)
                minified = self.minify_js(content)
                deobfuscated = self.deobfuscate_js(content)
            else:
                self.log(f"Unsupported file type: {ext}", "warning")
                return

            output_base = self.output_dir / file_path.relative_to(self.input_dir).with_suffix('')
            output_base.parent.mkdir(parents=True, exist_ok=True)

            for suffix, data in [
                ('.beautified' + ext, beautified),
                ('.minified' + ext, minified),
                ('.deobfuscated' + ext, deobfuscated)
            ]:
                with open(output_base.with_suffix(suffix), 'w', encoding='utf-8') as f:
                    f.write(data)
            self.log(f"Processed {file_path}: beautified, minified, deobfuscated")
        except Exception as e:
            self.log(f"Error processing {file_path}: {e}", "error")

    def process_directory(self):
        # Process directory files and handle processed folder
        try:
            files = []
            for root, _, filenames in os.walk(self.input_dir):
                for file in filenames:
                    if file.endswith(('.html', '.css', '.js')):
                        files.append(os.path.join(root, file))
            
            for file in tqdm(files, desc="Processing files", file=sys.stdout):
                self.process_file(file)

            if not self.keep_processed and self.output_dir.exists():
                shutil.rmtree(self.output_dir)
                self.log(f"Removed processed folder: {self.output_dir}", "info")
        except Exception as e:
            self.log(f"Error processing directory: {e}", "error")

    def stop(self):
        # Stop the crawler
        self.running = False
        self.log("Stopping crawler...", "warning")

class MasydeWebStealerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Masyde Web Stealer")
        self.root.geometry("900x700")
        self.root.overrideredirect(True)  # Remove default title bar
        self.processor = None
        self.dragging = False
        self.logo_path = self.load_logo()
        try:
            self.setup_gui()
            logger.info("GUI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GUI: {e}")
            raise

    def load_logo(self):
        # Load local logo
        try:
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            logo_jpeg = Path(base_path) / "masyde.jpeg"
            logo_ico = Path(base_path) / "masyde.ico"
            if logo_jpeg.exists():
                logger.info(f"Logo found: {logo_jpeg}")
                return logo_jpeg
            elif logo_ico.exists():
                logger.info(f"Logo found: {logo_ico}")
                return logo_ico
            logger.warning("Logo not found (masyde.jpeg or masyde.ico)")
            return None
        except Exception as e:
            logger.error(f"Error loading logo: {e}")
            return None

    def setup_gui(self):
        # Initialize GUI components
        logger.info("Setting up GUI components")
        self.main_frame = tk.Frame(self.root, bg="#2ecc71")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Custom title bar
        self.title_bar = tk.Frame(self.main_frame, bg="#34495e")
        self.title_bar.pack(fill=tk.X)

        # Logo
        if self.logo_path and Image and ImageTk:
            try:
                img = Image.open(self.logo_path).resize((40, 40), Image.Resampling.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(img)
                self.logo_label = tk.Label(self.title_bar, image=self.logo_image, bg="#34495e")
                self.logo_label.pack(side=tk.LEFT, padx=5)
                logger.info("Logo loaded in GUI")
            except Exception as e:
                logger.error(f"Failed to load logo in GUI: {e}")

        # Title
        tk.Label(self.title_bar, text="Masyde Web Stealer", font=("Arial", 16, "bold"), fg="white", bg="#34495e").pack(side=tk.LEFT)

        # Title bar buttons
        self.close_button = tk.Label(self.title_bar, text="✖", font=("Arial", 12), fg="white", bg="#34495e", cursor="hand2")
        self.close_button.pack(side=tk.RIGHT, padx=5)
        self.close_button.bind("<Button-1>", lambda e: self.root.destroy())

        self.minimize_button = tk.Label(self.title_bar, text="─", font=("Arial", 12), fg="white", bg="#34495e", cursor="hand2")
        self.minimize_button.pack(side=tk.RIGHT, padx=5)
        self.minimize_button.bind("<Button-1>", lambda e: self.root.iconify())

        # Dragging functionality
        self.title_bar.bind("<ButtonPress-1>", self.start_drag)
        self.title_bar.bind("<ButtonRelease-1>", self.stop_drag)
        self.title_bar.bind("<B1-Motion>", self.on_drag)

        # Input frame
        input_frame = tk.Frame(self.main_frame, bg="#2ecc71", bd=10)
        input_frame.pack(pady=20, padx=20, fill=tk.X)

        # URL
        tk.Label(input_frame, text="Website URL:", font=("Arial", 12), fg="white", bg="#2ecc71").grid(row=0, column=0, sticky="w", pady=5)
        self.url_entry = tk.Entry(input_frame, width=50, font=("Arial", 12), bd=0, bg="#ecf0f1", relief="flat")
        self.url_entry.insert(0, "https://example.com")
        self.url_entry.grid(row=0, column=1, pady=5, padx=10)

        # Directory
        tk.Label(input_frame, text="Save Directory:", font=("Arial", 12), fg="white", bg="#2ecc71").grid(row=1, column=0, sticky="w", pady=5)
        self.dir_entry = tk.Entry(input_frame, width=50, font=("Arial", 12), bd=0, bg="#ecf0f1", relief="flat")
        self.dir_entry.insert(0, "downloaded_site")
        self.dir_entry.grid(row=1, column=1, pady=5, padx=10)

        # Depth
        tk.Label(input_frame, text="Crawl Depth:", font=("Arial", 12), fg="white", bg="#2ecc71").grid(row=2, column=0, sticky="w", pady=5)
        self.depth_scale = tk.Scale(input_frame, from_=0, to=10, orient=tk.HORIZONTAL, bg="#2ecc71", fg="white", bd=0, highlightthickness=0)
        self.depth_scale.set(2)
        self.depth_scale.grid(row=2, column=1, pady=5, padx=10, sticky="w")

        # Retries
        tk.Label(input_frame, text="Retries:", font=("Arial", 12), fg="white", bg="#2ecc71").grid(row=3, column=0, sticky="w", pady=5)
        self.retries_scale = tk.Scale(input_frame, from_=1, to=5, orient=tk.HORIZONTAL, bg="#2ecc71", fg="white", bd=0, highlightthickness=0)
        self.retries_scale.set(3)
        self.retries_scale.grid(row=3, column=1, pady=5, padx=10, sticky="w")

        # Keep Processed Checkbox
        self.keep_processed_var = tk.BooleanVar(value=True)
        tk.Checkbutton(input_frame, text="Keep Processed Folder", variable=self.keep_processed_var, font=("Arial", 12), fg="white", bg="#2ecc71", selectcolor="#2ecc71").grid(row=4, column=0, columnspan=2, pady=5, sticky="w")

        # Buttons
        button_frame = tk.Frame(self.main_frame, bg="#2ecc71")
        button_frame.pack(pady=10)

        self.start_button = tk.Button(button_frame, text="Start", command=self.start_download, bg="#3498db", fg="white", font=("Arial", 12, "bold"), bd=0, relief="flat", width=10)
        self.start_button.pack(side=tk.LEFT, padx=5)
        self.start_button.bind("<Enter>", lambda e: self.start_button.config(bg="#2980b9"))
        self.start_button.bind("<Leave>", lambda e: self.start_button.config(bg="#3498db"))

        self.stop_button = tk.Button(button_frame, text="Stop", command=self.stop_download, bg="#e74c3c", fg="white", font=("Arial", 12, "bold"), bd=0, relief="flat", width=10)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        self.stop_button.bind("<Enter>", lambda e: self.stop_button.config(bg="#c0392b"))
        self.stop_button.bind("<Leave>", lambda e: self.stop_button.config(bg="#e74c3c"))

        # Log window
        self.log_text = scrolledtext.ScrolledText(self.main_frame, height=20, font=("Arial", 10), bg="#ecf0f1", fg="black", bd=0, relief="flat")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Responsive layout
        self.main_frame.bind("<Configure>", self.on_resize)
        logger.info("GUI setup complete")

    def start_drag(self, event):
        self.dragging = True
        self.drag_start_x = event.x_root - self.root.winfo_x()
        self.drag_start_y = event.y_root - self.root.winfo_y()

    def stop_drag(self, event):
        self.dragging = False

    def on_drag(self, event):
        if self.dragging:
            x = event.x_root - self.drag_start_x
            y = event.y_root - self.drag_start_y
            self.root.geometry(f"+{x}+{y}")

    def on_resize(self, event):
        # Handle window resize
        try:
            self.main_frame.update_idletasks()
            self.log_text.config(width=self.main_frame.winfo_width() // 10)
        except Exception as e:
            logger.error(f"Resize error: {e}")

    def log_message(self, message, color):
        # Log messages with fade-in animation
        try:
            color_map = {"blue": "blue", "red": "red", "yellow": "orange", "green": "green"}
            self.log_text.tag_configure(color, foreground=color_map.get(color, "black"))
            self.log_text.insert(tk.END, f"{message}\n", color)
            self.log_text.see(tk.END)
            self.log_text.update()
            self.log_text.after(50, lambda: self.log_text.tag_configure(color, foreground=color_map.get(color, "black")))
        except Exception as e:
            logger.error(f"Log message error: {e}")

    def start_download(self):
        # Start download process
        try:
            if self.processor and self.processor.running:
                self.log_message("Download already in progress.", "red")
                return
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.log_text.delete(1.0, tk.END)

            url = self.url_entry.get().strip()
            if not url:
                self.log_message("Please provide a URL.", "red")
                self.start_button.config(state="normal")
                return

            Thread(target=self.run_async_download, daemon=True).start()
        except Exception as e:
            logger.error(f"Start download error: {e}")
            self.log_message(f"Error starting download: {e}", "red")

    def run_async_download(self):
        # Run async download
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.processor = WebsiteProcessor(
                url=self.url_entry.get().strip(),
                input_dir=self.dir_entry.get().strip(),
                crawl_depth=self.depth_scale.get(),
                retries=self.retries_scale.get(),
                include=None,
                exclude=None,
                use_browser=False,
                log_callback=self.log_message,
                keep_processed=self.keep_processed_var.get()
            )
            loop.run_until_complete(self.processor.download_website())
            self.processor.process_directory()
            self.log_message(f"Download complete. Output saved to '{self.processor.input_dir}'.", "green")
        except Exception as e:
            logger.error(f"Async download error: {e}")
            self.log_message(f"Error during download: {e}", "red")
        finally:
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            loop.close()

    def stop_download(self):
        # Stop download process
        try:
            if self.processor:
                self.processor.stop()
                self.processor = None
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.log_message("Download stopped.", "yellow")
        except Exception as e:
            logger.error(f"Stop download error: {e}")
            self.log_message(f"Error stopping download: {e}", "red")

def main():
    # Initialize Tkinter and run app
    try:
        logger.info("Starting Masyde Web Stealer")
        root = tk.Tk()
        logger.info("Tkinter root created")
        app = MasydeWebStealerGUI(root)
        logger.info("GUI instance created")
        root.mainloop()
        logger.info("Mainloop exited")
    except tk.TclError as e:
        logger.error(f"Tkinter initialization error: {e}")
        print(f"Failed to initialize GUI: {e}. Check display settings or Tkinter installation.")
    except Exception as e:
        logger.error(f"Application error: {e}")
        print(f"Application error: {e}")

if __name__ == "__main__":
    main()
