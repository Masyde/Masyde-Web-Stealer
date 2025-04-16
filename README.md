__We are sorry for any errors with the code yet, we will give the working version without errors in just few days!__

# Masyde Web Stealer

Masyde Web Stealer is a powerful, user-friendly tool to download and process entire websites for offline use or analysis. With a sleek GUI, customizable crawling options, and robust file processing, it grabs HTML, CSS, JavaScript, images, and more, then beautifies or minifies them for your needs. Built with Python, it’s open-source under the MIT License, ready for developers, researchers, or anyone curious about web scraping done right.

[**You can join discord here!**](https://discord.com/invite/T2NegRDG3Y)

## Features

- **Intuitive GUI**: Modern interface with draggable window, custom header, and animated buttons.
- **Flexible Crawling**: Set crawl depth (0-10) and retries (1-5) to control how deep and persistent the scraper goes.
- **Comprehensive Downloads**: Captures HTML, CSS, JS, images, and other assets, preserving site structure.
- **File Processing**: Beautifies, minifies, and deobfuscates HTML, CSS, and JS for clean or compact outputs.
- **Output Options**: Saves to organized folders, generates sitemaps, analysis reports, and ZIP archives.
- **Customizable**: Toggle “Keep Processed Folder” to retain or delete processed files.
- **Error Handling**: Gracefully manages 404s, redirects, and network issues with detailed logging.
- **Cross-Platform**: Runs as a Python script or standalone .exe on Windows.

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Install Dependencies
```python
pip install httpx parsel cssbeautifier jsbeautifier cssmin jsmin tqdm aiofiles esprima pillow
```
Optional (for browser-based crawling):
```python
pip install playwright
playwright install
```

### Download
Clone or download the repository to your local machine.

## Usage

1. **Run the Script**:
   - Navigate to the project directory.
   - Execute: python Masyde-ws.py
   - For Windows .exe, double-click Masyde-ws.exe (after building).

2. **Interface Overview**:
   - **Window**: 900x700, no default title bar, draggable header.
   - **Header**: Dark gray with logo (masyde.jpeg), title, close/minimize buttons.
   - **Inputs**:
     - **URL**: Enter the website to scrape (e.g., https://example.com).
     - **Save Directory**: Set output folder (default: downloaded_site).
     - **Crawl Depth**: Slider for crawling depth (default: 2).
     - **Retries**: Slider for retry attempts (default: 3).
     - **Keep Processed Folder**: Checkbox to retain processed files (default: checked).
   - **Buttons**:
     - **Start**: Begins download (blue, hover effect).
     - **Stop**: Halts crawling (red, hover effect).
   - **Logs**: Real-time updates (green for success, red for errors, blue for info, yellow for warnings).

3. **Output**:
   - Files saved to: downloaded_site/YYYYMMDD_HHMMSS/
   - Structure:
     - src/: Mirrored site files.
     - www.[domain]/: Categorized HTML, CSS, JS, images.
     - sitemap.txt: List of crawled URLs.
     - analysis.json: Metadata, keywords, and more.
     - site_archive.zip: Zipped site.
     - processed/: Beautified/minified files (if kept).

4. **Build .exe** (Optional):
   - Make sure you have python installed!
   - Run: build.bat
   - Find executable in: build/

## Configuration

- **Logo**: Place masyde.jpeg (or masyde.ico) in the project directory for GUI branding.
- **Logging**: Check masyde.log for detailed runtime info.
- **Processed Folder**: Uncheck “Keep Processed Folder” to delete processed files after run.

## How to use [example]

1. Launch the app.
2. Enter https://example.com in the URL field.
3. Set depth to 2, retries to 3.
4. Click Start.
5. Watch logs for progress.
6. Find files in downloaded_site/YYYYMMDD_HHMMSS/.

## Troubleshooting

- **GUI Doesn’t Load**: Ensure Python and Tkinter are installed. Check masyde.log.
- **404 Errors**: External assets may be unavailable; the app logs and skips them.
- **.exe Issues**: Rebuild with --log-level DEBUG and verify masyde.jpeg inclusion.
- **Dependencies**: Reinstall packages if errors occur.

## Contributing

Fork, modify, and submit pull requests. Report issues or suggest features via discord or the repository’s issue tracker. All contributions are welcome under the MIT License.

## License

MIT License

Copyright © 2025 Masyde

Permission is granted to use, copy, modify, and distribute this software, provided the above copyright notice and this permission notice are included in all copies.
