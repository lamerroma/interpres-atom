@echo off
echo ============================================================
echo  Building Translate_word_to_Word.exe
echo ============================================================

pip install pyinstaller python-docx ollama customtkinter -q

pyinstaller --onefile --windowed --name "Translate_word_to_Word" Translate_word_to_Word.py

echo.
echo ============================================================
echo  Done! EXE is in: dist\Translate_word_to_Word.exe
echo ============================================================
pause
