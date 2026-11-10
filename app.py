import re
import hashlib
import base64
import math
import tempfile
import time
from io import BytesIO
from PIL import Image
from music21 import converter
from components.editor import score_editor
from algorithms.fixed_fingering import build_fixed_fingers_by_event

from pathlib import Path

import streamlit as st

from fingering_1to4voices_cached_fixed import (
    load_musicxml,
    build_timeline_events,
    timeline_to_events,
    estimate_fingering_segmented,
    build_source_state_map,
    annotate_score_with_source_states,
)

# ==========================================
# PC側のネイティブファイル選択用
# ==========================================

LAST_DIRECTORY_FILE = (
    Path(__file__).resolve().parent
    / ".stringnavigator_last_musicxml_dir.txt"
)


class LocalSelectedFile:
    """PCで選択したローカルファイルをUploadedFile風に扱う。"""

    def __init__(self, file_path):
        self.path = Path(file_path)
        self.name = self.path.name
        self._data = self.path.read_bytes()

    def getvalue(self):
        return self._data


def get_last_pc_directory():
    """前回PCで選択したフォルダを取得する。"""

    try:
        if LAST_DIRECTORY_FILE.exists():
            directory = Path(
                LAST_DIRECTORY_FILE.read_text(
                    encoding="utf-8"
                ).strip()
            )

            if directory.is_dir():
                return directory
    except Exception:
        pass

    return None


def save_last_pc_directory(file_path):
    """PCで最後に選択したフォルダを保存する。"""

    try:
        LAST_DIRECTORY_FILE.write_text(
            str(Path(file_path).parent),
            encoding="utf-8"
        )
    except Exception:
        pass


def open_pc_musicxml_dialog():
    """Windows PC上で通常のファイル選択画面を開く。"""

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    dialog_options = {
        "title": "MusicXMLファイルを選択",
        "filetypes": [
            (
                "MusicXMLファイル",
                "*.musicxml *.xml *.mxl"
            ),
            ("すべてのファイル", "*.*"),
        ],
    }

    last_directory = get_last_pc_directory()

    if last_directory is not None:
        dialog_options["initialdir"] = str(
            last_directory
        )

    try:
        selected_path = filedialog.askopenfilename(
            **dialog_options
        )
    finally:
        root.destroy()

    if not selected_path:
        return None

    selected_path = Path(selected_path)
    save_last_pc_directory(selected_path)

    return selected_path


@st.cache_data(
    show_spinner=False
)
def create_score_preview(
    file_data,
    file_suffix
):
    """MusicXMLを楽譜画像へ変換する"""

    with tempfile.TemporaryDirectory() as temp_dir:

        temp_path = Path(temp_dir)

        input_path = (
            temp_path
            / f"preview_input{file_suffix}"
        )

        input_path.write_bytes(file_data)

        preview_score = converter.parse(
            str(input_path)
        )

        requested_path = (
            temp_path
            / "score_preview.png"
        )

        written_path = preview_score.write(
            "musicxml.png",
            fp=str(requested_path)
        )

        all_image_paths = list(
            temp_path.glob("*.png")
        )


        def get_page_number(image_path):

            match = re.search(
                r"-(\d+)\.png$",
                image_path.name
            )

            if match:
                return int(
                    match.group(1)
                )

            return 0


        numbered_image_paths = [
            image_path
            for image_path in all_image_paths
            if re.search(
                r"-(\d+)\.png$",
                image_path.name
            )
        ]


        if numbered_image_paths:

            image_paths = sorted(
                numbered_image_paths,
                key=get_page_number
            )

        else:

            image_paths = sorted(
                all_image_paths
            )

        if not image_paths and written_path:
            written_path = Path(
                written_path
            )

            if written_path.exists():
                image_paths = [
                    written_path
                ]

        if not image_paths:
            raise FileNotFoundError(
                "楽譜画像を作成できませんでした。"
            )

        # ==========================================
        # iPad用にプレビュー画像を軽量化
        # ==========================================

        preview_images = []


        for image_path in image_paths:

            with Image.open(image_path) as image:

                image.thumbnail(
                    (1200, 1700),
                    Image.Resampling.LANCZOS
                )

                if image.mode != "RGB":

                    background = Image.new(
                        "RGB",
                        image.size,
                        "white"
                    )

                    if "A" in image.getbands():

                        background.paste(
                            image,
                            mask=image.getchannel("A")
                        )

                    else:

                        background.paste(image)

                    image = background


                image_buffer = BytesIO()

                image.save(
                    image_buffer,
                    format="JPEG",
                    quality=85,
                    optimize=True
                )

                preview_images.append(
                    image_buffer.getvalue()
                )


        return preview_images

# ==========================================
# ページの基本設定
# ==========================================

st.set_page_config(
    page_title="StringNavigator",
    page_icon="🎻",
    layout="wide"
)

# ==========================================
# 固定条件付き運指再提案の共通処理
# ==========================================

