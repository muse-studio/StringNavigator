
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import copy

# 入力ファイル
source_path = Path("SUZUKI-7-3_位置調整済.mscz")
target_path = Path("SUZUKI-7-3_位置未調整.mscz")

# 出力ファイル
output_path = Path("test_position_copied.mscz")


def read_mscz(path):
    with zipfile.ZipFile(path, "r") as z:
        mscx_name = next(
            name for name in z.namelist()
            if name.endswith(".mscx")
        )
        root = ET.fromstring(z.read(mscx_name))
    return root


# 2つの楽譜を読み込む
source_root = read_mscz(source_path)
target_root = read_mscz(target_path)

# 42小節目を取得
source_measure = source_root.find(
    "./Score/Staff"
).findall("Measure")[41]

target_measure = target_root.find(
    "./Score/Staff"
).findall("Measure")[41]

# 声部ごとに指番号の位置情報をコピー
for voice_index, (source_voice, target_voice) in enumerate(
    zip(
        source_measure.findall("voice"),
        target_measure.findall("voice")
    ),
    start=1
):
    source_fingerings = list(source_voice.iter("Fingering"))
    target_fingerings = list(target_voice.iter("Fingering"))

    # 対応関係を確認
    source_numbers = [f.findtext("text") for f in source_fingerings]
    target_numbers = [f.findtext("text") for f in target_fingerings]

    if source_numbers != target_numbers:
        raise ValueError(
            f"Voice {voice_index} の指番号が一致しません"
        )

    for src, dst in zip(source_fingerings, target_fingerings):
        # 既存の位置設定を削除
        for tag in ("offset", "minDistance"):
            old = dst.find(tag)
            if old is not None:
                dst.remove(old)

        # 調整済みの位置設定をコピー
        for tag in ("offset", "minDistance"):
            element = src.find(tag)
            if element is not None:
                # text要素の直前に位置設定を挿入
                text_element = dst.find("text")
                insert_index = list(dst).index(text_element)

                dst.insert(insert_index, copy.deepcopy(element))
                

# MusicXMLではなくMuseScore形式で保存
xml_data = ET.tostring(
    target_root,
    encoding="utf-8",
    xml_declaration=True
)

with zipfile.ZipFile(target_path, "r") as src_zip:
    with zipfile.ZipFile(output_path, "w") as dst_zip:
        for item in src_zip.infolist():
            data = src_zip.read(item.filename)

            if item.filename.endswith(".mscx"):
                data = xml_data

            dst_zip.writestr(item, data)

print("出力完了:", output_path)
