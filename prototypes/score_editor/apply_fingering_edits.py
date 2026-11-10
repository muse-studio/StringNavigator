
import json
from pathlib import Path
from music21 import converter, articulations

# ファイルの場所
BASE_DIR = Path(__file__).resolve().parent

INPUT_XML = BASE_DIR / "test.musicxml"
EDIT_JSON = BASE_DIR / "fingering_edits.json"
OUTPUT_XML = BASE_DIR / "test_edited.musicxml"

# 楽譜と修正情報を読み込む
score = converter.parse(str(INPUT_XML))

with open(EDIT_JSON, "r", encoding="utf-8") as f:
    edits = json.load(f)

# 楽譜内の音符を取得
notes = list(score.flatten().notes)

for edit in edits:
    offset = edit["offset"]
    midi = edit["midi"]
    finger = int(edit["fingering"])

    # 開始時刻と音高が一致する音符を探す
    matches = [
        n for n in notes
        if abs(float(n.offset) - offset) < 1e-6
        and midi in [p.midi for p in n.pitches]
    ]

    if len(matches) != 1:
        print(f"対象を一意に特定できません: offset={offset}, midi={midi}, 件数={len(matches)}")
        continue

    note = matches[0]

    # 既存の指番号を削除
    note.articulations = [
        a for a in note.articulations
        if not isinstance(a, articulations.Fingering)
    ]

    # 新しい指番号を設定
    note.articulations.append(articulations.Fingering(finger))

    print(f"修正完了: offset={offset}, midi={midi}, finger={finger}")

# 新しいMusicXMLを出力
score.write("musicxml", fp=str(OUTPUT_XML))

print(f"出力完了: {OUTPUT_XML}")
