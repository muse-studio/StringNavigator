
from pathlib import Path
from music21 import (
    stream, note, chord, meter, clef,
    instrument, metadata, tempo, articulations
)

# 出力先
out = Path("prototypes/score_editor/test_chords.musicxml")
out.parent.mkdir(parents=True, exist_ok=True)

score = stream.Score()
score.metadata = metadata.Metadata()
score.metadata.title = "StringNavigator - Triple and Quadruple Stop Test"
score.metadata.composer = "Test score"

part = stream.Part(id="Violin")
part.insert(0, instrument.Violin())
part.insert(0, clef.TrebleClef())
part.insert(0, meter.TimeSignature("4/4"))
part.insert(0, tempo.MetronomeMark(number=80))

# MIDI番号と初期指番号
# 0 = 開放弦
measures = [
    [
        ("note", 69, 0),
        ("chord", [62, 69, 76], [0, 0, 0]),
        ("note", 71, 1),
        ("chord", [57, 62, 69, 76], [1, 0, 0, 0]),
    ],
    [
        ("note", 67, 3),
        ("chord", [55, 62, 71], [0, 0, 1]),
        ("note", 69, 0),
        ("chord", [55, 62, 69, 76], [0, 0, 0, 0]),
    ],
]

for number, events in enumerate(measures, 1):
    m = stream.Measure(number=number)

    for kind, pitches, fingers in events:

        if kind == "note":
            obj = note.Note(pitches)
            obj.articulations.append(
                articulations.Fingering(fingers)
            )

        
        else:
            obj = chord.Chord(pitches)

            # Chord本体に構成音の順番で指番号を登録
            for finger in fingers:
                obj.articulations.append(
                    articulations.Fingering(finger)
                )


        obj.quarterLength = 1
        m.append(obj)

    part.append(m)

score.insert(0, part)

score.write("musicxml", fp=str(out))
print(f"Created: {out}")



# MusicXMLに出力された指番号を確認
import xml.etree.ElementTree as ET

tree = ET.parse(out)
root = tree.getroot()

print("\n=== MusicXMLの指番号確認 ===")

for measure in root.findall(".//part/measure"):
    measure_number = measure.get("number")

    for xml_note in measure.findall("note"):
        pitch = xml_note.find("pitch")
        if pitch is None:
            continue

        step = pitch.findtext("step", "")
        octave = pitch.findtext("octave", "")
        alter = pitch.findtext("alter", "0")

        fingers = [
            element.text
            for element in xml_note.findall(
                ".//technical/fingering"
            )
        ]

        print(
            f"小節{measure_number}: "
            f"{step}{alter}/{octave} "
            f"指番号={fingers}"
        )
