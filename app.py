import re
import hashlib
import math
import tempfile
import time
from music21 import converter

from pathlib import Path

import streamlit as st

from fingering import (
    annotate_score_with_fingering,
    estimate_fingering_segmented,
    load_musicxml,
)


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

        return [
            image_path.read_bytes()
            for image_path in image_paths
        ]


# ==========================================
# ページの基本設定
# ==========================================

st.set_page_config(
    page_title="StringNavigator",
    page_icon="🎻",
    layout="wide"
)



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

    uploaded_file = st.file_uploader(
        "MusicXMLファイルを選択してください",
        type=["musicxml", "xml", "mxl"]
    )


    if uploaded_file is not None:
        st.success(
            f"「{uploaded_file.name}」を選択しました。"
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

            # 推定前の表示へ戻す
            st.session_state[
                "preview_mode"
            ] = "推定前"

            st.session_state[
                "preview_page"
            ] = 0


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
    # 3. 演奏レベルの設定
    # ------------------------------------------

    st.subheader("3. 演奏レベルを選択")


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

                    score, events, note_lengths = (
                        load_musicxml(input_path)
                    )

                    load_seconds = (
                        time.perf_counter()
                        - load_start
                    )


                    # ----------------------------------
                    # 運指推定時間
                    # ----------------------------------

                    estimate_start = time.perf_counter()

                    best_path = (
                        estimate_fingering_segmented(
                            score,
                            events,
                            note_lengths,
                            L,
                            long_note_threshold=(
                                long_note_threshold
                            )
                        )
                    )

                    estimate_seconds = (
                        time.perf_counter()
                        - estimate_start
                    )


                    # ----------------------------------
                    # 結果ファイルの作成時間
                    # ----------------------------------

                    output_start = time.perf_counter()

                    annotated_score = (
                        annotate_score_with_fingering(
                            score,
                            best_path,
                            mode_name
                        )
                    )

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

        musicxml_column, pdf_column = (
            st.columns(2)
        )


        with musicxml_column:

            st.download_button(
                label="MusicXMLをダウンロード",
                data=st.session_state[
                    "result_musicxml"
                ],
                file_name=st.session_state[
                    "result_download_name"
                ],
                mime="application/vnd.recordare.musicxml+xml",
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

                st.image(
                    preview_images[
                        current_page
                    ],
                    use_container_width=True
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