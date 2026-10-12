"""
Minimal regression smoke checks for CI.
"""

import os
import tempfile

import cv2
import numpy as np

from modules.image_processor import process_image_canny, process_image_pencil
from modules.ui_state import normalize_preset


def make_sample_image(path: str):
    img = np.full((240, 320, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (40, 40), (280, 200), (0, 0, 0), 3)
    cv2.circle(img, (160, 120), 45, (0, 0, 0), 2)
    cv2.imwrite(path, img)


def run():
    presets = normalize_preset({"canny_blur": 4, "speed_multiplier": 99})
    assert presets["canny_blur"] % 2 == 1, "canny_blur should be normalized to odd"
    assert presets["speed_multiplier"] == 5.0, "speed_multiplier should be clamped"

    with tempfile.TemporaryDirectory() as d:
        img_path = os.path.join(d, "smoke.png")
        make_sample_image(img_path)

        preview1, contours1, _, _ = process_image_pencil(img_path, 60, 0.4, 0.05, 1.0, 0, 1)
        assert preview1 is not None and contours1 is not None, "Pencil mode failed"

        preview2, contours2, _, _ = process_image_canny(img_path, 3, 50, 150, 1.0, 0, 1)
        assert preview2 is not None and contours2 is not None, "Canny mode failed"

    print("Smoke checks passed.")


if __name__ == "__main__":
    run()
