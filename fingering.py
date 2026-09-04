import math
import tkinter as tk

from tkinter import filedialog
from pathlib import Path
from functools import lru_cache

from music21 import (
    articulations,
    chord,
    converter,
    expressions,
    note,
    stream,
    tempo,
)

from generators.state_generator import (
    Fingers,
    FI_PATTERNS,
    Strings,
    finger_offset,
    generate_event_music_states,
    generate_states_cached,
)

from generators.state_generator import Strings, Fingers

from double_stop_prepare import (
    music_state_pressing_cost,
    music_state_transition_cost,
)



# k と σ^2 の設定値
# ※ ここでは sigma ではなく、論文の式に入れる「分散 σ^2」を入力します。
PARAMS = {
    "sigma2_1": 1.0,  # 式(4) 弦移動
    "sigma2_2": 1.0,  # 式(5) HP移動
    "k1": 3.0,        # 式(6) FI移動
    "sigma2_3": 1.0,  # 式(8) 弦押弦
    "k2": 3.0,        # 式(9) 指番号
    "sigma2_4": 7.0,  # 式(9) 指番号 表現側
    "sigma2_5": 5.0,  # 式(10) HP押弦
    "k3": 3.0,        # 式(11) FI押弦
}


def select_musicxml_file_dialog():
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title = "MusicXMLファイルを選択してください",
        filetypes = [
            ("MusicXML files", "*.musicxml *.xml *.mxl" ),
            ("Compressed MusicXML files", "*.mxl"),
            ("All files", "*.*"),
        ]
    )

    root.destroy()

    if not file_path:
        raise FileNotFoundError("MusicXMLファイルが選択されませんでした。")

    return Path(file_path)

def select_output_folder_dialog():
    root = tk.Tk()
    root.withdraw()

    folder_path = filedialog.askdirectory(
        title="PDFの保存先フォルダを選択してください"
    )

    root.destroy()

    if not folder_path:
        raise FileNotFoundError("保存先フォルダが選択されませんでした。")

    return Path(folder_path)



def input_float_with_default(label, default, positive=True):
    while True:
        text = input(f"{label} [{default}]: ").strip()

        if text == "":
            return float(default)

        try:
            value = float(text)
        except ValueError:
            print("数値で入力してください。例：1, 0.5, 3")
            continue

        if positive and value <= 0:
            print("0より大きい値を入力してください。")
            continue

        return value


def input_parameters():
    print("\n--- パラメータ設定 ---")
    print("何も入力せずEnterを押すと、[]内の値を使います。")
    print("sigma は σ ではなく σ^2（分散）の値として入力してください。")

    PARAMS["sigma2_1"] = input_float_with_default("sigma2_1 式(4) 弦移動", PARAMS["sigma2_1"])
    PARAMS["sigma2_2"] = input_float_with_default("sigma2_2 式(5) HP移動", PARAMS["sigma2_2"])
    PARAMS["k1"] = input_float_with_default("k1 式(6) FI移動", PARAMS["k1"])
    PARAMS["sigma2_3"] = input_float_with_default("sigma2_3 式(8) 弦押弦", PARAMS["sigma2_3"])
    PARAMS["k2"] = input_float_with_default("k2 式(9) 指番号", PARAMS["k2"])
    PARAMS["sigma2_4"] = input_float_with_default("sigma2_4 式(9) 指番号 表現側", PARAMS["sigma2_4"])
    PARAMS["sigma2_5"] = input_float_with_default("sigma2_5 式(10) HP押弦", PARAMS["sigma2_5"])
    PARAMS["k3"] = input_float_with_default("k3 式(11) FI押弦", PARAMS["k3"])

    # k や σ^2 を変えた後に、古いコスト計算結果が残らないようにする
    transition_cost.cache_clear()
    pressing_cost.cache_clear()

    print("\n設定されたパラメータ:")
    for key, value in PARAMS.items():
        print(f"{key} = {value}")

# e：表現度
def expression_degree(note_length, L):
    if L == math.inf:
        return 0.0
    return min(note_length / L, 1.0)


# 確率密度関数
def normal_pdf(x, mu, sigma2):
    return (1 / math.sqrt(2 * math.pi * sigma2)) * math.exp(
        -((x - mu) ** 2) / (2 * sigma2)
    )


