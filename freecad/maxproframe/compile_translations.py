"""
Utility script to compile Qt XML translation (.ts) files into binary (.qm) files.
"""

import os
import struct
import xml.etree.ElementTree as ET


def elf_hash(val_bytes):
    h = 0
    for b in val_bytes:
        h = (h << 4) + b
        g = h & 0xf0000000
        if g:
            h ^= g >> 24
        h &= ~g
    return h if h else 1


def build_qm_bytes(entries):
    """
    Builds binary QM file content from list of (context, source, translation).
    """
    magic = bytes([
        0x3c, 0xb8, 0x64, 0x18, 0xca, 0xef, 0x9c, 0x95,
        0xcd, 0x21, 0x1c, 0xbf, 0x60, 0xa1, 0xbd, 0xdd
    ])

    messages = bytearray()
    hash_pairs = []

    for ctx, src, trans in entries:
        if not trans:
            continue
        offset = len(messages)
        src_bytes = src.encode("utf-8")
        ctx_bytes = ctx.encode("utf-8")
        trans_bytes = trans.encode("utf-16-be")

        # Tag_SourceText = 0x06
        messages.append(0x06)
        messages.extend(struct.pack(">I", len(src_bytes)))
        messages.extend(src_bytes)

        # Tag_Context = 0x07
        messages.append(0x07)
        messages.extend(struct.pack(">I", len(ctx_bytes)))
        messages.extend(ctx_bytes)

        # Tag_Translation = 0x03
        messages.append(0x03)
        messages.extend(struct.pack(">I", len(trans_bytes)))
        messages.extend(trans_bytes)

        # Tag_End = 0x01
        messages.append(0x01)

        h = elf_hash(src_bytes)
        hash_pairs.append((h, offset))

    hash_pairs.sort(key=lambda x: x[0])

    hashes_block = bytearray()
    for h, off in hash_pairs:
        hashes_block.extend(struct.pack(">II", h, off))

    qm = bytearray(magic)
    qm.append(0x42)  # Tag_Hashes
    qm.extend(struct.pack(">I", len(hashes_block)))
    qm.extend(hashes_block)

    qm.append(0x69)  # Tag_Messages
    qm.extend(struct.pack(">I", len(messages)))
    qm.extend(messages)

    return bytes(qm)


def compile_ts(ts_path, qm_path=None):
    """Compiles a .ts file into a .qm file."""
    if not qm_path:
        qm_path = os.path.splitext(ts_path)[0] + ".qm"

    tree = ET.parse(ts_path)
    root = tree.getroot()

    entries = []
    for ctx_elem in root.findall("context"):
        ctx_name_elem = ctx_elem.find("name")
        ctx_name = ctx_name_elem.text if ctx_name_elem is not None else ""

        for msg_elem in ctx_elem.findall("message"):
            src_elem = msg_elem.find("source")
            trans_elem = msg_elem.find("translation")

            if src_elem is not None and trans_elem is not None:
                src_text = src_elem.text or ""
                trans_text = trans_elem.text or ""
                if src_text and trans_text and trans_elem.get("type") != "unfinished":
                    entries.append((ctx_name, src_text, trans_text))

    qm_data = build_qm_bytes(entries)
    os.makedirs(os.path.dirname(os.path.abspath(qm_path)), exist_ok=True)
    with open(qm_path, "wb") as f:
        f.write(qm_data)

    return qm_path


def compile_all_translations(translations_dir):
    """Finds all .ts files in translations_dir and compiles them to .qm, including FreeCAD runtime aliases."""
    compiled = []
    if not os.path.isdir(translations_dir):
        return compiled

    # FreeCAD supportedLocales mappings and Qt aliases for recognized project Spanish catalogs:
    # FreeCAD maps 'Spanish' -> 'es-CO' and 'Spanish (Argentina)' -> 'es-AR'
    SPANISH_KNOWN_SOURCES = {"frameforge_es.ts", "maxproframe_es.ts"}
    SPANISH_LOCALES = ["es", "es-ES", "es-CO", "es-AR"]
    PROJECT_PREFIXES = ["frameforge", "FrameForge", "maxproframe", "MaxProFrame"]

    for fname in sorted(os.listdir(translations_dir)):
        if fname.endswith(".ts"):
            ts_path = os.path.join(translations_dir, fname)
            qm_path = compile_ts(ts_path)
            if qm_path not in compiled:
                compiled.append(qm_path)

            if fname in SPANISH_KNOWN_SOURCES:
                with open(qm_path, "rb") as f:
                    qm_bytes = f.read()
                for prefix in PROJECT_PREFIXES:
                    for loc in SPANISH_LOCALES:
                        alias_name = f"{prefix}_{loc}.qm"
                        alias_path = os.path.join(translations_dir, alias_name)
                        if alias_path != qm_path:
                            with open(alias_path, "wb") as f_out:
                                f_out.write(qm_bytes)
                            if alias_path not in compiled:
                                compiled.append(alias_path)

    return compiled


if __name__ == "__main__":
    import sys
    base_dir = os.path.dirname(__file__)
    trans_dir = os.path.join(base_dir, "resources", "translations")
    out = compile_all_translations(trans_dir)
    print(f"Compiled {len(out)} translation file(s): {out}")
