
from pathlib import Path
import streamlit as st

# HTMLとJavaScriptの保存先
EDITOR_DIR = Path(__file__).parent / "editor"

HTML_PATH = EDITOR_DIR / "index.html"
JS_PATH = EDITOR_DIR / "editor.js"

# Streamlitのカスタムコンポーネントを定義
score_editor = st.components.v2.component(
    "stringnavigator.score_editor",
    html=HTML_PATH.read_text(encoding="utf-8"),
    js=JS_PATH.read_text(encoding="utf-8"),
    isolate_styles=False,
)