# 式(4)
def C_SP_transition(sp_i, sp_j):
    sigma2_1 = PARAMS["sigma2_1"]
    x = abs(sp_i - sp_j)

    denom = 0.0
    for sp_p in Strings.keys():
        for sp_q in Strings.keys():
            xpq = abs(sp_p - sp_q)
            denom += normal_pdf(xpq, 0, sigma2_1)

    prob = normal_pdf(x, 0, sigma2_1) / denom
    return -math.log(prob)


# 式(5)
def C_HP_transition(hp_i, hp_j):
    sigma2_2 = PARAMS["sigma2_2"]
    x = abs(hp_i - hp_j)

    denom = 0.0
    for hp_p in range(24):
        for hp_q in range(24):
            xpq = abs(hp_p - hp_q)
            denom += normal_pdf(xpq, 0, sigma2_2)

    prob = normal_pdf(x, 0, sigma2_2) / denom
    return -math.log(prob)


# 式(6)
def C_FI_transition(fi_i, fi_j):
    k1 = PARAMS["k1"]
    if fi_i == fi_j:
        x = 0
    else:
        x = 1

    prob = (k1 + (1 - k1) * x) / (k1 + 1)
    return -math.log(prob)


# 式(3)
# ここがメモ化される
@lru_cache(maxsize=None)
def transition_cost(state_i, state_j):
    cost_sp = C_SP_transition(state_i.sp, state_j.sp)
    cost_hp = C_HP_transition(state_i.hp, state_j.hp)
    cost_fi = C_FI_transition(state_i.fi, state_j.fi)
    return cost_sp + cost_hp + cost_fi


# 式(7)
# 押弦コストもメモ化
@lru_cache(maxsize=None)
def pressing_cost(state_i, pitch, e):
    if not is_valid_state(state_i, pitch):
        return float("inf")

    return (
        C_SP_press(state_i.sp, e)
        + C_FN_press(state_i.fn, e)
        + C_HP_press(state_i.hp)
        + C_FI_press(state_i.fi)
    )


def is_valid_state(state, pitch):
    sp = state.sp
    fn = state.fn
    hp = state.hp
    fi = state.fi

    open_pitch = Strings[sp][1]
    semitone = pitch - open_pitch

    if semitone < 0:
        return False

    if fn == 0:
        return semitone == 0

    # 開放弦のすぐ上の音は1の指に限定する場合はここを有効化
    # if semitone in [1, 2] and fn != 1:
    #     return False

    return semitone == hp + finger_offset(fn, fi) + 1


# 式(8)
def C_SP_press(sp_i, e):
    sigma2_3 = PARAMS["sigma2_3"]
    denom = 0.0
    for sp_p in Strings.keys():
        denom += normal_pdf(sp_p, 0, sigma2_3)

    easy_part = (1 / 4) * (1 - e)
    expression_part = (normal_pdf(sp_i, 0, sigma2_3) / denom) * e

    prob = easy_part + expression_part
    return -math.log(prob)


# 式(9)
def C_FN_press(fn_i, e):
    k2 = PARAMS["k2"]
    sigma2_4 = PARAMS["sigma2_4"]
    x1 = {0: 0, 1: 1, 2: 1, 3: 1, 4: 2}
    x2 = {3: 0, 2: 1, 1: 2, 4: 3, 0: 4}

    easy_part = ((2 * k2 + (1 - k2) * x1[fn_i]) / (3 * (k2 + 1))) * (1 - e)

    denom = 0.0
    for fn_p in Fingers:
        denom += normal_pdf(x2[fn_p], 0, sigma2_4)

    expression_part = (normal_pdf(x2[fn_i], 0, sigma2_4) / denom) * e

    prob = easy_part + expression_part
    return -math.log(prob)


# 式(10)
def C_HP_press(hp_i):
    sigma2_5 = PARAMS["sigma2_5"]
    hp_order = [1, 0, 4, 2, 3] + list(range(5, 24))

    hp_rank = {}
    for rank, hp in enumerate(hp_order):
        hp_rank[hp] = rank

    x = hp_rank[hp_i]

    denom = 0.0
    for hp_p in range(24):
        xp = hp_rank[hp_p]
        denom += normal_pdf(xp, 0, sigma2_5)

    prob = normal_pdf(x, 0, sigma2_5) / denom
    return -math.log(prob)


