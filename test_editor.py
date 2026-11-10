import streamlit as st
from components.editor import score_editor
from music21 import converter
from fingering_1to4voices_cached_fixed import build_timeline_events
from algorithms.fixed_fingering import build_fixed_fingers_by_event
import math

from fingering_1to4voices_cached_fixed import (
    timeline_to_events,
    estimate_fingering_segmented,
    build_source_state_map,
    annotate_score_with_source_states,
)



st.title("楽譜編集テスト")

# 過去の修正情報を保持
if "fixed_notes" not in st.session_state:
    st.session_state.fixed_notes = []

# 過去の修正情報を固定条件として維持するか選択
keep_previous_fingering = st.checkbox(
    "過去に修正した指番号を維持する",
    value=True,
    help="チェックを外すと、今回修正した指番号のみを固定条件として再提案します。",
)

# 表示するMusicXMLを保持
if "display_musicxml" not in st.session_state:
    with open(
        "prototypes/score_editor/SUZUKI-7-3_fingering.musicxml",
        "r",
        encoding="utf-8"
    ) as f:
        st.session_state.display_musicxml = f.read()

xml = st.session_state.display_musicxml

# 楽譜編集コンポーネントを表示
result = score_editor(
    data={"musicxml": xml},
    key="test_score_editor",
)

st.success("コンポーネントを呼び出しました")

# JavaScriptから受信した修正情報を表示
st.subheader("Python側で受信した修正情報")

if result is not None:
    edited_notes = getattr(result, "edited_notes", None)

    if edited_notes is not None:
        st.json(edited_notes)
        score = converter.parse("prototypes/score_editor/SUZUKI-7-3_fingering.musicxml")
        timeline_events = build_timeline_events(score)

        try:
            fixed = build_fixed_fingers_by_event(
                timeline_events,
                edited_notes
            )

            fixed_summary = [
                (i, item)
                for i, item in enumerate(fixed)
                if item
            ]

            st.subheader("DP用の固定指番号")
            st.write(fixed_summary)

            if st.button("固定指番号で再提案"):

                # 過去の修正情報をコピー
                merged_notes = [
                    note.copy()
                    for note in st.session_state.fixed_notes
                ]

                # 今回の修正情報を統合
                for new_note in edited_notes:

                    existing_index = next(
                        (
                            i for i, note in enumerate(merged_notes)
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
                        # 同じ音符なら新しい指番号で上書き
                        merged_notes[existing_index] = new_note.copy()
                    else:
                        # 異なる音符なら追加
                        merged_notes.append(new_note.copy())

                # 統合した修正情報を保存
                st.session_state.fixed_notes = merged_notes

                # チェックボックスの状態に応じて固定条件を切り替える
                if keep_previous_fingering:
                    # 過去の修正と今回の修正を固定
                    notes_to_fix = merged_notes
                else:
                    # 今回の修正だけを固定
                    notes_to_fix = edited_notes

                # DP用の固定条件を生成
                fixed = build_fixed_fingers_by_event(
                    timeline_events,
                    notes_to_fix
                )

                with st.spinner("運指を再計算しています..."):

                    events, note_lengths = timeline_to_events(
                        timeline_events, 120
                    )

                    best_path = estimate_fingering_segmented(
                        score,
                        events,
                        note_lengths,
                        timeline_events,
                        120,
                        math.inf,
                        fixed_fingers_by_event=fixed,
                    )

                    source_state_map = build_source_state_map(
                        timeline_events,
                        best_path,
                    )

                    annotate_score_with_source_states(
                        score,
                        timeline_events,
                        source_state_map,
                    )

                    output_path = (
                        "prototypes/score_editor/"
                        "test_refingering_streamlit.musicxml"
                    )

                    score.write("musicxml", fp=output_path)
                    # 再提案したMusicXMLを表示用データに反映
                    with open(output_path, "r", encoding="utf-8") as f:
                        st.session_state.display_musicxml = f.read()

                    st.rerun()



                    st.success("固定指番号を反映した運指の再提案が完了しました")
                    st.write("出力ファイル:", output_path)

        except ValueError as e:
            st.error(f"固定指番号の変換に失敗しました: {e}")

    else:
        st.info("修正情報はまだありません")
else:
    st.info("コンポーネントからの応答待ち")

# 保存されている修正情報を確認
st.subheader("保存済みの修正情報")
st.json(st.session_state.fixed_notes)
