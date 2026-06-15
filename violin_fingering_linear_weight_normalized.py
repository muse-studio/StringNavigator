import math
from dataclasses import dataclass
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

# cost_mode:
#   "normal" = 元の正規分布版
#              正規分布値 → 総和で正規化 → -log(prob)
#   "linear" = 比較用の線形評価版
#              線形重み → 総和で正規化 → -log(prob)
#
# どちらも「好ましさ」を確率のように正規化してから、
# DPで最小化できるように -log(prob) でコスト化する。
COST_MODE = "linear"


@dataclass(frozen=True)
class State:
    sp: int     # string position
    fn: int     # finger number
    hp: int     # hand position
    fi: tuple   # finger interval


# e：表現度
# e = min(l / L, 1)
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
    raise ValueError(f"未対応の指番号です: {fn}")


# s：状態
# s = {sp, fn, hp, fi}
def generate_states(pitch):
    states = []

    for sp, (string_name, open_pitch) in Strings.items():
        semitone = pitch - open_pitch

        # 開放弦より低い音はその弦で弾けない
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

                # 開放弦のすぐ上の音は1の指で取る場合は、下を有効化する
                # if semitone in [1, 2] and fn != 1:
                #     continue

                if 0 <= hp < 24:
                    states.append(State(sp, fn, hp, fi))

    return states


# 確率密度関数 =========================================================================================
# 正規分布(normal distribution)
def normal_pdf(x, mu, sigma2):
    return (1 / math.sqrt(2 * math.pi * sigma2)) * math.exp(-((x - mu) ** 2) / (2 * sigma2))


def safe_neg_log(prob):
    if prob <= 0:
        return float("inf")
    return -math.log(prob)


# 線形重み版 ===========================================================================================
def linear_weight_from_rank(rank, max_rank):
    """
    rank=0を最良、rank=max_rankを最悪として線形重みを作る。
    値が大きいほど好ましい。

    例:
        max_rank=3 のとき
        rank 0,1,2,3 -> weight 4,3,2,1
    """
    return (max_rank - rank) + 1


def normalize_weight(selected_weight, all_weights):
    """
    線形評価・正規分布評価を同じ形で比較するための正規化。
    選ばれた候補の重み / 全候補の重みの総和
    """
    total = sum(all_weights)
    if total <= 0:
        return 0.0
    return selected_weight / total


# 式(4) ===============================================================================================
# 弦の移動幅：正規分布版
def C_SP_transition_normal(sp_i, sp_j, sigma2_1=3):
    x = abs(sp_i - sp_j)

    denom = 0.0
    for sp_p in Strings.keys():
        for sp_q in Strings.keys():
            xpq = abs(sp_p - sp_q)
            denom += normal_pdf(xpq, 0, sigma2_1)

    prob = normal_pdf(x, 0, sigma2_1) / denom
    return safe_neg_log(prob)


# 式(4) 線形重み版
# 線形重み → 総和で正規化 → -log
def C_SP_transition_linear(sp_i, sp_j):
    x = abs(sp_i - sp_j)

    all_weights = []
    for sp_p in Strings.keys():
        for sp_q in Strings.keys():
            xpq = abs(sp_p - sp_q)
            all_weights.append(linear_weight_from_rank(xpq, 3))

    prob = normalize_weight(linear_weight_from_rank(x, 3), all_weights)
    return safe_neg_log(prob)


def C_SP_transition(sp_i, sp_j):
    if COST_MODE == "linear":
        return C_SP_transition_linear(sp_i, sp_j)
    return C_SP_transition_normal(sp_i, sp_j)


# 式(5) ===============================================================================================
# 手の移動幅：正規分布版
def C_HP_transition_normal(hp_i, hp_j, sigma2_2=2):
    x = abs(hp_i - hp_j)

    denom = 0.0
    for hp_p in range(24):
        for hp_q in range(24):
            xpq = abs(hp_p - hp_q)
            denom += normal_pdf(xpq, 0, sigma2_2)

    prob = normal_pdf(x, 0, sigma2_2) / denom
    return safe_neg_log(prob)