# 式(11)
def C_FI_press(fi_i):
    k3 = PARAMS["k3"]
    half_count = fi_i.count(1)

    if half_count == 0 or half_count == 1:
        x = 0
    elif half_count == 2:
        x = 1
    else:
        x = 2

    prob = (2 * k3 + (1 - k3) * x) / (3 * (k3 + 1))
    return -math.log(prob)


# 式(12)


def is_same_held_state(prev_state, curr_state):
    """
    継続中の同じ音符について、
    前後で同じ押さえ方になっているか確認する。
    """

    # 開放弦の場合
    # FIは実際の押弦には関係しないので、
    # 同じ弦の開放弦なら同じ状態として扱う
    if prev_state.fn == 0 and curr_state.fn == 0:
        return prev_state.sp == curr_state.sp

    if(
        prev_state.sp != curr_state.sp
        or prev_state.fn != curr_state.fn
        or prev_state.hp != curr_state.hp
    ):
        return False

    if prev_state.fn == 1:
        return True

    if prev_state.fn == 2:
        return(
            prev_state.fi[0]
            == curr_state.fi[0]
        )

    if prev_state.fn == 3:
        return(
            prev_state.fi[:2]
            == curr_state.fi[:2]
        )

    if prev_state.fn == 4:
        return(
            prev_state.fi
            == curr_state.fi
        )

    return False

    # 押弦の場合はState全体が同じであることを要求
#    return prev_state == curr_state




def sustained_notes_are_valid(
        prev_music_state,
        curr_music_state,
        prev_timeline_event,
        curr_timeline_event):

    """
    前後のtimeline eventに同じsource_idがある場合、
    その音のStateが維持されているか確認する。
    """

    prev_states = {
        item["source_id"]: state
        for item, state in zip(
            prev_timeline_event["items"],
            prev_music_state.states
        )
    }

    curr_states = {
        item["source_id"]: state
        for item, state in zip(
            curr_timeline_event["items"],
            curr_music_state.states
        )
    }

    common_source_ids = (
        prev_states.keys()
        & curr_states.keys()
    )

    for source_id in common_source_ids:

        if not is_same_held_state(
            prev_states[source_id],
            curr_states[source_id]
        ):
            return False

    return True