def run_refingering(
    uploaded_file,
    fixed_notes,
    L,
    long_note_threshold,
    selected_positions
):
    """
    指定した固定条件で運指を再計算し、
    MusicXMLとPDFを返す。
    """

    with tempfile.TemporaryDirectory() as temp_dir:

        input_suffix = Path(uploaded_file.name).suffix

        original_path = (
            Path(temp_dir) / f"original{input_suffix}"
        )

        original_path.write_bytes(
            uploaded_file.getvalue()
        )

        # 元の楽譜を読み込む
        original_score, _, _, original_bpm = load_musicxml(
            original_path
        )

        original_timeline = build_timeline_events(
            original_score
        )

        # 固定条件をDP用に変換
        fixed = build_fixed_fingers_by_event(
            original_timeline,
            fixed_notes
        )

        

        # 時間軸イベントを生成
        events, note_lengths = timeline_to_events(
            original_timeline,
            original_bpm
        )

        # 固定条件付きDP
        best_path = estimate_fingering_segmented(
            original_score,
            events,
            note_lengths,
            original_timeline,
            original_bpm,
            L,
            long_note_threshold=long_note_threshold,
            selected_positions=selected_positions,
            fixed_fingers_by_event=fixed,
        )

        # 推定結果を元の音符に対応付ける
        source_state_map = build_source_state_map(
            original_timeline,
            best_path
        )

        # 楽譜に指番号を書き込む
        annotate_score_with_source_states(
            original_score,
            original_timeline,
            source_state_map
        )

        # MusicXMLを出力
        output_path = (
            Path(temp_dir) / "refingering_result.musicxml"
        )

        original_score.write(
            "musicxml",
            fp=str(output_path)
        )

        updated_musicxml = output_path.read_bytes()

        # PDFを出力
        pdf_path = (
            Path(temp_dir) / "refingering_result.pdf"
        )

        original_score.write(
            "musicxml.pdf",
            fp=str(pdf_path)
        )

        updated_pdf = pdf_path.read_bytes()

    return updated_musicxml, updated_pdf


# ==========================================
# primaryボタンだけ赤色にする
# ==========================================

