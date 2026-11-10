
import json
import math

from music21 import converter

from algorithms.fixed_fingering import build_fixed_fingers_by_event

from fingering_1to4voices_cached_fixed import (
    build_timeline_events,
    timeline_to_events,
    estimate_fingering_segmented,
    build_source_state_map,
    annotate_score_with_source_states,
)

# 入力ファイル
input_path = "prototypes/score_editor/test.musicxml"
edits_path = "prototypes/score_editor/fingering_edits.json"
output_path = "prototypes/score_editor/test_refingering.musicxml"

# 1. 楽譜を読み込む
score = converter.parse(input_path)

# 2. 時間軸イベントを生成
timeline_events = build_timeline_events(score)
events, note_lengths = timeline_to_events(timeline_events, 120)

# 3. ユーザーの修正情報を読み込む
with open(edits_path, encoding="utf-8") as f:
    edits = json.load(f)

# 4. 固定条件を生成
fixed = build_fixed_fingers_by_event(timeline_events, edits)

# 5. 固定条件付きDPを実行
best_path = estimate_fingering_segmented(
    score,
    events,
    note_lengths,
    timeline_events,
    120,
    math.inf,
    fixed_fingers_by_event=fixed,
)

# 6. DP結果を元の音符に対応付ける
source_state_map = build_source_state_map(
    timeline_events,
    best_path,
)

# 7. 楽譜に指番号を書き込む
annotate_score_with_source_states(
    score,
    timeline_events,
    source_state_map,
)

# 8. MusicXMLとして保存
score.write("musicxml", fp=output_path)

print("出力完了:", output_path)
print(
    "固定指番号:",
    [
        (i, fixed[i], tuple(s.fn for s in best_path[i].states))
        for i in range(len(fixed))
        if fixed[i]
    ],
)
