import os
import fitz  # PyMuPDF
from fpdf import FPDF
from ollama import generate

def translate_pdf():
    # 1. Setup Input Parameters
    source_lang = input("Enter Source Language (e.g., English): ")
    source_code = input("Enter Source Code (e.g., EN): ")
    target_lang = input("Enter Target Language (e.g., Bulgarian): ")
    target_code = input("Enter Target Code (e.g., BG): ")
    folder_path = input("Enter the path to your PDF folder: ")
    
    # Create output directory
    output_dir = "translated_pdfs"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Path to a Unicode-compatible font (Windows path used here)
    # If on Linux, use: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_path = r"C:/Windows/Fonts/arial.ttf" 

    # 2. Process Files
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            print(f"\n--- Processing: {filename} ---")
            
            doc = fitz.open(os.path.join(folder_path, filename))
            
            # Initialize FPDF2
            pdf_out = FPDF()
            pdf_out.set_auto_page_break(auto=True, margin=15)
            
            # Add Unicode Font
            try:
                pdf_out.add_font("CustomFont", "", font_path)
                pdf_out.set_font("CustomFont", size=11)
            except:
                print("Warning: Arial.ttf not found. Falling back to Helvetica (Unicode may fail).")
                pdf_out.set_font("Helvetica", size=11)

            for page_num in range(len(doc)):
                print(f"  Translating page {page_num + 1}...")
                page = doc.load_page(page_num)
                text = page.get_text()
                
                if not text.strip():
                    continue

                # 3. Construct the Prompt (Your custom professional prompt)
                prompt = f"""You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator. 
Your goal is to accurately convey the meaning and nuances of the original {source_lang} text while adhering to {target_lang} grammar, vocabulary, and cultural sensitivities.
Produce only the {target_lang} translation, without any additional explanations or commentary. 

Please translate the following {source_lang} text into {target_lang}:
{text}"""

                # 4. Run Inference via Ollama
                response = generate(model='translategemma:4b', prompt=prompt)
                translated_text = response['response']

                # 5. Write to new PDF
                pdf_out.add_page()
                # Clean text of characters that even Unicode fonts might struggle with
                clean_text = translated_text.replace('\u200b', '').replace('\x00', '')
                pdf_out.multi_cell(0, 10, txt=clean_text)

            # Save the file
            output_name = os.path.join(output_dir, f"translated_{filename}")
            pdf_out.output(output_name)
            print(f"Success! Saved to: {output_name}")

if __name__ == "__main__":
    translate_pdf()