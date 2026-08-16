import base64
import glob
import io
import json
import os
import random
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image


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


class TlantRandomLine:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("line",)
    FUNCTION = "random_line"
    CATEGORY = "Tlant Toolkit/Text"

    def random_line(self, text):
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return ("",)
        return (secrets.choice(lines),)

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return float("NaN")


def normalize_base_url(server_url):
    url = (server_url or "").strip()
    if not url:
        raise ValueError("server_url cannot be empty")
    return url.rstrip("/")


def build_url(server_url, endpoint):
    endpoint = (endpoint or "/v1/chat/completions").strip()
    if not endpoint:
        endpoint = "/v1/chat/completions"
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return normalize_base_url(server_url) + endpoint


def parse_stop_sequences(stop):
    if not stop or not stop.strip():
        return None
    values = []
    for line in stop.splitlines():
        line = line.strip()
        if line:
            values.append(line)
    return values or None


def parse_extra_json(extra_json):
    if not extra_json or not extra_json.strip():
        return {}
    try:
        data = json.loads(extra_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extra_json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("extra_json must be a JSON object")
    return data


def tensor_images_to_data_urls(images, image_format, jpeg_quality, max_images):
    if images is None:
        return []

    fmt = "JPEG" if image_format == "jpeg" else "PNG"
    mime = "jpeg" if image_format == "jpeg" else "png"
    max_images = max(1, int(max_images))
    quality = max(1, min(100, int(jpeg_quality)))

    if hasattr(images, "detach"):
        array = images.detach().cpu().numpy()
    else:
        array = np.asarray(images)

    if array.ndim == 3:
        array = array[None, ...]
    if array.ndim != 4:
        raise ValueError(f"images must be an IMAGE tensor with 3 or 4 dims, got shape {array.shape}")

    data_urls = []
    for item in array[:max_images]:
        item = np.clip(item * 255.0, 0, 255).astype(np.uint8)
        if item.shape[-1] == 1:
            item = item[..., 0]
        image = Image.fromarray(item)
        if fmt == "JPEG" and image.mode != "RGB":
            image = image.convert("RGB")

        buffer = io.BytesIO()
        if fmt == "JPEG":
            image.save(buffer, format=fmt, quality=quality)
        else:
            image.save(buffer, format=fmt)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        data_urls.append(f"data:image/{mime};base64,{encoded}")

    return data_urls


def extract_message_text(response):
    choices = response.get("choices") if isinstance(response, dict) else None
    if not choices:
        return ""

    first = choices[0]
    message = first.get("message", {}) if isinstance(first, dict) else {}
    content = message.get("content", "")
    if (content is None or content == "") and isinstance(message, dict):
        content = message.get("reasoning_content", "")

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    parts.append(str(text))
            elif part is not None:
                parts.append(str(part))
        return "\n".join(parts)
    return "" if content is None else str(content)


def post_json(url, payload, timeout, api_key=""):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = (api_key or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to connect to {url}: {exc}") from exc

    elapsed_ms = int((time.time() - started) * 1000)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"HTTP {status} returned non-JSON response from {url}: {raw[:1000]}") from exc
    return data, status, elapsed_ms


class TlantLlamaServerChat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "server_url": ("STRING", {"default": "http://127.0.0.1:18080", "multiline": False}),
                "endpoint": ("STRING", {"default": "/v1/chat/completions", "multiline": False}),
                "model": ("STRING", {"default": "default", "multiline": False}),
                "system_prompt": ("STRING", {"default": "", "multiline": True}),
                "prompt": ("STRING", {"default": "请用中文描述这张图片。", "multiline": True}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 32768, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "top_k": ("INT", {"default": 40, "min": 0, "max": 1000, "step": 1}),
                "min_p": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "repeat_penalty": ("FLOAT", {"default": 1.05, "min": 0.0, "max": 3.0, "step": 0.01}),
                "presence_penalty": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "frequency_penalty": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": MAX_SEED, "step": 1}),
                "stop": ("STRING", {"default": "", "multiline": True}),
                "response_format": (["text", "json_object"], {"default": "text"}),
                "image_format": (["png", "jpeg"], {"default": "png"}),
                "jpeg_quality": ("INT", {"default": 92, "min": 1, "max": 100, "step": 1}),
                "max_images": ("INT", {"default": 1, "min": 1, "max": 64, "step": 1}),
                "timeout_seconds": ("FLOAT", {"default": 300.0, "min": 1.0, "max": 3600.0, "step": 1.0}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "extra_json": ("STRING", {"default": "", "multiline": True}),
                "unload_after": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "images": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "raw_json", "status")
    FUNCTION = "chat"
    CATEGORY = "Tlant Toolkit/LLM"

    def chat(
        self,
        server_url,
        endpoint,
        model,
        system_prompt,
        prompt,
        max_tokens,
        temperature,
        top_p,
        top_k,
        min_p,
        repeat_penalty,
        presence_penalty,
        frequency_penalty,
        seed,
        stop,
        response_format,
        image_format,
        jpeg_quality,
        max_images,
        timeout_seconds,
        api_key,
        extra_json,
        unload_after,
        images=None,
    ):
        data_urls = tensor_images_to_data_urls(images, image_format, jpeg_quality, max_images)

        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})

        if data_urls:
            content = [{"type": "text", "text": prompt}]
            for data_url in data_urls:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": (model or "default").strip() or "default",
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "top_p": float(top_p),
            "presence_penalty": float(presence_penalty),
            "frequency_penalty": float(frequency_penalty),
        }

        if int(top_k) > 0:
            payload["top_k"] = int(top_k)
        if float(min_p) > 0:
            payload["min_p"] = float(min_p)
        if float(repeat_penalty) > 0:
            payload["repeat_penalty"] = float(repeat_penalty)
        if int(seed) >= 0:
            payload["seed"] = int(seed)

        stop_sequences = parse_stop_sequences(stop)
        if stop_sequences:
            payload["stop"] = stop_sequences

        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        payload.update(parse_extra_json(extra_json))

        url = build_url(server_url, endpoint)
        response, http_status, elapsed_ms = post_json(url, payload, timeout_seconds, api_key)
        text = extract_message_text(response)
        raw_json = json.dumps(response, ensure_ascii=False, indent=2)

        status_parts = [
            f"HTTP {http_status}",
            f"{elapsed_ms} ms",
            f"images={len(data_urls)}",
        ]

        if unload_after:
            unload_url = build_url(server_url, "/models/unload")
            try:
                unload_payload = {"model": payload["model"]}
                unload_response, unload_status, unload_ms = post_json(
                    unload_url,
                    unload_payload,
                    timeout_seconds,
                    api_key,
                )
                status_parts.append(f"unload=HTTP {unload_status} ({unload_ms} ms)")
                status_parts.append("unload_response=" + json.dumps(unload_response, ensure_ascii=False))
            except Exception as exc:
                status_parts.append(f"unload_failed={exc}")

        return (text, raw_json, "; ".join(status_parts))

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return float("NaN")


NODE_CLASS_MAPPINGS = {
    "TlantLoadFileBatch": TlantLoadFileBatch,
    "TlantRandomLine": TlantRandomLine,
    "TlantLlamaServerChat": TlantLlamaServerChat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TlantLoadFileBatch": "Load File Batch (Tlant)",
    "TlantRandomLine": "Random Line (No Seed) (Tlant)",
    "TlantLlamaServerChat": "Llama Server Chat/Vision (Tlant)",
}
