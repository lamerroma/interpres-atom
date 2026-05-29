@echo off
echo ============================================================
echo  Building Translate_word_to_Word.exe
echo ============================================================

pip install pyinstaller python-docx ollama customtkinter -q

pyinstaller --onefile --windowed --name "Translate_word_to_Word" Translate_word_to_Word.py

echo.
echo  Copying theme file...
copy theme_custom.json dist\theme_custom.json

echo.
echo ============================================================
echo  Done! Copy both files to the target PC:
echo    dist\Translate_word_to_Word.exe
echo    dist\theme_custom.json
echo ============================================================
pause
