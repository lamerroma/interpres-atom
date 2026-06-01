## Local Docx Translator (Powered by TranslateGemma)

This repository contains a Python-based automation tool that allows you to translate Microsoft Word documents (`.docx`) locally on your machine. By leveraging **TranslateGemma** via **Ollama**, you can ensure your sensitive documents are never uploaded to the cloud, maintaining 100% privacy and data security.


*Developed for the "TranslateGemma: Free Local Model" tutorial on YouTube.

[![Watch the video](https://img.youtube.com/vi/cd6HZSFZExM/0.jpg)](https://www.youtube.com/watch?v=cd6HZSFZExM)

### ✨ Features

* **100% Local & Private:** No API keys required, no data leaves your computer.
* **Batch Processing:** Automatically translates all `.docx` files in a selected directory.
* **Format Preservation:** Iterates through paragraphs and tables to maintain document structure.
* **Smart Layout Protection:** Automatically adjusts font sizes if the translated text is significantly longer than the original to help prevent layout breaks.
* **GUI Folder Selection:** Uses a simple popup interface for selecting input and output folders.

### 🛠️ Prerequisites

Before running the script, ensure you have the following installed:

1.  **Ollama:** [Download and install Ollama](https://ollama.com/)
2.  **TranslateGemma:** Pull the model using the command:
    ```bash
    ollama pull translategemma:4b
    ```
3.  **Python 3.x**

### 🚀 Installation

1.  Clone this repository:
    ```bash
    git clone https://github.com/petkovplamen1989/local-docx-translator.git
    cd local-docx-translator
    ```
2.  Install the required Python libraries:
    ```bash
    pip install python-docx ollama
    ```

### 📋 Usage

1.  Run the script:
    ```bash
    python translator.py
    ```
2.  **Select Folders:** A window will prompt you to select the folder containing your source documents and then a folder where the translations should be saved.
3.  **Configure Language:** Enter your desired target language (e.g., "Spanish", "German", "French") in the terminal.
4.  **Wait for Completion:** The script will process each file and save it with a `TR_[Language]_` prefix.

### ⚙️ How it Works

The script uses `python-docx` to parse the document's XML structure. It sends each text "run" (a string of text with consistent formatting) to the **TranslateGemma:4b** model. 

To maintain the visual integrity of your document, the script compares the length of the translation to the original. If the translation is more than 30% longer, it attempts to decrease the font size by 1pt to keep the text within its original container.

---