# 式(5) 線形重み版
# 線形重み → 総和で正規化 → -log
def C_HP_transition_linear(hp_i, hp_j):
    x = abs(hp_i - hp_j)

    all_weights = []
    for hp_p in range(24):
        for hp_q in range(24):
            xpq = abs(hp_p - hp_q)
            all_weights.append(linear_weight_from_rank(xpq, 23))

    prob = normalize_weight(linear_weight_from_rank(x, 23), all_weights)
    return safe_neg_log(prob)


def C_HP_transition(hp_i, hp_j):
    if COST_MODE == "linear":
        return C_HP_transition_linear(hp_i, hp_j)
    return C_HP_transition_normal(hp_i, hp_j)


# 式(6) ===============================================================================================
# 指の間隔：ここは元から正規分布ではないため、そのまま
def C_FI_transition(fi_i, fi_j, k1=3):
    if fi_i == fi_j:
        x = 0
    else:
        x = 1

    prob = (k1 + (1 - k1) * x) / (k1 + 1)
    return safe_neg_log(prob)


# 式(3) ===============================================================================================
# 遷移コストの定義
def transition_cost(state_i, state_j):
    cost_sp = C_SP_transition(state_i.sp, state_j.sp)
    cost_hp = C_HP_transition(state_i.hp, state_j.hp)
    cost_fi = C_FI_transition(state_i.fi, state_j.fi)
    return cost_sp + cost_hp + cost_fi


# 式(7) ===============================================================================================
# 押弦コストの定義
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

    # 開放弦のすぐ上の音は1の指で取る場合は、下を有効化する
    # if semitone in [1, 2] and fn != 1:
    #     return False

    return semitone == hp + finger_offset(fn, fi) + 1


# 式(8) ===============================================================================================
# SP押弦：正規分布版
def C_SP_press_normal(sp_i, e, sigma2_3=1):
    denom = 0.0
    for sp_p in Strings.keys():
        denom += normal_pdf(sp_p, 0, sigma2_3)

    # e = 0に近いとき弦に依存しない → 1/4
    easy_part = (1 / 4) * (1 - e)

    # e = 1に近いとき太い弦の方が好まれる
    expression_part = (normal_pdf(sp_i, 0, sigma2_3) / denom) * e

    prob = easy_part + expression_part
    return safe_neg_log(prob)


# 式(8) 線形重み版
# e=0: 1/4
# e=1: 線形重み → 総和で正規化
def C_SP_press_linear(sp_i, e):
    easy_prob = 1 / 4

    all_weights = [linear_weight_from_rank(sp, 3) for sp in Strings.keys()]
    expression_prob = normalize_weight(linear_weight_from_rank(sp_i, 3), all_weights)

    prob = easy_prob * (1 - e) + expression_prob * e
    return safe_neg_log(prob)


def C_SP_press(sp_i, e):
    if COST_MODE == "linear":
        return C_SP_press_linear(sp_i, e)
    return C_SP_press_normal(sp_i, e)


# 式(9) ===============================================================================================
# FN押弦：正規分布版
def C_FN_press_normal(fn_i, e, k2=5, sigma2_4=3):
    # e=0: FN=0が最も容易、1,2,3が次、4が難しい
    x1 = {0: 0, 1: 1, 2: 1, 3: 1, 4: 2}

    # e=1: ビブラートをかけやすい順 3,2,1,4,0
    x2 = {3: 0, 2: 1, 1: 2, 4: 3, 0: 4}

    easy_part = ((2 * k2 + (1 - k2) * x1[fn_i]) / (3 * (k2 + 1))) * (1 - e)

    denom = 0.0
    for fn_p in Fingers:
        denom += normal_pdf(x2[fn_p], 0, sigma2_4)

    expression_part = (normal_pdf(x2[fn_i], 0, sigma2_4) / denom) * e

    prob = easy_part + expression_part
    return safe_neg_log(prob)


