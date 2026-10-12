"""
Layout layer for Heytea Painter modern UI.
"""

import customtkinter as ctk


def build_main_layout(root, font_family, zoom_in_cb, zoom_out_cb, reset_zoom_cb, wheel_cb):
    main_container = ctk.CTkFrame(root)
    main_container.pack(fill="both", expand=True, padx=10, pady=10)

    left_right_container = ctk.CTkFrame(main_container, fg_color="transparent")
    left_right_container.pack(fill="both", expand=True)

    control_panel = ctk.CTkScrollableFrame(left_right_container, width=400, corner_radius=10)
    control_panel.pack(side="left", fill="y", padx=(0, 10))

    right_container = ctk.CTkFrame(left_right_container, fg_color="transparent")
    right_container.pack(side="right", fill="both", expand=True)

    preview_frame = ctk.CTkFrame(right_container, corner_radius=10)
    preview_frame.pack(fill="both", expand=True, pady=(0, 10))

    preview_header = ctk.CTkFrame(preview_frame, height=50, corner_radius=0)
    preview_header.pack(fill="x", padx=0, pady=0)

    ctk.CTkLabel(preview_header, text="预览区域", font=(font_family, 16, "bold")).pack(side="left", padx=20, pady=10)

    zoom_frame = ctk.CTkFrame(preview_header, fg_color="transparent")
    zoom_frame.pack(side="right", padx=20)

    ctk.CTkButton(zoom_frame, text="放大", width=50, command=zoom_in_cb, font=(font_family, 11)).pack(side="left", padx=2)
    ctk.CTkButton(zoom_frame, text="缩小", width=50, command=zoom_out_cb, font=(font_family, 11)).pack(side="left", padx=2)
    ctk.CTkButton(zoom_frame, text="重置", width=50, command=reset_zoom_cb, font=(font_family, 11)).pack(side="left", padx=2)

    preview_canvas = ctk.CTkCanvas(preview_frame, bg="#1a1a1a", highlightthickness=0)
    preview_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    preview_canvas.bind("<MouseWheel>", wheel_cb)

    console_frame = ctk.CTkFrame(right_container, corner_radius=10)
    console_frame.pack(fill="x", pady=0)

    ctk.CTkLabel(console_frame, text="控制台输出", font=(font_family, 14, "bold")).pack(anchor="w", padx=15, pady=(10, 5))

    console_text = ctk.CTkTextbox(console_frame, height=150, font=(font_family, 10))
    console_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    console_text.configure(state="disabled")

    return {
        "control_panel": control_panel,
        "preview_canvas": preview_canvas,
        "console_text": console_text,
    }
