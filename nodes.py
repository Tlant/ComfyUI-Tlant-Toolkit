import glob
import json
import os
import random
import re
import threading
from pathlib import Path


MAX_SEED = 0xFFFFFFFFFFFFFFFF
STATE_PATH = os.path.join(os.path.dirname(__file__), "tlant_toolkit_state.json")
STATE_LOCK = threading.Lock()


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state):
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, STATE_PATH)


def parse_extensions(extensions):
    if not extensions or not extensions.strip():
        return None

    parts = re.split(r"[\s,;，；]+", extensions.strip())
    normalized = []
    seen = set()
    for part in parts:
        ext = part.strip().lower()
        if not ext:
            continue
        ext = ext[1:] if ext.startswith(".") else ext
        if ext and ext not in seen:
            normalized.append(ext)
            seen.add(ext)
    return set(normalized) if normalized else None


def collect_files(folder_path, extensions, recursive):
    if not folder_path or not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Folder does not exist: {folder_path}")

    root = os.path.abspath(os.path.expanduser(folder_path))
    pattern = "**/*" if recursive else "*"
    candidates = glob.glob(os.path.join(glob.escape(root), pattern), recursive=recursive)
    files = []
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        ext = Path(candidate).suffix.lower().lstrip(".")
        if extensions is None or ext in extensions:
            files.append(os.path.abspath(candidate))

    files.sort(key=lambda value: value.lower())
    if not files:
        ext_text = "all files" if extensions is None else ", ".join(sorted(extensions))
        raise FileNotFoundError(f"No matching files found in {root} ({ext_text})")
    return files


def counter_key(label, folder_path, extensions, recursive):
    ext_key = "*" if extensions is None else ",".join(sorted(extensions))
    return json.dumps(
        {
            "label": label,
            "path": os.path.abspath(os.path.expanduser(folder_path)),
            "extensions": ext_key,
            "recursive": bool(recursive),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


class TlantLoadFileBatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["single_file", "incremental_file", "random"],),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_SEED,
                        "control_after_generate": True,
                    },
                ),
                "index": ("INT", {"default": 0, "min": 0, "max": 150000, "step": 1}),
                "label": ("STRING", {"default": "Batch 001", "multiline": False}),
                "path": ("STRING", {"default": "", "multiline": False}),
                "extensions": ("STRING", {"default": "", "multiline": False}),
                "recursive": ("BOOLEAN", {"default": False}),
                "filename_text_extension": (["true", "false"],),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = (
        "file_path",
        "filename_text",
        "filename_stem",
        "folder_path",
        "extension",
        "index",
        "count",
    )
    FUNCTION = "load_file"
    CATEGORY = "Tlant Toolkit/IO"

    def load_file(
        self,
        mode,
        seed,
        index,
        label,
        path,
        extensions,
        recursive,
        filename_text_extension="true",
    ):
        parsed_extensions = parse_extensions(extensions)
        files = collect_files(path, parsed_extensions, recursive)
        count = len(files)

        if mode == "single_file":
            if index < 0 or index >= count:
                raise IndexError(f"Invalid file index {index}; valid range is 0 to {count - 1}")
            selected_index = index
        elif mode == "incremental_file":
            key = counter_key(label, path, parsed_extensions, recursive)
            with STATE_LOCK:
                state = load_state()
                counters = state.setdefault("counters", {})
                selected_index = counters.get(key, 0)
                if selected_index >= count:
                    selected_index = 0
                counters[key] = (selected_index + 1) % count
                save_state(state)
        else:
            selected_index = random.Random(seed).randrange(count)

        file_path = files[selected_index]
        file_name = os.path.basename(file_path)
        filename_stem, extension = os.path.splitext(file_name)
        extension = extension.lstrip(".")
        filename_text = file_name if filename_text_extension == "true" else filename_stem
        folder_path = os.path.dirname(file_path)

        return (
            file_path,
            filename_text,
            filename_stem,
            folder_path,
            extension,
            selected_index,
            count,
        )

    @classmethod
    def IS_CHANGED(cls, mode, seed, index, label, path, extensions, recursive, filename_text_extension="true"):
        parsed_extensions = parse_extensions(extensions)
        if mode == "single_file":
            files = collect_files(path, parsed_extensions, recursive)
            selected = files[index]
            try:
                stat = os.stat(selected)
                return (selected, stat.st_mtime_ns, stat.st_size)
            except OSError:
                return selected
        return float("NaN")


NODE_CLASS_MAPPINGS = {
    "TlantLoadFileBatch": TlantLoadFileBatch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TlantLoadFileBatch": "Load File Batch (Tlant)",
}
