
import math
from pathlib import Path

from music21 import converter

from fingering_1to4voices_cached_fixed import (
    build_timeline_events,
    timeline_to_events,
    estimate_fingering_segmented,
    build_source_state_map,
    annotate_score_with_source_states,
)

input_path = Path("prototypes/score_editor/SUZUKI-7-3.musicxml")
output_path = Path("prototypes/score_editor/SUZUKI-7-3_fingering.musicxml")

# 元の楽譜を読み込む
score = converter.parse(str(input_path))

# 二声を含む時間軸イベントを生成
timeline_events = build_timeline_events(score)
print(f"イベント数: {len(timeline_events)}")

# DP用イベントに変換
events, note_lengths = timeline_to_events(timeline_events, 120)

# 初回運指提案（固定指番号なし）
best_path = estimate_fingering_segmented(
    score,
    events,
    note_lengths,
    timeline_events,
    120,
    math.inf,
)

# 推定結果を元の音符に対応付ける
source_state_map = build_source_state_map(
    timeline_events,
    best_path,
)

# 指番号を書き込む
annotate_score_with_source_states(
    score,
    timeline_events,
    source_state_map,
)

# 別ファイルに保存
score.write("musicxml", fp=str(output_path))

print(f"出力完了: {output_path}")
