
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

INPUT_FILE = Path("SUZUKI-7-3_位置未調整.mscz")
OUTPUT_FILE = Path("test_adjusted.mscz")


def adjust_fingering_position(
    root,
    measure_number,
    voice_number,
    fingering_index,
    x=0,
    y=0
):
    """
    指定した指番号の表示位置を調整する。

    measure_number: 小節番号（1から）
    voice_number: 声部番号（1から）
    fingering_index: 声部内の指番号の順番（1から）
    x: 横方向の移動量（正で右）
    y: 縦方向の移動量（正で下）
    """

    staff = root.find("./Score/Staff")

    if staff is None:
        raise ValueError("Staffが見つかりません")

    measures = staff.findall("Measure")
    measure = measures[measure_number - 1]

    voices = measure.findall("voice")
    voice = voices[voice_number - 1]

    fingerings = list(voice.iter("Fingering"))
    fingering = fingerings[fingering_index - 1]

    # 現在の位置設定を取得
    offset = fingering.find("offset")

    if offset is None:
        offset = ET.Element("offset")

        # MuseScoreの要素順序に合わせる
        text_element = fingering.find("text")
        if text_element is not None:
            index = list(fingering).index(text_element)
            fingering.insert(index, offset)
        else:
            fingering.append(offset)

    old_x = float(offset.get("x", "0"))
    old_y = float(offset.get("y", "0"))

    # 現在の位置から相対的に移動
    offset.set("x", str(old_x + x))
    offset.set("y", str(old_y + y))

    print(
        f"{measure_number}小節目 "
        f"Voice {voice_number} "
        f"{fingering_index}番目 "
        f"指番号 {fingering.findtext('text')}"
    )
    print("変更後:", offset.attrib)


# MuseScoreファイルを読み込む
with zipfile.ZipFile(INPUT_FILE, "r") as z:
    mscx_name = next(
        name for name in z.namelist()
        if name.endswith(".mscx")
    )
    root = ET.fromstring(z.read(mscx_name))


# 調整する指番号の一覧
adjustments = [
    # (小節番号, Voice番号, 指番号の順番, x, y)
    (42, 1, 3, 1.53, -2.68),
    (42, 1, 4, 1.02, -2.43),
    (42, 2, 1, -1.15, 3.20),
]

# 指番号を順番に調整
for measure, voice, index, x, y in adjustments:
    adjust_fingering_position(
        root,
        measure_number=measure,
        voice_number=voice,
        fingering_index=index,
        x=x,
        y=y
    )


# XMLを保存
xml_data = ET.tostring(
    root,
    encoding="utf-8",
    xml_declaration=True
)

# msczとして出力
with zipfile.ZipFile(INPUT_FILE, "r") as src:
    with zipfile.ZipFile(OUTPUT_FILE, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)

            if item.filename == mscx_name:
                data = xml_data

            dst.writestr(item, data)

print("出力完了:", OUTPUT_FILE)