st.markdown(
    """
    <style>
    /* 通常のprimaryボタン */
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #ff4b4b !important;
        border-color: #ff4b4b !important;
        color: white !important;
    }

    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #e84343 !important;
        border-color: #e84343 !important;
        color: white !important;
    }

    /* ダウンロードボタン */
    div[data-testid="stDownloadButton"] button[kind="primary"] {
        background-color: #ff4b4b !important;
        border-color: #ff4b4b !important;
        color: white !important;
    }

    div[data-testid="stDownloadButton"] button[kind="primary"]:hover {
        background-color: #e84343 !important;
        border-color: #e84343 !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)



# ==========================================
# タイトル・説明
# ==========================================

st.title("🎻 StringNavigator")

st.write(
    "MusicXML形式の楽譜から、"
    "ヴァイオリンの運指を提案します。"
)

st.divider()


# ==========================================
# 左右の表示領域
# ==========================================

left_column, right_column = st.columns(
    [1, 1.5],
    gap="large"
)


# ==========================================
# 左側：操作欄
# ==========================================

with left_column:

    # ------------------------------------------
    # 1. MusicXMLファイルの選択
    # ------------------------------------------

    st.subheader("1. 楽譜を選択")

    st.caption(
        "現在は、単音と二重音を含む"
        "ヴァイオリン譜に対応しています。"
    )

    # ==========================================
    # PC・iPadでファイル選択方法を切り替える
    # ==========================================

    device_mode = st.radio(
        "利用する端末",
        options=["PC", "タブレット（iPad）"],
        horizontal=True,
        key="device_mode",
        help=(
            "PCではWindowsのファイル選択画面を使い、"
            "タブレットではブラウザからアップロードします。"
        )
    )

    uploaded_file = None
    allowed_suffixes = [
        ".musicxml",
        ".xml",
        ".mxl"
    ]


    # ------------------------------------------
    # PC：Windowsの通常のファイル選択画面
    # ------------------------------------------

    if device_mode == "PC":

        st.caption(
            "PC内の好きな場所からMusicXMLを選択できます。"
            "前回選択したフォルダを次回も最初に開きます。"
        )

        if st.button(
            "PCからMusicXMLファイルを選択",
            use_container_width=True,
            key="pc_file_select_button"
        ):

            try:
                selected_path = (
                    open_pc_musicxml_dialog()
                )

                if selected_path is not None:
                    st.session_state[
                        "pc_selected_musicxml_path"
                    ] = str(selected_path)

            except Exception as error:
                st.error(
                    "PCのファイル選択画面を"
                    "開けませんでした。"
                )

                with st.expander(
                    "ファイル選択エラーの詳細"
                ):
                    st.exception(error)

        saved_pc_path = st.session_state.get(
            "pc_selected_musicxml_path"
        )

        if saved_pc_path:
            saved_pc_path = Path(saved_pc_path)

            if saved_pc_path.exists():

                file_suffix = (
                    saved_pc_path.suffix.lower()
                )

                if file_suffix in allowed_suffixes:
                    uploaded_file = LocalSelectedFile(
                        saved_pc_path
                    )

                else:
                    st.error(
                        "MusicXML形式のファイルを"
                        "選択してください。"
                    )

                    st.caption(
                        "対応形式：.musicxml、.xml、.mxl"
                    )

            else:
                st.warning(
                    "前回選択したファイルが見つかりません。"
                    "もう一度選択してください。"
                )

                st.session_state.pop(
                    "pc_selected_musicxml_path",
                    None
                )


    # ------------------------------------------
    # タブレット：iPadの「ファイル」から選択
    # ------------------------------------------

    else:

        st.caption(
            "iPadの「ファイル」アプリ内にある"
            "MusicXMLを選択してください。"
        )

        uploaded_file = st.file_uploader(
            "MusicXMLファイルを選択してください",
            type=None,
            key="ipad_musicxml_uploader",
        )

    # ------------------------------------------
    # 修正指番号JSONのアップロード
    # ------------------------------------------

    fixed_fingering_json = st.file_uploader(
        "修正した指番号のJSONファイル（任意）",
        type=["json"],
        key="fixed_fingering_json_uploader",
        help="指番号を固定して運指を再提案する場合に指定してください。"
    )




    # ------------------------------------------
    # PC・iPad共通：選択後の処理
    # ------------------------------------------

    if uploaded_file is not None:

        file_suffix = Path(
            uploaded_file.name
        ).suffix.lower()

        if file_suffix not in allowed_suffixes:

            st.error(
                "MusicXML形式のファイルを"
                "選択してください。"
            )

            st.caption(
                "対応形式：.musicxml、.xml、.mxl"
            )

            uploaded_file = None

        else:

            st.success(
                f"「{uploaded_file.name}」を"
                "選択しました。"
            )

            input_file_data = (
                uploaded_file.getvalue()
            )

            input_file_id = hashlib.sha256(
                input_file_data
            ).hexdigest()


            # 別の楽譜を選択した場合
            if (
                st.session_state.get(
                    "input_file_id"
                )
                != input_file_id
            ):

                st.session_state[
                    "input_file_id"
                ] = input_file_id

                result_keys = [
                    "result_musicxml",
                    "result_download_name",
                    "result_pdf",
                    "result_pdf_download_name",
                    "result_event_count",
                    "result_path_count",
                    "result_load_seconds",
                    "result_estimate_seconds",
                    "result_output_seconds",
                    "result_total_seconds",
                    "result_level",
                ]

                for key in result_keys:
                    st.session_state.pop(
                        key,
                        None
                    )

                # 別の楽譜を選択した場合、固定条件を初期化
                st.session_state["fixed_notes"] = []
                st.session_state["edit_history"] = []

                # 推定前の表示へ戻す
                st.session_state[
                    "preview_mode"
                ] = "推定前"

                st.session_state[
                    "preview_page"
                ] = 0

                st.session_state.pop(
                    "preview_file_id",
                    None
                )


    # ------------------------------------------
    # 2. 出力ファイル名
    # ------------------------------------------

    st.subheader("2. 出力ファイル名")


    if uploaded_file is not None:

        default_output_name = Path(
            uploaded_file.name
        ).stem

        with st.container(border=True):

            st.markdown(
                "**ダウンロードするときの"
                "ファイル名を設定してください。**"
            )

            output_file_name = st.text_input(
                "出力ファイル名",
                value=default_output_name,
                help="拡張子を付けずに入力してください。",
                key=f"output_name_{uploaded_file.name}"
            )

            if output_file_name.strip():
                st.caption(
                    f"保存時の名前："
                    f"{output_file_name.strip()}.musicxml"
                )

            else:
                st.warning(
                    "出力ファイル名を入力してください。"
                )

    else:

        output_file_name = ""

        with st.container(border=True):

            st.text_input(
                "出力ファイル名",
                value="",
                placeholder=(
                    "楽譜を選択すると、"
                    "元のファイル名が表示されます"
                ),
                disabled=True
            )


    # ------------------------------------------
    # 3. 演奏者の設定
    # ------------------------------------------

    with st.expander("3. 演奏者の設定", expanded=False):

        # 演奏レベル
        st.markdown("**演奏レベル**")

        level = st.radio(
            "提案する運指の種類を選んでください",
            options=["初心者", "中級者"],
            index=0,
            horizontal=True
        )

        if level == "初心者":
            mode_name = "Beginner"
            L = math.inf

            st.info(
                "弾きやすさを優先した運指を提案します。"
            )

        else:
            mode_name = "Intermediate"
            L = 0.1

            st.info(
                "表現の幅を考慮した運指を提案します。"
            )

        st.divider()

        # 使用できるポジション
        st.markdown("**使用できるポジション**")

        # 使用できるポジション
        st.markdown("**使用できるポジション（複数選択可）**")

        selected_positions = []

        col1, col2 = st.columns(2)

        for position in range(1, 8):

            # 左右交互に配置
            column = col1 if position % 2 == 1 else col2

            with column:
                if st.checkbox(
                    f"第{position}ポジション",
                    value=(position == 1),
                    key=f"position_{position}"
                ):
                    selected_positions.append(position)

        # 第8ポジション以上
        if st.checkbox(
            "第8ポジション以上",
            value=False,
            key="position_8_plus"
        ):
            selected_positions.append(8)

        st.caption(
            "※ 現在は選択UIのみです。"
            "ポジション正弦波っ今後、運指推定に反映します。"
        )


    # ------------------------------------------
    # 4. 詳細設定
    # ------------------------------------------

    with st.expander("4. 詳細設定"):

        split_at_long_notes = st.checkbox(
            "長い音符で処理を区切る",
            value=True,
            help=(
                "長い音符の後で運指計算を区切ることで、"
                "前後のフレーズを分けて処理します。"
            )
        )

        if split_at_long_notes:

            long_note_threshold = st.number_input(
                "区切りとして扱う音符の長さ（秒）",
                min_value=0.1,
                max_value=10.0,
                value=1.0,
                step=0.1
            )

        else:

            long_note_threshold = None


    # ------------------------------------------
    # 5. 運指推定の実行
    # ------------------------------------------

    st.subheader("5. 運指を提案")

    execute_button = st.button(
        "運指を提案する",
        type="primary",
        use_container_width=True,
        disabled=(
            uploaded_file is None
            or not output_file_name.strip()
        )
    )


    # ==========================================
    # MusicXML読み込み・運指推定・結果作成
    # ==========================================

    if execute_button:

        try:

            with st.spinner(
                "運指を計算し、"
                "結果の楽譜を作成しています..."
            ):

                with tempfile.TemporaryDirectory() as temp_dir:

                    # ----------------------------------
                    # アップロードファイルを一時保存
                    # ----------------------------------

                    file_suffix = Path(
                        uploaded_file.name
                    ).suffix

                    input_path = (
                        Path(temp_dir)
                        / f"input{file_suffix}"
                    )

                    input_path.write_bytes(
                        uploaded_file.getvalue()
                    )


                    # ----------------------------------
                    # MusicXMLの読み込み時間
                    # ----------------------------------

                    load_start = time.perf_counter()

                    score, _, _, bpm = load_musicxml(input_path)

                    timeline_events = build_timeline_events(score)

                    events, note_lengths = timeline_to_events(
                        timeline_events,
                        bpm
                    )

                    load_seconds = (
                        time.perf_counter()
                        - load_start
                    )


                    # ----------------------------------
                    # 運指推定時間
                    # ----------------------------------

                    estimate_start = time.perf_counter()

                    best_path = estimate_fingering_segmented(
                        score,
                        events,
                        note_lengths,
                        timeline_events,
                        bpm,
                        L,
                        long_note_threshold=long_note_threshold,
                        selected_positions=selected_positions
                    )

                    estimate_seconds = (
                        time.perf_counter()
                        - estimate_start
                    )


                    # ----------------------------------
                    # 結果ファイルの作成時間
                    # ----------------------------------

                    output_start = time.perf_counter()

                    # 時間軸上の推定結果を元の音符に対応させる
                    source_state_map = build_source_state_map(
                        timeline_events,
                        best_path
                    )

                    # 楽譜に指番号を書き込む
                    annotate_score_with_source_states(
                        score,
                        timeline_events,
                        source_state_map
                    )

                    # 指番号を書き込んだ楽譜
                    annotated_score = score

                    output_path = (
                        Path(temp_dir)
                        / "fingering_result.musicxml"
                    )

                    annotated_score.write(
                        "musicxml",
                        fp=str(output_path)
                    )

                    # ----------------------------------
                    # PDFファイルを作成
                    # ----------------------------------

                    pdf_output_path = (
                        Path(temp_dir)
                        / "fingering_result.pdf"
                    )

                    annotated_score.write(
                        "musicxml.pdf",
                        fp=str(pdf_output_path)
                    )

                    pdf_result_data = (
                        pdf_output_path.read_bytes()
                    )



                    result_data = (
                        output_path.read_bytes()
                    )

                    output_seconds = (
                        time.perf_counter()
                        - output_start
                    )

                    total_seconds = (
                        load_seconds
                        + estimate_seconds
                        + output_seconds
                    )


                    # 推定結果を保持する
                    st.session_state[
                        "result_musicxml"
                    ] = result_data

                    st.session_state[
                        "result_download_name"
                    ] = (
                        f"{output_file_name.strip()}"
                        ".musicxml"
                    )

                    st.session_state[
                        "result_pdf"
                    ] = pdf_result_data

                    st.session_state[
                        "result_pdf_download_name"
                    ] = (
                        f"{output_file_name.strip()}"
                        ".pdf"
                    )


                    st.session_state[
                        "result_event_count"
                    ] = len(events)

                    st.session_state[
                        "result_path_count"
                    ] = len(best_path)

                    st.session_state[
                        "result_load_seconds"
                    ] = load_seconds

                    st.session_state[
                        "result_estimate_seconds"
                    ] = estimate_seconds

                    st.session_state[
                        "result_output_seconds"
                    ] = output_seconds

                    st.session_state[
                        "result_total_seconds"
                    ] = total_seconds

                    st.session_state[
                        "result_level"
                    ] = level


                    # 推定後のプレビューへ切り替える
                    st.session_state[
                        "preview_mode"
                    ] = "推定後"

                    st.session_state[
                        "preview_page"
                    ] = 0


           

        # ------------------------------------------
        # エラー表示
        # ------------------------------------------

        except Exception as error:

            st.error(
                "運指を推定できませんでした。"
            )

            with st.expander(
                "エラーの詳細"
            ):
                st.exception(error)


    # ==========================================
    # 保存済みの推定結果
    # ==========================================

    if (
        "result_musicxml"
        in st.session_state
    ):

        st.success(
            "運指推定が完了しました。"
        )

        st.write(
            f"演奏レベル："
            f"{st.session_state['result_level']}"
        )

        st.write(
            f"読み込んだ音符数："
            f"{st.session_state['result_event_count']}"
        )

        st.write(
            f"推定した運指数："
            f"{st.session_state['result_path_count']}"
        )


        # ----------------------------------
        # 処理時間
        # ----------------------------------

        with st.expander("処理時間"):

            st.write(
                f"楽譜の読み込み："
                f"{st.session_state['result_load_seconds']:.2f}秒"
            )

            st.write(
                f"運指の推定："
                f"{st.session_state['result_estimate_seconds']:.2f}秒"
            )

            st.write(
                f"結果ファイルの作成："
                f"{st.session_state['result_output_seconds']:.2f}秒"
            )

            st.write(
                f"合計："
                f"{st.session_state['result_total_seconds']:.2f}秒"
            )


        # ----------------------------------
        # ダウンロード・やり直し
        # ----------------------------------

        st.subheader(
            "6. 結果を保存"
        )

        # ----------------------------------
        # 端末ごとにダウンロード表示を変更
        # ----------------------------------

        if device_mode == "PC":

            musicxml_column, pdf_column = st.columns(2)

            with musicxml_column:

                st.download_button(
                    label="MusicXMLをダウンロード",
                    data=st.session_state[
                        "result_musicxml"
                    ],
                    file_name=st.session_state[
                        "result_download_name"
                    ],
                    mime="application/octet-stream",
                    type="primary",
                    use_container_width=True
                )

            with pdf_column:

                st.download_button(
                    label="PDFをダウンロード",
                    data=st.session_state[
                        "result_pdf"
                    ],
                    file_name=st.session_state[
                        "result_pdf_download_name"
                    ],
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )

        else:

            st.download_button(
                label="PDFをダウンロード",
                data=st.session_state[
                    "result_pdf"
                ],
                file_name=st.session_state[
                    "result_pdf_download_name"
                ],
                mime="application/octet-stream",
                type="primary",
                use_container_width=True
            )


        retry_button = st.button(
            "条件を変えてやり直す",
            use_container_width=True
        )


        st.caption(
            "保存先はブラウザの設定に従います。"
        )


        

        # ----------------------------------
        # やり直し処理
        # ----------------------------------

        if retry_button:

            result_keys = [
                "result_musicxml",
                "result_download_name",
                "result_pdf",
                "result_pdf_download_name",
                "result_event_count",
                "result_path_count",
                "result_load_seconds",
                "result_estimate_seconds",
                "result_output_seconds",
                "result_total_seconds",
                "result_level",
            ]

            for key in result_keys:
                st.session_state.pop(
                    key,
                    None
                )

            # やり直す場合、過去の固定条件を初期化
            st.session_state["fixed_notes"] = []

            st.session_state["preview_mode"] = "推定前"
            st.session_state["preview_page"] = 0

            st.session_state[
                "preview_mode"
            ] = "推定前"

            st.session_state[
                "preview_page"
            ] = 0

            st.session_state.pop(
                "preview_file_id",
                None
            )

            st.rerun()


# ==========================================
# 右側：楽譜プレビュー欄
# ==========================================

with right_column:

    st.subheader("楽譜プレビュー")

    with st.container(border=True):

        if uploaded_file is None:

            st.info(
                "MusicXMLファイルを選択すると、"
                "ここに楽譜を表示します。"
            )

        else:

            try:

                # ==================================
                # 表示する楽譜の選択
                # ==================================

                preview_options = [
                    "推定前"
                ]

                if (
                    "result_musicxml"
                    in st.session_state
                ):
                    preview_options.append(
                        "推定後"
                    )


                preview_mode = st.radio(
                    "表示する楽譜",
                    options=preview_options,
                    horizontal=True,
                    key="preview_mode"
                )


                # ==================================
                # 表示する楽譜データ
                # ==================================

                if preview_mode == "推定前":

                    file_data = (
                        uploaded_file.getvalue()
                    )

                    file_suffix = Path(
                        uploaded_file.name
                    ).suffix

                else:

                    file_data = (
                        st.session_state[
                            "result_musicxml"
                        ]
                    )

                    file_suffix = ".musicxml"


                # ==================================
                # 楽譜の識別
                # ==================================

                preview_start = (
                    time.perf_counter()
                )

                file_id = hashlib.sha256(
                    file_data
                ).hexdigest()


                # ==================================
                # 楽譜画像の作成
                # ==================================

                with st.spinner(
                    "楽譜を表示しています..."
                ):

                    preview_images = (
                        create_score_preview(
                            file_data,
                            file_suffix
                        )
                    )

                preview_seconds = (
                    time.perf_counter()
                    - preview_start
                )


                # ==================================
                # 表示楽譜が変わった場合
                # ==================================

                if (
                    st.session_state.get(
                        "preview_file_id"
                    )
                    != file_id
                ):

                    st.session_state[
                        "preview_file_id"
                    ] = file_id

                    st.session_state[
                        "preview_page"
                    ] = 0


                # ==================================
                # 現在のページ
                # ==================================

                page_count = len(
                    preview_images
                )

                current_page = (
                    st.session_state.get(
                        "preview_page",
                        0
                    )
                )

                current_page = max(
                    0,
                    min(
                        current_page,
                        page_count - 1
                    )
                )

                st.session_state[
                    "preview_page"
                ] = current_page


                # ==================================
                # ページ移動
                # ==================================

                (
                    previous_column,
                    page_column,
                    next_column
                ) = st.columns(
                    [1, 2, 1]
                )


                with previous_column:

                    previous_button = st.button(
                        "← 前へ",
                        disabled=(
                            current_page == 0
                        ),
                        use_container_width=True,
                        key="preview_previous"
                    )


                with page_column:

                    st.markdown(
                        (
                            "<p style='text-align:center;'>"
                            f"{current_page + 1} / "
                            f"{page_count} ページ"
                            "</p>"
                        ),
                        unsafe_allow_html=True
                    )


                with next_column:

                    next_button = st.button(
                        "次へ →",
                        disabled=(
                            current_page
                            == page_count - 1
                        ),
                        use_container_width=True,
                        key="preview_next"
                    )


                # ==================================
                # 前のページへ移動
                # ==================================

                if previous_button:

                    st.session_state[
                        "preview_page"
                    ] = (
                        current_page - 1
                    )

                    st.rerun()


                # ==================================
                # 次のページへ移動
                # ==================================

                if next_button:

                    st.session_state[
                        "preview_page"
                    ] = (
                        current_page + 1
                    )

                    st.rerun()


                # ==================================
                # 現在のページを表示
                # ==================================

                image_base64 = base64.b64encode(
                    preview_images[current_page]
                ).decode("utf-8")

                st.markdown(
                    f"""
                    <div style="width:100%; text-align:center;">
                        <img
                            src="data:image/jpeg;base64,{image_base64}"
                            style="
                                width:100%;
                                height:auto;
                                display:block;
                            "
                        >
                    </div>
                    """,
                    unsafe_allow_html=True
                )


                st.caption(
                    f"プレビュー表示："
                    f"{preview_seconds:.2f}秒"
                )


            except Exception as error:

                st.warning(
                    "楽譜のプレビューを"
                    "表示できませんでした。"
                )

                with st.expander(
                    "プレビューエラーの詳細"
                ):

                    st.exception(error)


# ==========================================
# 運指付き楽譜の編集
# ==========================================

# ==========================================
# 過去の修正指番号を保持
# ==========================================

if "fixed_notes" not in st.session_state:
    st.session_state["fixed_notes"] = []

# 指番号の修正履歴を保持
if "edit_history" not in st.session_state:
    st.session_state["edit_history"] = []

if "result_musicxml" in st.session_state:

    st.divider()

    st.subheader("運指付き楽譜の編集")

    st.caption(
        "運指推定後の楽譜を表示します。"
    )

    musicxml_data = st.session_state[
        "result_musicxml"
    ]

    if isinstance(musicxml_data, bytes):
        musicxml_text = musicxml_data.decode("utf-8")
    else:
        musicxml_text = musicxml_data

    editor_result = score_editor(
        data={"musicxml": musicxml_text},
        key="main_score_editor",
    )

    # JavaScriptから指番号の修正情報を取得
    if editor_result is not None:

        edited_notes = getattr(
            editor_result,
            "edited_notes",
            None
        )

        if edited_notes is not None:

            st.write("修正した指番号")
            st.json(edited_notes)


            # 元のMusicXMLから再提案用の楽譜を読み込む
            if uploaded_file is not None:

                with tempfile.TemporaryDirectory() as temp_dir:

                    input_suffix = Path(uploaded_file.name).suffix

                    original_path = (
                        Path(temp_dir) / f"original{input_suffix}"
                    )

                    original_path.write_bytes(
                        uploaded_file.getvalue()
                    )

                    original_score, _, _, original_bpm = load_musicxml(
                        original_path
                    )

                    original_timeline = build_timeline_events(
                        original_score
                    )

                    fixed = build_fixed_fingers_by_event(
                        original_timeline,
                        edited_notes
                    )

                    fixed_summary = [
                        (i, item)
                        for i, item in enumerate(fixed)
                        if item
                    ]

                    st.write("DP用の固定指番号")
                    st.write(fixed_summary)

                    st.write("BPM:", original_bpm)

                    # ==========================================
                    # 固定指番号による運指の再提案
                    # ==========================================

                    keep_previous = st.checkbox(
                        "過去の修正を維持する",
                        value=True,
                        key="keep_previous_fingering",
                        help=(
                            "ON：過去と今回の修正を固定します。"
                            "OFF：今回の修正だけを固定します。"
                        ),
                    )

                    if st.button(
                        "固定指番号で再提案",
                        key="main_refingering_button"
                    ):

                        try:
                            # 過去の修正を利用するか選択
                            if keep_previous:
                                merged_notes = [
                                    note.copy()
                                    for note in st.session_state["fixed_notes"]
                                ]
                            else:
                                merged_notes = []

                            # 今回の修正を追加・上書き
                            for new_note in edited_notes:

                                existing_index = next(
                                    (
                                        i
                                        for i, note in enumerate(merged_notes)
                                        if (
                                            note["partId"] == new_note["partId"]
                                            and note["voiceId"] == new_note["voiceId"]
                                            and note["measureNumber"] == new_note["measureNumber"]
                                            and note["offset"] == new_note["offset"]
                                            and note["midi"] == new_note["midi"]
                                        )
                                    ),
                                    None
                                )

                                if existing_index is not None:
                                    merged_notes[existing_index] = new_note.copy()
                                else:
                                    merged_notes.append(new_note.copy())

                            # 統合した修正情報をDP用固定条件に変換
                            fixed = build_fixed_fingers_by_event(
                                original_timeline,
                                merged_notes
                            )

                            with st.spinner("運指を再計算しています..."):

                                updated_musicxml, updated_pdf = run_refingering(
                                    uploaded_file=uploaded_file,
                                    fixed_notes=merged_notes,
                                    L=L,
                                    long_note_threshold=long_note_threshold,
                                    selected_positions=selected_positions
                                )
                            # 再提案が成功した場合のみ固定情報を保存
                            st.session_state["fixed_notes"] = merged_notes    

                            # 今回の修正を履歴に追加
                            from datetime import datetime
                            from zoneinfo import ZoneInfo

                            for note in edited_notes:
                                history_item = {
                                    "partId": note["partId"],
                                    "voiceId": note["voiceId"],
                                    "measureNumber": note["measureNumber"],
                                    "offset": note["offset"],
                                    "midi": note["midi"],
                                    "before_fingering": note.get("before_fingering"),
                                    "after_fingering": note["fingering"],
                                    "timestamp": datetime.now(
                                        ZoneInfo("Asia/Tokyo")
                                    ).isoformat(timespec="seconds"),
                                }

                                st.session_state["edit_history"].append(history_item)

                            # 再提案結果を保存
                            st.session_state[
                                "result_musicxml"
                            ] = updated_musicxml

                            # 再提案後のPDFも保存
                            st.session_state[
                            "result_pdf"
                            ] = updated_pdf

                            # プレビューのページを先頭に戻す
                            st.session_state["preview_page"] = 0

                            # 画面を更新
                            st.rerun()

                        except Exception as error:
                            st.error(
                                "固定指番号による再提案に失敗しました。"
                            )
                            st.exception(error)

# ==========================================
# 現在の固定指番号の一覧
# ==========================================

st.subheader("現在の固定指番号")

fixed_notes = st.session_state.get("fixed_notes", [])

st.write("固定されている音符数:", len(fixed_notes))

if fixed_notes:

    fixed_table = []

    for i, note in enumerate(fixed_notes):

        fixed_table.append({
            "番号": i + 1,
            "小節": note.get("measureNumber"),
            "声部": note.get("voiceId"),
            "MIDI": note.get("midi"),
            "固定指番号": note.get("fingering"),
        })

    st.dataframe(
        fixed_table,
        use_container_width=True,
        hide_index=True
    )

    # ==========================================
    # 固定指番号の個別解除
    # ==========================================

    st.markdown("**固定指番号の個別解除**")

    selected_fixed = st.selectbox(
        "解除する固定指番号を選択",
        options=list(range(len(fixed_notes))),
        format_func=lambda i: (
            f"小節{fixed_notes[i].get('measureNumber')} / "
            f"声部{fixed_notes[i].get('voiceId')} / "
            f"MIDI{fixed_notes[i].get('midi')} / "
            f"指番号{fixed_notes[i].get('fingering')}"
        ),
        key="selected_fixed_to_remove"
    )

    if st.button(
        "選択した固定条件を解除",
        key="remove_selected_fixed"
    ):
        st.session_state["fixed_notes"].pop(selected_fixed)
        st.rerun()

    # ==========================================
    # 残りの固定条件で運指を再提案
    # ==========================================

    st.markdown("**固定条件を反映した運指の再提案**")

    if st.button(
        "残りの固定条件で再提案",
        key="refingering_after_removal",
        disabled=(uploaded_file is None)
    ):
        try:
            remaining_notes = [
                note.copy()
                for note in st.session_state["fixed_notes"]
            ]

            with st.spinner("残りの固定条件で運指を再計算しています..."):
                updated_musicxml, updated_pdf = run_refingering(
                    uploaded_file=uploaded_file,
                    fixed_notes=remaining_notes,
                    L=L,
                    long_note_threshold=long_note_threshold,
                    selected_positions=selected_positions
                )

            st.session_state["result_musicxml"] = updated_musicxml
            st.session_state["result_pdf"] = updated_pdf
            st.session_state["preview_page"] = 0

            # 修正履歴は変更しない
            st.rerun()

        except Exception as error:
            st.error("残りの固定条件による再提案に失敗しました。")
            st.exception(error)

else:
    st.info("現在、固定されている指番号はありません。")

# ==========================================
# 固定条件が0件の場合の再提案
# ==========================================

if (
    not st.session_state["fixed_notes"]
    and "result_musicxml" in st.session_state
):
    if st.button(
        "固定条件なしで再提案",
        key="refingering_without_fixed",
        disabled=(uploaded_file is None)
    ):
        try:
            with st.spinner("固定条件なしで運指を再計算しています..."):
                updated_musicxml, updated_pdf = run_refingering(
                    uploaded_file=uploaded_file,
                    fixed_notes=[],
                    L=L,
                    long_note_threshold=long_note_threshold,
                    selected_positions=selected_positions
                )

            st.session_state["result_musicxml"] = updated_musicxml
            st.session_state["result_pdf"] = updated_pdf
            st.session_state["preview_page"] = 0

            # 修正履歴は保持する
            st.rerun()

        except Exception as error:
            st.error("固定条件なしの再提案に失敗しました。")
            st.exception(error)    

# ==========================================
# 修正履歴の表示
# ==========================================

st.subheader("指番号の修正履歴")

history = st.session_state["edit_history"]

st.write("保存された修正履歴数:", len(history))

if history:

    history_table = []

    for item in history:
        history_table.append({
            "修正日時": item.get("timestamp", ""),
            "小節": item.get("measureNumber", ""),
            "MIDI": item.get("midi", ""),
            "変更前": item.get("before_fingering"),
            "変更後": item.get(
                "after_fingering",
                item.get("fingering")
            ),
        })

    st.dataframe(
        history_table,
        use_container_width=True,
        hide_index=True
    )

    # ==========================================
    # 修正履歴の個別削除
    # ==========================================

    st.markdown("**修正履歴の個別削除**")

    history_options = list(range(len(history)))

    selected_history = st.selectbox(
        "削除する修正履歴を選択",
        options=history_options,
        format_func=lambda i: (
            f"履歴{i + 1}："
            f"小節{history[i].get('measureNumber', '?')} / "
            f"MIDI{history[i].get('midi', '?')} / "
            f"{history[i].get('before_fingering', '?')}"
            f" → "
            f"{history[i].get('after_fingering', '?')}"
        ),
        key="selected_history_to_delete"
    )

    if st.button(
        "選択した履歴を削除",
        key="delete_selected_history"
    ):
        st.session_state["edit_history"].pop(
            selected_history
        )

        st.success("選択した修正履歴を削除しました。")
        st.rerun()

    # ==========================================
    # 修正履歴の一括削除
    # ==========================================

    if "confirm_clear_history" not in st.session_state:
        st.session_state["confirm_clear_history"] = False

    if not st.session_state["confirm_clear_history"]:

        if st.button("修正履歴をすべて削除"):
            st.session_state["confirm_clear_history"] = True
            st.rerun()

    else:

        st.warning(
            "すべての修正履歴を削除します。"
            "この操作は取り消せません。"
        )

        delete_col, cancel_col = st.columns(2)

        with delete_col:
            if st.button("削除する", type="primary"):
                st.session_state["edit_history"] = []
                st.session_state["confirm_clear_history"] = False
                st.rerun()

        with cancel_col:
            if st.button("キャンセル"):
                st.session_state["confirm_clear_history"] = False
                st.rerun()



else:
    st.info("修正履歴はまだありません。")