def estimate_fingering(
        events,
        note_lengths,
        L,
        timeline_events=None):

    if len(events) != len(note_lengths):
        raise ValueError(
            "eventsとnote_lengthsの長さが一致していません"
        )
    
    if (
            timeline_events is not None
            and len(events) != len(timeline_events)
        ):
            raise ValueError(
                "events と timeline_events の長さが一致していません"
            )

    # 単音・二重音・三重音・四重音を
    # MusicStateとして候補生成する
    all_music_states = [
        generate_event_music_states(event, generate_states_cached)
        for event in events
    ]

    for i, music_states in enumerate(all_music_states):
        if len(music_states) == 0:
            raise ValueError(f"{i}番目の音で有効な MusicState がありません: event={events[i]}")

    N = len(events)

    dp = []
    back = []

    # 1音目
    first_dp = {}
    first_back = {}

    e0 = expression_degree(note_lengths[0], L)

    for music_state in all_music_states[0]:
        first_dp[music_state] = (
            music_state_pressing_cost(
                music_state,
                events[0],
                e0,
                pressing_cost,
                C_HP_press,
                C_FI_press
            )
        )
        first_back[music_state] = None

    dp.append(first_dp)
    back.append(first_back)

    # 2音目以降
    for n in range(1, N):
        e = expression_degree(note_lengths[n], L)

        current_dp = {}
        current_back = {}

        for music_state_j in all_music_states[n]:
            best_cost = math.inf
            best_prev = None

            for music_state_i in all_music_states[n - 1]:

                if timeline_events is not None:

                    if not sustained_notes_are_valid(
                        music_state_i,
                        music_state_j,
                        timeline_events[n - 1],
                        timeline_events[n]
                    ):
                        continue

                cost = (
                    dp[n - 1][music_state_i]
                    + music_state_transition_cost(
                        music_state_i,
                        music_state_j,
                        transition_cost
                    )
                    + music_state_pressing_cost(
                        music_state_j,
                        events[n],
                        e,
                        pressing_cost,
                        C_HP_press,
                        C_FI_press
                    )
                )

                if cost < best_cost:
                    best_cost = cost
                    best_prev = music_state_i

            current_dp[music_state_j] = best_cost
            current_back[music_state_j] = best_prev

        reachable_states = [
            music_state
            for music_state, cost in current_dp.items()
            if cost < math.inf
        ]

        if not reachable_states:
            print("\n=== DP経路なし ===")
            print("event番号:", n)
            print("前event:", events[n - 1])
            print("現在event:", events[n])

            if timeline_events is not None:
                print(
                    "前source_ids:",
                    [
                        item["source_id"]
                        for item in timeline_events[n - 1]["items"]
                    ]
                )
                print(
                    "現在source_ids:",
                    [
                        item["source_id"]
                        for item in timeline_events[n]["items"]
                    ]
                )

            print("\n--- 継続音の候補確認 ---")

            common_ids = (
                {
                    item["source_id"]
                    for item in timeline_events[n - 1]["items"]
                }
                &
                {
                    item["source_id"]
                    for item in timeline_events[n]["items"]
                }
            )

            for source_id in common_ids:

                prev_index = next(
                    i
                    for i, item in enumerate(
                        timeline_events[n - 1]["items"]
                    )
                    if item["source_id"] == source_id
                )

                curr_index = next(
                    i
                    for i, item in enumerate(
                        timeline_events[n]["items"]
                    )
                    if item["source_id"] == source_id
                )

                print(
                    f"\nsource_id={source_id}"
                )

                print("前eventで到達可能なState:")

                prev_held_states = set()

                for music_state, cost in dp[n - 1].items():

                    if cost < math.inf:
                        state = music_state.states[prev_index]
                        prev_held_states.add(state)

                for state in prev_held_states:
                    print(
                        " ",
                        state_to_text(state)
                    )

                print("現在eventの候補State:")

                curr_held_states = set()

                for music_state in all_music_states[n]:
                    state = music_state.states[curr_index]
                    curr_held_states.add(state)

                for state in curr_held_states:
                    print(
                        " ",
                        state_to_text(state)
                    )

                print("共通State:")

                common_states = (
                    prev_held_states
                    & curr_held_states
                )

                for state in common_states:
                    print(
                        " ",
                        state_to_text(state)
                    )

                print(
                    "共通State数:",
                    len(common_states)
                )


            raise RuntimeError(
                f"event {n} に到達できるMusicStateがありません"
            )


        dp.append(current_dp)
        back.append(current_back)

    last_music_state = min(dp[-1], key=dp[-1].get)

    best_path = [last_music_state]

    for n in range(N - 1, 0, -1):
        last_music_state = back[n][last_music_state]
        best_path.append(last_music_state)

    best_path.reverse()
    return best_path

def estimate_fingering_segmented(
        score,
        events,
        note_lengths,
        timeline_events,
        bpm,
        L,
        long_note_threshold=2.0):

    boundaries = detect_timeline_segment_boundaries(
        score,
        timeline_events,
        bpm,
        long_note_threshold
    )

    segments = []

    start = 0

    for end in boundaries:
        segments.append((start, end))
        start = end

    segments.append((start, len(events)))

    print(f"\n{len(segments)}個の区間に分割しました")

    best_path = []

    for seg_no, (s, e) in enumerate(segments):

        print(
            f"\r[{seg_no+1}/{len(segments)}] "
            f"{e-s}音 DP実行中...",
            end="",
            flush=True
        )

        segment_path = estimate_fingering(
            events[s:e],
            note_lengths[s:e],
            L,
            timeline_events[s:e]
        )

        best_path.extend(segment_path)

    print()

    return best_path




# MusicXML読み込み関数
# MusicXML読み込み関数
def load_musicxml(path):
    score = converter.parse(str(path))

    tempos = score.flatten().getElementsByClass(
        tempo.MetronomeMark
    )

    if len(tempos) > 0 and tempos[0].number is not None:
        bpm = tempos[0].number
    else:
        bpm = 120

    seconds_per_quarter = 60 / bpm

    events = []
    note_lengths = []

    for element in score.flatten().notes:
        # =========================
        # 単音
        # =========================
        if isinstance(element, note.Note):
            events.append(
                [element.pitch.midi]
            )

            note_lengths.append(
                float(element.quarterLength)
                * seconds_per_quarter
            )

        # =========================
        # 2～4重音
        # =========================
        elif isinstance(element, chord.Chord):
            pitches = sorted(
                p.midi
                for p in element.pitches
            )

            if len(pitches) < 2 or len(pitches) > 4:
                raise ValueError(
                    "1音から4音までに対応しています。"
                    f"{len(pitches)}音の重音があります。"
                )

            events.append(pitches)

            note_lengths.append(
                float(element.quarterLength)
                * seconds_per_quarter
            )

    print("BPM:", bpm)

    return score, events, note_lengths, bpm