# 式(9) 線形重み版
# e=0側・e=1側をそれぞれ線形重みで作り、総和で正規化する
def C_FN_press_linear(fn_i, e):
    # e=0: 初心者の押さえやすさ。0が最良、1/2/3が中間、4が最悪。
    x1 = {0: 0, 1: 1, 2: 1, 3: 1, 4: 2}

    # e=1: 表現しやすさ。3,2,1,4,0の順。
    x2 = {3: 0, 2: 1, 1: 2, 4: 3, 0: 4}

    easy_weights = [linear_weight_from_rank(x1[fn], 2) for fn in Fingers]
    easy_prob = normalize_weight(linear_weight_from_rank(x1[fn_i], 2), easy_weights)

    expression_weights = [linear_weight_from_rank(x2[fn], 4) for fn in Fingers]
    expression_prob = normalize_weight(linear_weight_from_rank(x2[fn_i], 4), expression_weights)

    prob = easy_prob * (1 - e) + expression_prob * e
    return safe_neg_log(prob)


def C_FN_press(fn_i, e):
    if COST_MODE == "linear":
        return C_FN_press_linear(fn_i, e)
    return C_FN_press_normal(fn_i, e)


# 式(10) ==============================================================================================
# HP押弦：正規分布版
HP_ORDER = [1, 0, 4, 2, 3] + list(range(5, 24))
HP_RANK = {hp: rank for rank, hp in enumerate(HP_ORDER)}


def C_HP_press_normal(hp_i, sigma2_5=7):
    x = HP_RANK[hp_i]

    denom = 0.0
    for hp_p in range(24):
        xp = HP_RANK[hp_p]
        denom += normal_pdf(xp, 0, sigma2_5)

    prob = normal_pdf(x, 0, sigma2_5) / denom
    return safe_neg_log(prob)


# 式(10) 線形重み版
# HPの好ましい順位を線形重みにし、総和で正規化する
def C_HP_press_linear(hp_i):
    rank = HP_RANK[hp_i]
    all_weights = [linear_weight_from_rank(HP_RANK[hp], 23) for hp in range(24)]

    prob = normalize_weight(linear_weight_from_rank(rank, 23), all_weights)
    return safe_neg_log(prob)


def C_HP_press(hp_i):
    if COST_MODE == "linear":
        return C_HP_press_linear(hp_i)
    return C_HP_press_normal(hp_i)


# 式(11) ==============================================================================================
# FI押弦：ここは元から正規分布ではないため、そのまま
def C_FI_press(fi_i, k3=3):
    half_count = fi_i.count(1)

    if half_count == 0 or half_count == 1:
        x = 0
    elif half_count == 2:
        x = 1
    else:
        x = 2

    prob = (2 * k3 + (1 - k3) * x) / (3 * (k3 + 1))
    return safe_neg_log(prob)


# 式(12) ==============================================================================================
# 動的計画法
def estimate_fingering(pitches, note_lengths, L):
    if len(pitches) != len(note_lengths):
        raise ValueError("pitches と note_lengths の長さが一致していません")

    all_states = [generate_states(pitch) for pitch in pitches]

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

    # 最後の音で最小コストの状態を探す
    last_state = min(dp[-1], key=dp[-1].get)

    # 後ろからたどって状態列を復元
    best_path = [last_state]

    for n in range(N - 1, 0, -1):
        last_state = back[n][last_state]
        best_path.append(last_state)

    best_path.reverse()
    return best_path


# MusicXML読み込み関数 =================================================================================
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
        # 単音の場合
        if isinstance(element, note.Note):
            pitches.append(element.pitch.midi)
            note_lengths.append(float(element.quarterLength) * seconds_per_quarter)

        # 和音の場合 → 一番高い音だけ
        elif isinstance(element, chord.Chord):
            highest_note = element.pitches[-1]
            pitches.append(highest_note.midi)
            note_lengths.append(float(element.quarterLength) * seconds_per_quarter)

    print("BPM:", bpm)

    return pitches, note_lengths


# 結果表示関数 =========================================================================================
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
            f"{string_name[state.sp]},"
            f"{finger_names[state.fn]},"
            f"HP = {state.hp},"
            f"FI = {state.fi}"
        )


# 簡単な集計表示 =======================================================================================
def print_summary(best_path):
    string_counts = {"G": 0, "D": 0, "A": 0, "E": 0}
    finger_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    total_hp_move = 0
    total_sp_move = 0

    for i, state in enumerate(best_path):
        string_counts[Strings[state.sp][0]] += 1
        finger_counts[state.fn] += 1

        if i > 0:
            prev = best_path[i - 1]
            total_hp_move += abs(prev.hp - state.hp)
            total_sp_move += abs(prev.sp - state.sp)

    print("\n--- summary ---")
    print("弦の使用回数:", string_counts)
    print("指の使用回数:", finger_counts)
    print("弦移動量合計:", total_sp_move)
    print("HP移動量合計:", total_hp_move)


