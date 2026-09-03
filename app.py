import streamlit as st
import tempfile
from pathlib import Path

from fingering import load_musicxml


st.set_page_config(
    page_title="StringNavigator",
    page_icon="🎻",
    layout="centered"
)


st.title("🎻 StringNavigator")

st.write(
    "MusicXML形式の楽譜から、"
    "ヴァイオリンの運指を提案します。"
)

uploaded_file = st.file_uploader(
    "MusicXMLファイルを選択してください",
    type=["musicxml", "xml", "mxl"]
)


if uploaded_file is not None:
    st.success(
        f"「{uploaded_file.name}」を選択しました。"
    )

st.subheader("演奏レベルを選択")


level = st.radio(
    "提案する運指の種類を選んでください",
    options=["初心者", "中級者"],
    index=0,
    horizontal=True
)


if level == "初心者":
    st.info(
        "弾きやすさを優先した運指を提案します。"
    )

elif level == "中級者":
    st.info(
        "表現の幅を考慮した運指を提案します。"
    )

st.divider()


execute_button = st.button(
    "運指を提案する",
    type="primary",
    use_container_width=True,
    disabled=uploaded_file is None
)


if execute_button:

    try:
        with st.spinner(
            "MusicXMLファイルを読み込んでいます..."
        ):

            with tempfile.TemporaryDirectory() as temp_dir:

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

                score, events, note_lengths = (
                    load_musicxml(input_path)
                )

        st.success(
            "MusicXMLファイルを読み込みました。"
        )

        st.write(
            f"読み込んだ音符数：{len(events)}"
        )

    except Exception as error:
        st.error(
            "MusicXMLファイルを読み込めませんでした。"
        )

        with st.expander("エラーの詳細"):
            st.exception(error)