def build_timeline_events(score):
    """
    楽譜を時間区間に分割し、
    各区間で実際に鳴っている音高を取得する。
    """

    elements = list(score.flatten().notes)

    note_infos = []

    # 各音の開始時刻・終了時刻・pitchを保存
    source_id = 0

    for element in elements:
        start = float(element.offset)
        end = start + float(element.quarterLength)

        # 単音
        if isinstance(element, note.Note):

            note_infos.append({
                "source_id": source_id,
                "start": start,
                "end": end,
                "pitch": element.pitch.midi,
                "element": element,
                "pitch_index": 0
            })

            source_id += 1

        # Chord
        elif isinstance(element, chord.Chord):

            for pitch_index, pitch in enumerate(element.pitches):

                note_infos.append({
                    "source_id": source_id,
                    "start": start,
                    "end": end,
                    "pitch": pitch.midi,
                    "element": element,
                    "pitch_index": pitch_index
                })

                source_id += 1

    # 音の開始・終了時刻をすべて集める
    time_points = set()

    for info in note_infos:
        time_points.add(info["start"])
        time_points.add(info["end"])

    time_points = sorted(time_points)

    timeline_events = []

    # 隣り合う時刻の間で鳴っている音を調べる
    for i in range(len(time_points) - 1):
        start = time_points[i]
        end = time_points[i + 1]

        active_items = []

        for info in note_infos:
            if info["start"] <= start < info["end"]:

                active_items.append({
                    "source_id": info["source_id"],
                    "start": info["start"],
                    "end": info["end"],
                    "pitch": info["pitch"],
                    "element": info["element"],
                    "pitch_index": info["pitch_index"]
                })

        if active_items:

            # pitchの低い順に並べる
            active_items.sort(
                key=lambda item: item["pitch"]
            )

            active_pitches = [
                item["pitch"]
                for item in active_items
            ]

            timeline_events.append({
                "start": start,
                "end": end,
                "pitches": active_pitches,
                "items": active_items
            })

    return timeline_events

def get_double_barline_offsets(score):
    """
    二重線・終止線がある位置を
    楽譜全体のoffsetとして取得する。
    """

    offsets = []

    for measure in score.parts[0].getElementsByClass("Measure"):

        right_barline = measure.rightBarline

        if right_barline is None:
            continue

        if right_barline.type in [
            "double",
            "final",
            "light-light",
            "light-heavy"
        ]:
            # 小節の開始位置 + 小節の長さ
            barline_offset = (
                float(measure.offset)
                + float(measure.barDuration.quarterLength)
            )

            offsets.append(barline_offset)

    return offsets

def get_timeline_barline_boundaries(
        timeline_events,
        double_barline_offsets):
    """
    二重線のoffsetを、
    timeline eventの区切り位置に変換する。
    """

    boundaries = []

    for offset in double_barline_offsets:

        for i, event in enumerate(timeline_events):

            if event["end"] == offset:

                boundary = i + 1

                # 最後のeventの後は区切る必要がない
                if boundary < len(timeline_events):
                    boundaries.append(boundary)

                break

    return boundaries

def get_timeline_long_note_boundaries(
        timeline_events,
        bpm,
        long_note_threshold):

    """
    元の音符の長さを使って、
    長い音符が終わる位置をtimeline境界に変換する。
    """

    boundaries = []

    if long_note_threshold is None:
        return boundaries

    seconds_per_quarter = 60 / bpm

    # source_idごとに1回だけ確認する
    source_items = {}

    for event in timeline_events:
        for item in event["items"]:
            source_items[item["source_id"]] = item

    # 長い音符の終了位置を集める
    long_note_end_offsets = set()

    for item in source_items.values():

        quarter_length = (
            item["end"] - item["start"]
        )

        length_seconds = (
            quarter_length
            * seconds_per_quarter
        )

        if length_seconds >= long_note_threshold:
            long_note_end_offsets.add(
                item["end"]
            )

    # 音符の終了位置を
    # timeline eventの境界番号に変換する
    for end_offset in sorted(long_note_end_offsets):

        for i, event in enumerate(timeline_events):

            if event["end"] == end_offset:

                boundary = i + 1

                if boundary < len(timeline_events):
                    boundaries.append(boundary)

                break

    return sorted(set(boundaries))



