
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

# 入力ファイル
input_path = Path("SUZUKI-7-3_位置調整済.mscz")

# 出力ファイル
output_path = Path("test_offset_changed.mscx")

# msczからmscxを取り出す
with zipfile.ZipFile(input_path, "r") as z:
    mscx_name = next(
        name for name in z.namelist()
        if name.endswith(".mscx")
    )
    xml_data = z.read(mscx_name)

# XMLを読み込む
root = ET.fromstring(xml_data)

# 42小節目を取得
staff = root.find("./Score/Staff")
measures = staff.findall("Measure")
measure42 = measures[41]

# 42小節目の指番号だけを探す
# 42小節目のVoice 2を取得
voices = measure42.findall("voice")
voice2 = voices[1]

# Voice 2の指番号を下方向に2sp移動
for fingering in voice2.iter("Fingering"):
    offset = fingering.find("offset")

    if offset is None:
        offset = ET.SubElement(fingering, "offset")

    y = float(offset.get("y", "0"))
    offset.set("y", str(y + 2))

    print(
        "指番号:", fingering.findtext("text"),
        "変更後:", offset.attrib
    )

# mscxとして保存
tree = ET.ElementTree(root)
tree.write(
    output_path,
    encoding="utf-8",
    xml_declaration=True
)

print("出力完了:", output_path)
