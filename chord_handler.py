# chord_handler.py

from pathlib import Path
from music21 import converter, note, chord, stream, articulations


def is_single_note(element):
    """単音かどうか判定"""
    return isinstance(element, note.Note)


def is_chord(element):
    """重音かどうか判定"""
    return isinstance(element, chord.Chord)


def add_fingering_to_note(note_obj, finger, placement="above"):
    """
    単音に指番号を付ける
    placement: "above" または "below"
    """
    fingering = articulations.Fingering(str(finger))
    fingering.placement = placement
    note_obj.articulations.append(fingering)


def get_default_chord_fingerings(note_count):
    """
    確認用の仮指番号を返す
    下の音 → 上の音 の順
    """

    if note_count == 2:
        return [1, 3]

    elif note_count == 3:
        return [1, 2, 4]

    elif note_count == 4:
        return [0, 1, 2, 4]

    else:
        return None


def add_vertical_fingering_to_chord(chord_obj, fingerings=None):
    """
    重音用：
    2重音〜4重音まで、指番号を縦に表示する

    fingerings は 下の音 → 上の音 の順で指定する

    例：
      2重音 [1, 3]
        表示：
        3
        1

      3重音 [1, 2, 4]
        表示：
        4
        2
        1

      4重音 [0, 1, 2, 4]
        表示：
        4
        2
        1
        0
    """

    notes = sorted(chord_obj.notes, key=lambda n: n.pitch.midi)
    note_count = len(notes)

    if note_count == 0:
        return

    if fingerings is None:
        fingerings = get_default_chord_fingerings(note_count)

    if fingerings is None:
        print(f"{note_count}重音は未対応です：{chord_obj}")
        return

    if len(fingerings) != note_count:
        raise ValueError(
            f"重音の音数({note_count})と指番号数({len(fingerings)})が一致しません"
        )

    # 表示は上の音から下の音へ並べる
    text = "\n".join(str(finger) for finger in reversed(fingerings))

    fingering = articulations.Fingering(text)
    fingering.placement = "above"

    chord_obj.articulations.append(fingering)

    print(f"{note_count}重音に指番号を付けました：")
    print(text)


def add_voice_fingering(note_obj, finger, voice_position):
    """
    2パート用：
    上パート → 音符の上
    下パート → 音符の下
    """

    if voice_position == "upper":
        add_fingering_to_note(
            note_obj,
            finger=finger,
            placement="above"
        )

    elif voice_position == "lower":
        add_fingering_to_note(
            note_obj,
            finger=finger,
            placement="below"
        )


def print_element_info(element, index):
    """
    確認用：単音・重音の情報を表示
    """

    if is_single_note(element):
        print(f"{index}音目：単音 {element.pitch.nameWithOctave}")

    elif is_chord(element):
        pitch_names = [p.nameWithOctave for p in element.pitches]
        print(f"{index}音目：重音 {pitch_names}")


def add_test_fingerings(score):
    """
    確認用：
    ・単純な重音には縦並びの指番号を付ける
    ・2パートの上パートには上、下パートには下に指番号を付ける
    ・通常の単音には確認用として上に2を付ける
    """

    note_index = 1

    for part in score.parts:
        for measure in part.getElementsByClass(stream.Measure):

            voices = measure.getElementsByClass(stream.Voice)

            # 2パート小節
            if len(voices) >= 2:
                print(f"\n小節 {measure.measureNumber}：2パートあり")

                for voice_index, voice in enumerate(voices):

                    if voice_index == 0:
                        voice_position = "upper"
                        test_finger = 3
                        print("  上パートとして処理します")

                    else:
                        voice_position = "lower"
                        test_finger = 1
                        print("  下パートとして処理します")

                    for element in voice.notes:
                        print_element_info(element, note_index)

                        if is_single_note(element):
                            add_voice_fingering(
                                element,
                                finger=test_finger,
                                voice_position=voice_position
                            )

                        elif is_chord(element):
                            add_vertical_fingering_to_chord(element)

                        note_index += 1

            # 通常小節
            else:
                print(f"\n小節 {measure.measureNumber}：通常小節")

                for element in measure.notes:
                    print_element_info(element, note_index)

                    if is_single_note(element):
                        add_fingering_to_note(
                            element,
                            finger=2,
                            placement="above"
                        )

                    elif is_chord(element):
                        add_vertical_fingering_to_chord(element)

                    note_index += 1


def main():
    xml_path = input("MusicXMLファイルのパスを入力してください：").strip().strip('"')

    if not xml_path:
        print("ファイルが指定されていません。")
        return

    xml_path = Path(xml_path)

    if not xml_path.exists():
        print("指定されたファイルが存在しません。")
        return

    score = converter.parse(xml_path)

    print("=== 指番号付与開始 ===")
    add_test_fingerings(score)
    print("\n=== 指番号付与終了 ===")

    output_path = xml_path.with_name(xml_path.stem + "_fingering_test.musicxml")
    score.write("musicxml", fp=output_path)

    print(f"\n保存しました：{output_path}")


if __name__ == "__main__":
    main()