def detect_timeline_segment_boundaries(
        score,
        timeline_events,
        bpm,
        long_note_threshold=2.0):

    double_barline_offsets = get_double_barline_offsets(score)

    barline_boundaries = get_timeline_barline_boundaries(
        timeline_events,
        double_barline_offsets
    )

    long_note_boundaries = get_timeline_long_note_boundaries(
        timeline_events,
        bpm,
        long_note_threshold
    )

    boundaries = sorted(
        set(barline_boundaries + long_note_boundaries)
    )

    return boundaries




def timeline_to_events(timeline_events, bpm):
    """
    timeline_events を
    DPで使用する events と note_lengths に変換する。
    """

    seconds_per_quarter = 60 / bpm

    events = []
    note_lengths = []

    for timeline_event in timeline_events:
        pitches = timeline_event["pitches"]

        start = timeline_event["start"]
        end = timeline_event["end"]

        quarter_length = end - start
        length_seconds = quarter_length * seconds_per_quarter

        events.append(pitches)
        note_lengths.append(length_seconds)

    return events, note_lengths



def state_to_text(state):
    string_name = Strings[state.sp][0]
    return f"{string_name}線, {state.fn}指, HP={state.hp}, FI={state.fi}"

def build_source_state_map(
        timeline_events,
        best_path):

    """
    source_idごとに、
    その音が最初に現れたtimeline eventでの
    Stateを保存する。
    """

    source_state_map = {}

    for timeline_event, music_state in zip(
            timeline_events,
            best_path):

        for item, state in zip(
                timeline_event["items"],
                music_state.states):

            source_id = item["source_id"]

            # 同じsource_idが複数のtimeline eventに
            # 現れても、最初のStateだけ保存する
            if source_id not in source_state_map:
                source_state_map[source_id] = state

    return source_state_map

def build_source_item_map(timeline_events):
    """
    source_idごとに元の音符情報を保存する。
    """

    source_item_map = {}

    for timeline_event in timeline_events:

        for item in timeline_event["items"]:

            source_id = item["source_id"]

            if source_id not in source_item_map:
                source_item_map[source_id] = item

    return source_item_map


def print_music_state_candidates(events):
    print("\n=== 1～4音の候補確認 ===")

    event_names = {
        1: "単音",
        2: "二重音",
        3: "三重音",
        4: "四重音",
    }

    for i, event in enumerate(events, start=1):
        candidates = generate_event_music_states(
            event,
            generate_states_cached
        )

        event_name = event_names[len(event)]

        print(
            f"\n{i}音目："
            f"{event_name} pitches={event}"
        )

        print(f"候補数：{len(candidates)}")

        for j, music_state in enumerate(
            candidates[:10],
            start=1
        ):
            print(f"候補{j}")

            states = music_state.states
            state_count = len(states)

            for state_index, state in enumerate(
                states,
                start=1
            ):
                if state_count == 1:
                    label = "単音"

                elif state_index == 1:
                    label = "最低音"

                elif state_index == state_count:
                    label = "最高音"

                else:
                    label = f"中間音{state_index - 1}"

                print(
                    f"  {label}："
                    + state_to_text(state)
                )

        if len(candidates) > 10:
            print(
                f"... 他 {len(candidates) - 10} 個"
            )


# 結果表示関数
def print_result(best_path):
    event_names = {
        1: "単音",
        2: "二重音",
        3: "三重音",
        4: "四重音",
    }

    for i, music_state in enumerate(
        best_path,
        start=1
    ):
        states = music_state.states
        state_count = len(states)
        event_name = event_names[state_count]

        print(f"{i}音目：{event_name}")

        for state_index, state in enumerate(
            states,
            start=1
        ):
            if state_count == 1:
                label = "単音"

            elif state_index == 1:
                label = "最低音"

            elif state_index == state_count:
                label = "最高音"

            else:
                label = f"中間音{state_index - 1}"

            print(
                f"  {label}："
                + state_to_text(state)
            )


def input_mode_and_L():
    print("\n--- 出力する運指の種類 ---")
    print("1: Beginner（初心者） L = infinity, e = 0")
    print("2: Intermediate（中級者） L を指定")

    while True:
        choice = input("どちらを楽譜に書き込みますか？ [1/2]: ").strip()
        if choice == "1":
            return "Beginner", math.inf
        if choice == "2":
            L_mid = input_float_with_default("Intermediate の L", 0.1)
            return "Intermediate", L_mid
        print("1 か 2 を入力してください。")


