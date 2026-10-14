"""从 icon.png 生成 Windows .ico 与 macOS .icns（白底抠成透明）。"""

import os
import shutil
import struct
import subprocess
import sys
from collections import deque
from io import BytesIO

from PIL import Image
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "icon.png")
OUT_PNG = os.path.join(HERE, "app_icon.png")
OUT_ICO = os.path.join(HERE, "icon.ico")
OUT_ICNS = os.path.join(HERE, "icon.icns")

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ICNS_SPECS = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def remove_white_background(image, threshold=248):
    arr = np.array(image.convert("RGBA"))
    height, width = arr.shape[:2]

    def is_bg(x, y):
        red, green, blue, _alpha = arr[y, x]
        return red >= threshold and green >= threshold and blue >= threshold

    seen = np.zeros((height, width), dtype=bool)
    queue = deque()
    for x in range(width):
        for y in (0, height - 1):
            if is_bg(x, y) and not seen[y, x]:
                seen[y, x] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if is_bg(x, y) and not seen[y, x]:
                seen[y, x] = True
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        if not is_bg(x, y):
            continue
        arr[y, x, 3] = 0
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and not seen[ny, nx]:
                seen[ny, nx] = True
                if is_bg(nx, ny):
                    queue.append((nx, ny))

    return Image.fromarray(arr)


def write_ico(path, images):
    """写入含多尺寸 PNG 帧的 ICO（Vista 及以后可用）。"""
    payloads = []
    for image in images:
        buf = BytesIO()
        image.save(buf, format="PNG")
        payloads.append(buf.getvalue())

    offset = 6 + 16 * len(payloads)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(payloads)))
        current = offset
        for image, payload in zip(images, payloads):
            width, height = image.size
            handle.write(struct.pack(
                "<BBBBHHII",
                0 if width >= 256 else width,
                0 if height >= 256 else height,
                0,
                0,
                1,
                32,
                len(payload),
                current,
            ))
            current += len(payload)
        for payload in payloads:
            handle.write(payload)


def main():
    if not os.path.isfile(SRC):
        raise SystemExit(f"缺少源图标: {SRC}")

    icon = remove_white_background(Image.open(SRC))
    preview = icon.copy()
    preview.thumbnail((512, 512), Image.Resampling.LANCZOS)
    preview.save(OUT_PNG, format="PNG")
    write_ico(OUT_ICO, [icon.resize(size, Image.Resampling.LANCZOS) for size in ICO_SIZES])
    print(f"wrote {OUT_PNG}")
    print(f"wrote {OUT_ICO}")

    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = os.path.join(HERE, "icon.iconset")
        if os.path.isdir(iconset):
            shutil.rmtree(iconset)
        os.makedirs(iconset)
        for name, size in ICNS_SPECS:
            icon.resize((size, size), Image.Resampling.LANCZOS).save(os.path.join(iconset, name))
        subprocess.check_call(["iconutil", "-c", "icns", "-o", OUT_ICNS, iconset])
        shutil.rmtree(iconset)
        print(f"wrote {OUT_ICNS}")
    else:
        icon.save(OUT_ICNS, format="ICNS")
        print(f"wrote {OUT_ICNS} (Pillow)")


if __name__ == "__main__":
    main()
