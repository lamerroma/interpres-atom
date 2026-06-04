# xlsx_translate.py
# XLSX translation engine — ZIP/XML logic ported from DocuTranslate
# (github.com/QinHan/DocuTranslate, MPL-2.0), translation calls replaced with
# direct Ollama integration.
#
# Public API:
#   translate_xlsx(content, lang_to, translate_batch_fn, stop_event, chunk_size,
#                  insert_mode, separator)
#     -> bytes  (translated .xlsx)

import io
import logging
import re
import threading
import xml.etree.ElementTree as ET
import zipfile
from typing import Callable, Dict, List, Optional

log = logging.getLogger("xlsx_translate")

# Register namespaces to prevent ns0/ns1 prefixes that corrupt Excel files
_NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_NS_REL  = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_NS_XML  = 'http://www.w3.org/XML/1998/namespace'
_NS_XDR  = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
_NS_A    = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_NS_VML  = 'urn:schemas-microsoft-com:vml'
_NS_MC   = 'http://schemas.openxmlformats.org/markup-compatibility/2006'

ET.register_namespace('',      _NS_MAIN)
ET.register_namespace('r',     _NS_REL)
ET.register_namespace('mc',    _NS_MC)
ET.register_namespace('xdr',   _NS_XDR)
ET.register_namespace('a',     _NS_A)
ET.register_namespace('v',     _NS_VML)
ET.register_namespace('x14ac', "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac")
ET.register_namespace('x15',   "http://schemas.microsoft.com/office/spreadsheetml/2010/11/main")
ET.register_namespace('x15ac', "http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac")


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _tag_is(elem: ET.Element, tag_name: str) -> bool:
    return elem.tag.endswith(f"}}{tag_name}") or elem.tag == tag_name


def _find_child(parent: ET.Element, tag_name: str) -> Optional[ET.Element]:
    for child in parent:
        if _tag_is(child, tag_name):
            return child
    return None


def _get_child_text(parent: ET.Element, tag_name: str) -> Optional[str]:
    child = _find_child(parent, tag_name)
    return child.text if child is not None else None


