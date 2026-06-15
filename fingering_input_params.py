import math
from dataclasses import dataclass
from functools import lru_cache
from music21 import converter, note, chord, tempo


Strings = {
    0: ("G", 55),
    1: ("D", 62),
    2: ("A", 69),
    3: ("E", 76),
}

Fingers = [0, 1, 2, 3, 4]

# FI  1=半音、2=全音
FI_PATTERNS = [
    (1, 1, 1),
    (1, 1, 2),
    (1, 2, 1),
    (1, 2, 2),
    (2, 1, 1),
    (2, 1, 2),
    (2, 2, 1),
    (2, 2, 2),
]


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


@dataclass(frozen=True)
class State:
    sp: int
    fn: int
    hp: int
    fi: tuple


# e：表現度
def expression_degree(note_length, L):
    if L == math.inf:
        return 0.0
    return min(note_length / L, 1.0)


# finger_offsetの定義
def finger_offset(fn, fi):
    if fn == 0:
        return 0
    if fn == 1:
        return 0
    if fn == 2:
        return fi[0]
    if fn == 3:
        return fi[0] + fi[1]
    if fn == 4:
        return fi[0] + fi[1] + fi[2]


# s：状態
# s = {sp, fn, hp, fi}
def generate_states(pitch):
    states = []

    for sp, (string_name, open_pitch) in Strings.items():
        semitone = pitch - open_pitch

        if semitone < 0:
            continue

        for fi in FI_PATTERNS:
            for fn in Fingers:

                # 開放弦の場合
                if fn == 0:
                    if semitone == 0:
                        states.append(State(sp, fn, 0, fi))
                    continue

                # 押弦の場合
                offset = finger_offset(fn, fi)
                hp = semitone - offset - 1

                # 開放弦のすぐ上の音は1の指で取る場合はここを有効化
                # if semitone in [1, 2] and fn != 1:
                #     continue

                if 0 <= hp < 24:
                    states.append(State(sp, fn, hp, fi))

    return tuple(states)


# generate_states(pitch) のメモ化版
@lru_cache(maxsize=None)
def generate_states_cached(pitch):
    return generate_states(pitch)


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
def estimate_fingering(pitches, note_lengths, L):
    if len(pitches) != len(note_lengths):
        raise ValueError("pitches と note_lengths の長さが一致していません")

    # ここで generate_states_cached を使う
    all_states = [generate_states_cached(pitch) for pitch in pitches]

    for i, states in enumerate(all_states):
        if len(states) == 0:
            raise ValueError(f"{i}番目の音で有効な状態がありません")

    N = len(pitches)

    dp = []
    back = []

    # 1音目
    first_dp = {}
    first_back = {}

    e0 = expression_degree(note_lengths[0], L)

    for state in all_states[0]:
        first_dp[state] = pressing_cost(state, pitches[0], e0)
        first_back[state] = None

    dp.append(first_dp)
    back.append(first_back)

    # 2音目以降
    for n in range(1, N):
        e = expression_degree(note_lengths[n], L)

        current_dp = {}
        current_back = {}

        for state_j in all_states[n]:
            best_cost = math.inf
            best_prev = None

            for state_i in all_states[n - 1]:
                cost = (
                    dp[n - 1][state_i]
                    + transition_cost(state_i, state_j)
                    + pressing_cost(state_j, pitches[n], e)
                )

                if cost < best_cost:
                    best_cost = cost
                    best_prev = state_i

            current_dp[state_j] = best_cost
            current_back[state_j] = best_prev

        dp.append(current_dp)
        back.append(current_back)

    last_state = min(dp[-1], key=dp[-1].get)

    best_path = [last_state]

    for n in range(N - 1, 0, -1):
        last_state = back[n][last_state]
        best_path.append(last_state)

    best_path.reverse()
    return best_path


# MusicXML読み込み関数
def load_musicxml(path):
    score = converter.parse(path)

    tempos = score.flatten().getElementsByClass(tempo.MetronomeMark)

    if len(tempos) > 0 and tempos[0].number is not None:
        bpm = tempos[0].number
    else:
        bpm = 120

    seconds_per_quarter = 60 / bpm

    pitches = []
    note_lengths = []

    for element in score.flatten().notes:
        if isinstance(element, note.Note):
            pitches.append(element.pitch.midi)
            note_lengths.append(float(element.quarterLength) * seconds_per_quarter)

        elif isinstance(element, chord.Chord):
            highest_note = element.pitches[-1]
            pitches.append(highest_note.midi)
            note_lengths.append(float(element.quarterLength) * seconds_per_quarter)

    print("BPM:", bpm)

    return pitches, note_lengths


# 結果表示関数
def print_result(best_path):
    string_name = {
        0: "G",
        1: "D",
        2: "A",
        3: "E",
    }

    finger_names = {
        0: "0",
        1: "1",
        2: "2",
        3: "3",
        4: "4",
    }

    for i, state in enumerate(best_path):
        print(
            f"{i + 1}音目："
            f"{string_name[state.sp]}, "
            f"{finger_names[state.fn]}, "
            f"HP = {state.hp}, "
            f"FI = {state.fi}"
        )


# キャッシュ確認用
def print_cache_info():
    print("\n--- cache info ---")
    print("generate_states_cached:", generate_states_cached.cache_info())
    print("transition_cost:", transition_cost.cache_info())
    print("pressing_cost:", pressing_cost.cache_info())


# 実行部分
if __name__ == "__main__":
    input_parameters()

    xml_path = input("\nMusicXML_path:")

    pitches, note_lengths = load_musicxml(xml_path)

    print("pitch:", pitches)
    print("note_lengths:", note_lengths)

    # 初心者
    print("\nBeginner")
    L_easy = math.inf
    best_path_easy = estimate_fingering(pitches, note_lengths, L_easy)
    print_result(best_path_easy)

    # 中級者
    print("\nIntermediate")
    L_mid = 0.1
    best_path_mid = estimate_fingering(pitches, note_lengths, L_mid)
    print_result(best_path_mid)

    # メモ化が効いているか確認
    print_cache_info()