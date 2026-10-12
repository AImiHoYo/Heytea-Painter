"""
Reusable UI components.
"""

import customtkinter as ctk


def create_section(parent, title, font_family):
    frame = ctk.CTkFrame(parent, corner_radius=10)
    frame.pack(fill="x", pady=10)
    ctk.CTkLabel(frame, text=title, font=(font_family, 14, "bold")).pack(pady=10)
    return frame


def create_slider(parent, label, from_, to, default, font_family, on_change, is_updating_getter, resolution=None):
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(fill="x", pady=5)

    if resolution is None:
        if (to - from_) < 10 and isinstance(default, float):
            resolution = 0.01
        else:
            resolution = 1

    if resolution >= 1:
        fmt = "{:.0f}"
    elif resolution >= 0.1:
        fmt = "{:.1f}"
    else:
        fmt = "{:.2f}"

    label_frame = ctk.CTkFrame(frame, fg_color="transparent")
    label_frame.pack(fill="x")

    ctk.CTkLabel(label_frame, text=label, font=(font_family, 11)).pack(side="left")

    var = ctk.DoubleVar(value=default)
    value_label = ctk.CTkLabel(label_frame, text=fmt.format(default), font=(font_family, 11, "bold"), text_color="#3498db")
    value_label.pack(side="right")

    def update_label(*_):
        if not is_updating_getter():
            value_label.configure(text=fmt.format(var.get()))

    var.trace_add("write", update_label)

    slider = ctk.CTkSlider(frame, from_=from_, to=to, variable=var, command=lambda _: on_change())
    slider.pack(fill="x", pady=2)

    return var