def _sanitize(text: str) -> str:
    """Remove XML control characters not allowed in Excel."""
    if not text:
        return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _collect_texts(zf: zipfile.ZipFile) -> List[str]:
    """Return all unique non-empty translatable strings from the XLSX."""
    texts: set = set()

    # 1. Shared strings (most cell text lives here)
    if "xl/sharedStrings.xml" in zf.namelist():
        with zf.open("xl/sharedStrings.xml") as f:
            for _, elem in ET.iterparse(f, events=("end",)):
                if _tag_is(elem, "t"):
                    if elem.text and elem.text.strip():
                        texts.add(elem.text)
                    elem.clear()

    # 2. Inline strings in worksheets
    sheet_files = [n for n in zf.namelist()
                   if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    for sheet_file in sheet_files:
        with zf.open(sheet_file) as f:
            for _, elem in ET.iterparse(f, events=("end",)):
                if _tag_is(elem, "c") and elem.get('t') == 'inlineStr':
                    is_node = _find_child(elem, "is")
                    if is_node is not None:
                        t_text = _get_child_text(is_node, "t")
                        if t_text and t_text.strip():
                            texts.add(t_text)
                    elem.clear()
                elif _tag_is(elem, "row"):
                    elem.clear()

    # 3. Table column names
    for item in zf.infolist():
        if item.filename.startswith("xl/tables/table"):
            with zf.open(item.filename) as f:
                root = ET.fromstring(f.read())
                for col in root.iter():
                    if _tag_is(col, "tableColumn") and col.get('name'):
                        texts.add(col.get('name'))

        # 4. Drawing text (text boxes / SmartArt in drawings)
        elif (item.filename.startswith("xl/drawings/drawing")
              and item.filename.endswith(".xml")):
            with zf.open(item.filename) as f:
                for _, elem in ET.iterparse(f, events=("end",)):
                    if _tag_is(elem, "t") and elem.text and elem.text.strip():
                        texts.add(elem.text)
                    elem.clear()

    return list(texts)


# ---------------------------------------------------------------------------
# ZIP rebuild with translations
# ---------------------------------------------------------------------------

def _rebuild_zip(original_content: bytes, translation_map: Dict[str, str],
                 insert_mode: str, separator: str) -> bytes:

    def apply_mode(original: str, translated: str) -> str:
        translated = _sanitize(translated)
        if insert_mode == "append":
            return f"{original}{separator}{translated}"
        elif insert_mode == "prepend":
            return f"{translated}{separator}{original}"
        return translated

    def preserve_space(elem: ET.Element, text: str):
        if '\n' in text or text.strip() != text:
            elem.set(f"{{{_NS_XML}}}space", "preserve")

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_content), 'r') as zf_in:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                content = zf_in.read(item.filename)
                filename = item.filename

                # Shared strings
                if filename == "xl/sharedStrings.xml":
                    root = ET.fromstring(content)
                    modified = False
                    for si in root.iter():
                        if not _tag_is(si, "si"):
                            continue
                        # Plain <t>
                        direct_t = _find_child(si, "t")
                        if direct_t is not None and direct_t.text in translation_map:
                            new_text = apply_mode(direct_t.text, translation_map[direct_t.text])
                            direct_t.text = new_text
                            preserve_space(direct_t, new_text)
                            p_pr = _find_child(si, "phoneticPr")
                            if p_pr is not None:
                                si.remove(p_pr)
                            modified = True
                        # Rich text <r>
                        for r in si.iter():
                            if not _tag_is(r, "r"):
                                continue
                            t_node = _find_child(r, "t")
                            if t_node is not None and t_node.text in translation_map:
                                new_text = apply_mode(t_node.text, translation_map[t_node.text])
                                t_node.text = new_text
                                preserve_space(t_node, new_text)
                                modified = True
                    zf_out.writestr(item,
                        ET.tostring(root, encoding='utf-8', xml_declaration=True)
                        if modified else content)

                # Worksheet inline strings
                elif filename.startswith("xl/worksheets/sheet") and filename.endswith(".xml"):
                    root = ET.fromstring(content)
                    modified = False
                    for cell in root.iter():
                        if not (_tag_is(cell, "c") and cell.get('t') == 'inlineStr'):
                            continue
                        is_node = _find_child(cell, "is")
                        if is_node is None:
                            continue
                        t_node = _find_child(is_node, "t")
                        if t_node is not None and t_node.text in translation_map:
                            new_text = apply_mode(t_node.text, translation_map[t_node.text])
                            t_node.text = new_text
                            preserve_space(t_node, new_text)
                            modified = True
                    zf_out.writestr(item,
                        ET.tostring(root, encoding='utf-8', xml_declaration=True)
                        if modified else content)

                # Table column names
                elif filename.startswith("xl/tables/table"):
                    root = ET.fromstring(content)
                    modified = False
                    for col in root.iter():
                        if _tag_is(col, "tableColumn"):
                            orig = col.get('name')
                            if orig in translation_map:
                                col.set('name', apply_mode(orig, translation_map[orig]))
                                modified = True
                    zf_out.writestr(item,
                        ET.tostring(root, encoding='utf-8', xml_declaration=True)
                        if modified else content)

                # Drawing text
                elif (filename.startswith("xl/drawings/drawing")
                      and filename.endswith(".xml")):
                    root = ET.fromstring(content)
                    modified = False
                    for elem in root.iter():
                        if _tag_is(elem, "p"):
                            for child in list(elem):
                                if _tag_is(child, "r"):
                                    t_node = _find_child(child, "t")
                                    if t_node is not None and t_node.text in translation_map:
                                        new_text = apply_mode(t_node.text,
                                                              translation_map[t_node.text])
                                        t_node.text = new_text
                                        preserve_space(t_node, new_text)
                                        modified = True
                    zf_out.writestr(item,
                        ET.tostring(root, encoding='utf-8', xml_declaration=True)
                        if modified else content)

                else:
                    zf_out.writestr(item, content)

    return output.getvalue()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def translate_xlsx(content: bytes,
                   lang_to: str,
                   translate_batch_fn: Callable,
                   stop_event: threading.Event,
                   chunk_size: int = 3000,
                   insert_mode: str = "replace",
                   separator: str = "\n") -> bytes:
    """Translate an XLSX file, preserving structure.

    Args:
        content: raw .xlsx bytes
        lang_to: target language name, e.g. "Ukrainian"
        translate_batch_fn: fn(batch: dict[str,str], lang_to: str, stop_event) -> dict[str,str]
        stop_event: set to abort mid-translation
        chunk_size: max characters per LLM request
        insert_mode: "replace" | "append" | "prepend"
        separator: string between original and translation in append/prepend mode

    Returns:
        Translated .xlsx bytes.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
            originals = _collect_texts(zf)
    except Exception as e:
        raise ValueError(f"Не вдалось відкрити XLSX: {e}") from e

    if not originals:
        log.info("No translatable text found in XLSX")
        return content

    translated: List[str] = [""] * len(originals)
    batch_ids: Dict[str, int] = {}
    current_batch: Dict[str, str] = {}
    current_chars = 0

    def flush_batch():
        if not current_batch or stop_event.is_set():
            return
        result = translate_batch_fn(current_batch, lang_to, stop_event)
        for k, v in result.items():
            idx = batch_ids.get(k)
            if idx is not None:
                translated[idx] = v or originals[idx]

    for i, text in enumerate(originals):
        if stop_event.is_set():
            break
        key = str(i)
        if current_chars + len(text) > chunk_size and current_batch:
            flush_batch()
            batch_ids.clear()
            current_batch.clear()
            current_chars = 0
        current_batch[key] = text
        batch_ids[key] = i
        current_chars += len(text)

    flush_batch()

    for i, t in enumerate(translated):
        if not t:
            translated[i] = originals[i]

    translation_map = dict(zip(originals, translated))
    return _rebuild_zip(content, translation_map, insert_mode, separator)
