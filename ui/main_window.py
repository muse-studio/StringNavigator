import tkinter as tk
from tkinter import filedialog
from pathlib import Path


def show_main_window():
    root = tk.Tk()
    root.title("StringNavigator")
    root.geometry("700x600")

    selected_file = tk.StringVar(
        value="MusicXMLファイルが選択されていません"
    )

    def select_musicxml_file():
        file_path = filedialog.askopenfilename(
            title="MusicXMLファイルを選択してください",
            filetypes=[
                (
                    "MusicXML files",
                    "*.musicxml *.xml *.mxl"
                ),
                (
                    "Compressed MusicXML files",
                    "*.mxl"
                ),
                (
                    "All files",
                    "*.*"
                ),
            ]
        )

        if not file_path:
            return

        selected_file.set(str(Path(file_path)))

    title_label = tk.Label(
        root,
        text="StringNavigator",
        font=("Yu Gothic", 18, "bold")
    )
    title_label.pack(pady=20)

    file_frame = tk.LabelFrame(
        root,
        text="MusicXMLファイル",
        padx=15,
        pady=15
    )
    file_frame.pack(
        fill="x",
        padx=20,
        pady=10
    )

    file_label = tk.Label(
        file_frame,
        textvariable=selected_file,
        anchor="w",
        wraplength=500
    )
    file_label.pack(
        side="left",
        fill="x",
        expand=True
    )

    select_button = tk.Button(
        file_frame,
        text="ファイルを選択",
        command=select_musicxml_file
    )
    select_button.pack(
        side="right",
        padx=(10, 0)
    )

    root.mainloop()


if __name__ == "__main__":
    show_main_window()