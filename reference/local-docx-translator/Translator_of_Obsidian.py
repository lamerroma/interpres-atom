import os
import re
from ollama import generate

def translate_obsidian_vault():
    # 1. Setup Input Parameters
    source_lang = input("Enter Source Language (e.g., English): ")
    source_code = input("Enter Source Code (e.g., EN): ")
    target_lang = input("Enter Target Language (e.g., Bulgarian): ")
    target_code = input("Enter Target Code (e.g., BG): ")
    vault_path = input("Enter the path to your Obsidian Vault: ")
    
    # Create a new folder for the translated vault so we don't overwrite originals
    output_vault = vault_path + "_translated"
    if not os.path.exists(output_vault):
        os.makedirs(output_vault)

    # 2. Walk through the vault recursively
    for root, dirs, files in os.walk(vault_path):
        # Mirror the directory structure in the output folder
        relative_path = os.path.relpath(root, vault_path)
        target_root = os.path.join(output_vault, relative_path)
        if not os.path.exists(target_root):
            os.makedirs(target_root)

        for filename in files:
            if filename.endswith(".md"):
                file_path = os.path.join(root, filename)
                print(f"Translating: {filename}...")

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 3. Handle Obsidian Frontmatter (YAML)
                # We usually want to skip translating the metadata keys
                parts = re.split(r'^---$', content, maxsplit=2, flags=re.MULTILINE)
                
                if len(parts) > 2:
                    frontmatter = parts[1]
                    body_text = parts[2]
                else:
                    frontmatter = None
                    body_text = content

                # 4. Construct the Prompt
                prompt = f"""You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator. 
                Your goal is to accurately convey the meaning while adhering to {target_lang} grammar.
                Maintain all Markdown formatting (like #, [[links]], and **bold**).
                Produce only the {target_lang} translation.

                Text to translate:
                {body_text}"""

                # 5. Run Inference
                response = generate(model='translategemma:4b', prompt=prompt)
                translated_body = response['response']

                # 6. Reassemble and Save
                new_file_path = os.path.join(target_root, filename)
                with open(new_file_path, 'w', encoding='utf-8') as f:
                    if frontmatter:
                        f.write(f"---{frontmatter}---\n")
                    f.write(translated_body)

    print(f"\nDone! Your translated vault is at: {output_vault}")

if __name__ == "__main__":
    translate_obsidian_vault()