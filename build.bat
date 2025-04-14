@echo off
pip install cx_Freeze js2xml
cls
cxfreeze --script=Masyde-ws.py --target-name=Masyde-ws.exe --include-files=masyde.jpeg --base-name=Win32GUI --packages=js2xml,esprima,httpx,parsel,cssbeautifier,jsbeautifier,cssmin,jsmin,tqdm,aiofiles,PIL --excludes=IPython,pandas,matplotlib,numpy,playwright,playwright.async_api --optimize=2 --copyright="© Masyde 2025" --icon=masyde.ico
@echo Check out build\exe.win-amd64-3.x\Masyde-ws.exe and test it out!
pause