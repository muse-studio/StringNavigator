
from music21 import stream, note, articulations

# テスト用の楽譜
score = stream.Score()
part = stream.Part()
measure = stream.Measure(number=1)

# 音符を作成
n = note.Note("C5", quarterLength=1)

# 指番号を作成
fingering = articulations.Fingering("3")
fingering.placement = "above"

# 指番号の基準位置を指定
fingering.style.absoluteX = 30
fingering.style.absoluteY = 40

n.articulations.append(fingering)

measure.append(n)
part.append(measure)
score.append(part)

# MusicXMLを出力
score.write(
    "musicxml",
    fp="test_fingering_absolute.musicxml"
)

print("MusicXML出力完了")