def input_long_note_threshold():
    print("\n--- 区切る長い音符の設定 ---")
    print("1: 長い音符でも区切る")
    print("2: 長い音符では区切らない（二重線のみ）")

    while True:
        choice = input("選んでください [1/2]: ").strip()

        if choice == "1":
            return input_float_with_default(
                "何秒以上の音符で区切りますか？",
                1.0
            )

        if choice == "2":
            return None

        print("1 か 2 を入力してください。")




def fingering_label(state):
    string_name = Strings[state.sp][0]
    return f"{string_name}線-{state.fn}"


def clear_old_fingering_marks(score):
    # 同じファイルを何度も処理したとき、前回の運指表示が重ならないようにする
    for element in score.recurse().notes:
        if hasattr(element, "articulations"):
            element.articulations = [
                a for a in element.articulations
                if not isinstance(a, articulations.Fingering)
            ]
        if hasattr(element, "expressions"):
            element.expressions = [
                ex for ex in element.expressions
                if not (isinstance(ex, expressions.TextExpression) and str(ex.content).startswith("String:"))
            ]


def annotate_score_with_source_states(
        score,
        timeline_events,
        source_state_map):

    """
    source_idを使って、
    元のNote・Chordに運指を書き込む。
    """

    source_item_map = build_source_item_map(
        timeline_events
    )

    # 以前の運指表示を削除
    clear_old_fingering_marks(score)

    # =========================
    # 通常のNote
    # =========================
    for source_id, item in source_item_map.items():

        element = item["element"]

        if not isinstance(element, note.Note):
            continue

        state = source_state_map[source_id]

        # 指番号
        fingering = articulations.Fingering(
            str(state.fn)
        )
        voice = element.getContextByClass(stream.Voice)

        # このsource_idが現れるtimeline eventを探す
        is_polyphonic = False

        for timeline_event in timeline_events:
            source_ids = [
                event_item["source_id"]
                for event_item in timeline_event["items"]
            ]

            if source_id in source_ids:
                # 同時に2音以上鳴っている場合だけ二声部分として扱う
                if len(timeline_event["items"]) >= 2:
                    is_polyphonic = True
                break

        # 二声部分のVoice 2だけ下に表示
        if (
            is_polyphonic
            and voice is not None
            and str(voice.id) == "2"
        ):
            fingering.placement = "below"
        else:
            fingering.placement = "above"

        element.articulations.append(fingering)

        # 弦名
        text = expressions.TextExpression(
            f"String:{Strings[state.sp][0]}"
        )
        text.placement = "below"
        element.expressions.append(text)

    # =========================
    # Chord
    # =========================
    chord_groups = {}

    for source_id, item in source_item_map.items():

        element = item["element"]

        if not isinstance(element, chord.Chord):
            continue

        key = id(element)

        if key not in chord_groups:
            chord_groups[key] = {
                "element": element,
                "states": []
            }

        chord_groups[key]["states"].append(
            (
                item["pitch_index"],
                source_state_map[source_id]
            )
        )

    # Chordごとにまとめて書き込む
    for chord_data in chord_groups.values():

        element = chord_data["element"]

        # Chord内の低音→高音の順
        indexed_states = sorted(
            chord_data["states"],
            key=lambda x: x[0]
        )

        states = [
            state
            for pitch_index, state in indexed_states
        ]

        # 指番号は楽譜上で高音→低音の順に表示
        fingering_text = "\n".join(
            str(state.fn)
            for state in reversed(states)
        )

        fingering = articulations.Fingering(
            fingering_text
        )
        fingering.placement = "above"
        element.articulations.append(fingering)

        # 使用弦は低音→高音
        string_names = [
            Strings[state.sp][0]
            for state in states
        ]

        text = expressions.TextExpression(
            "String:" + "-".join(string_names)
        )
        text.placement = "below"
        element.expressions.append(text)

    print(
        f"Note書き込み完了"
    )
    print(
        f"Chord書き込み数: {len(chord_groups)}"
    )