# 比較表確認用 =========================================================================================
def print_linear_probability_tables():
    """
    線形評価がどのような確率に正規化されるか確認するための表。
    推定には必須ではないが、発表用の確認に使える。
    """
    print("\n--- linear probability tables ---")

    print("\nSP transition / SP press e=1")
    weights = [linear_weight_from_rank(x, 3) for x in range(4)]
    for x in range(4):
        print(f"x={x}: {normalize_weight(linear_weight_from_rank(x, 3), weights):.3f}")

    print("\nFN press e=1")
    x2 = {3: 0, 2: 1, 1: 2, 4: 3, 0: 4}
    weights = [linear_weight_from_rank(x2[fn], 4) for fn in Fingers]
    for fn in [3, 2, 1, 4, 0]:
        print(f"fn={fn}: {normalize_weight(linear_weight_from_rank(x2[fn], 4), weights):.3f}")

    print("\nHP press")
    weights = [linear_weight_from_rank(HP_RANK[hp], 23) for hp in range(24)]
    for rank in [0, 1, 2, 3, 4, 5, 10, 15, 20, 23]:
        print(f"rank={rank}: {normalize_weight(linear_weight_from_rank(rank, 23), weights):.3f}")


# 実行部分 =============================================================================================
def run_estimation_for_mode(mode, pitches, note_lengths):
    """指定した評価方式で Beginner / Intermediate の運指を推定して表示する。"""
    global COST_MODE
    COST_MODE = mode

    print(f"\n===== {COST_MODE.upper()} =====")

    # 初心者
    print("\nBeginner")
    L_easy = math.inf
    best_path_easy = estimate_fingering(pitches, note_lengths, L_easy)
    print_result(best_path_easy)
    print_summary(best_path_easy)

    # 中級者
    print("\nIntermediate")
    L_mid = 0.1
    best_path_mid = estimate_fingering(pitches, note_lengths, L_mid)
    print_result(best_path_mid)
    print_summary(best_path_mid)


def select_cost_mode():
    """実行時に normal / linear / both を選択する。"""
    print("評価方式を選択してください")
    print("1 : normal（正規分布版：正規分布値→総和で正規化→-log）")
    print("2 : linear（線形重み版：線形重み→総和で正規化→-log）")
    print("3 : both（normal と linear の両方を実行）")

    mode_input = input("選択: ").strip().lower()

    if mode_input in ["1", "normal", "n"]:
        return "normal"
    if mode_input in ["2", "linear", "l"]:
        return "linear"
    if mode_input in ["3", "both", "b"]:
        return "both"

    raise ValueError("評価方式は 1/2/3 または normal/linear/both で入力してください")


if __name__ == "__main__":
    selected_mode = select_cost_mode()

    xml_path = input("MusicXML_path:")

    pitches, note_lengths = load_musicxml(xml_path)

    print("pitch:", pitches)
    print("note_lengths:", note_lengths)

    if selected_mode == "both":
        run_estimation_for_mode("normal", pitches, note_lengths)
        run_estimation_for_mode("linear", pitches, note_lengths)
    else:
        run_estimation_for_mode(selected_mode, pitches, note_lengths)


"""
使い方:
実行すると、最初に評価方式を選択できます。

1 または normal : 元の正規分布版で実行
2 または linear : 線形重み版で実行
3 または both   : normal と linear の両方を同じMusicXMLで実行

今回のlinear版:
- 正規分布版と比較しやすいように、形式をそろえています。
- 正規分布版:
    正規分布値 → 総和で正規化 → -log(prob)
- 線形重み版:
    線形重み → 総和で正規化 → -log(prob)

注意:
- 「値が大きいほど好ましい」という評価値を作ったあと、
  DPでは最小化する必要があるため、最後に -log(prob) でコストへ変換しています。
- 式(6) FI transition と式(11) FI press は、元から正規分布ではない式なので、
  論文式のまま残しています。
"""
