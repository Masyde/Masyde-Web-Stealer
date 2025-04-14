@echo off
cls
@echo.
pip install httpx parsel cssbeautifier jsbeautifier cssmin jsmin tqdm aiofiles esprima pillow
cls
python masyde-ws.py --url https://www.pswalloz.xyz --dir my_site --depth 3 --retries 5 --browser
pause
cls