def annotate_score_with_fingering(
        score,
        best_path,
        mode_name
):
    notes_in_score = list(
        score.recurse().notes
    )

    if len(notes_in_score) != len(best_path):
        raise ValueError(
            f"楽譜中の音数({len(notes_in_score)})と"
            f"推定結果({len(best_path)})が一致しません"
        )

    clear_old_fingering_marks(score)

    for element, music_state in zip(
        notes_in_score,
        best_path
    ):
        states = music_state.states
        state_count = len(states)

        # =========================
        # 単音の場合
        # =========================
        if state_count == 1:
            state = states[0]

            element.articulations.append(
                articulations.Fingering(
                    str(state.fn)
                )
            )

            text = expressions.TextExpression(
                f"String:{Strings[state.sp][0]}"
            )
            text.placement = "below"
            element.expressions.append(text)

        # =========================
        # 2～4重音の場合
        # =========================
        elif 2 <= state_count <= 4:
            # statesは低音から高音の順で入っている。
            # 楽譜上では高音から低音の順に表示する。
            fingering_text = "\n".join(
                str(state.fn)
                for state in reversed(states)
            )

            fingering = articulations.Fingering(
                fingering_text
            )
            fingering.placement = "above"
            element.articulations.append(fingering)

            # 使用弦は低音側から表示する
            # 例：String:G-D-A
            string_names = [
                Strings[state.sp][0]
                for state in states
            ]

            string_text = (
                "String:"
                + "-".join(string_names)
            )

            text = expressions.TextExpression(
                string_text
            )
            text.placement = "below"
            element.expressions.append(text)

        else:
            raise ValueError(
                "1音から4音までに対応しています。"
            )

    if score.metadata is None:
        from music21 import metadata
        score.metadata = metadata.Metadata()

    score.metadata.title = (
        f"Fingering Result - {mode_name}"
    )

    return score


def write_annotated_outputs(score, output_base):
    musicxml_path = output_base + ".musicxml"
    pdf_path = output_base + ".pdf"

    # MusicXMLはほぼ確実に出力できる
    written_musicxml = score.write("musicxml", fp=musicxml_path)
    print("\nMusicXML出力:", written_musicxml)

    # PDF出力は MuseScore など、music21が使う楽譜レンダラー設定が必要
    try:
        written_pdf = score.write("musicxml.pdf", fp=pdf_path)
        print("PDF出力:", written_pdf)
    except Exception as e:
        print("\nPDF出力に失敗しました。")
        print("原因: music21からPDFを書き出すには MuseScore の設定が必要な場合があります。")
        print("先に出力された .musicxml を MuseScore で開くとPDF保存できます。")
        print("エラー内容:", e)



# キャッシュ確認用
def print_cache_info():
    print("\n--- cache info ---")
    print("generate_states_cached:", generate_states_cached.cache_info())
    print("transition_cost:", transition_cost.cache_info())
    print("pressing_cost:", pressing_cost.cache_info())


# 実行部分
if __name__ == "__main__":

    # MusicXMLを選択
    xml_path = select_musicxml_file_dialog()

    print("\n選択されたMusicXMLファイル：")
    print(xml_path)

    # MusicXML読み込み
    score, _, _, bpm = load_musicxml(xml_path)

    # 二声を含め、時間軸に沿ったeventを作成
    timeline_events = build_timeline_events(score)

    events, note_lengths = timeline_to_events(
        timeline_events,
        bpm
    )

    # パラメータ設定
    input_parameters()

    # Beginner / Intermediate
    mode_name, L = input_mode_and_L()

    print(f"\n{mode_name}")

    # 長い音符で区切るか設定
    long_note_threshold = input_long_note_threshold()

    # DP実行
    best_path = estimate_fingering_segmented(
        score,
        events,
        note_lengths,
        timeline_events,
        bpm,
        L,
        long_note_threshold=long_note_threshold
    )

    # timeline上の結果を
    # 元の音符のsource_idに対応させる
    source_state_map = build_source_state_map(
        timeline_events,
        best_path
    )

    # 楽譜へ運指を書き込む
    annotate_score_with_source_states(
        score,
        timeline_events,
        source_state_map
    )

    # 保存先を選択
    output_dir = select_output_folder_dialog()

    print("\nPDF保存先フォルダ：")
    print(output_dir)

    output_name = input(
        "\n出力ファイル名（拡張子なし、未入力なら fingering_result）:"
    ).strip()

    if output_name == "":
        output_name = "fingering_result"

    output_base = str(
        output_dir / output_name
    )

    # MusicXML / PDF出力
    write_annotated_outputs(
        score,
        output_base
    )

    # キャッシュ情報
    print_cache_info()