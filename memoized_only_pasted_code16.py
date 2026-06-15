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

# FI    1=半音、2=全音
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


@dataclass(frozen = True)
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


# s：状態
# s = {sp, fn, hp, fi}
def generate_states(pitch):
    states = []

    for sp, (string_name, open_pitch) in Strings.items():       #semitone:半音
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

                # 開放弦のすぐ上の音は1の指で取る
 #               if semitone in [1, 2] and fn != 1:
 #                   continue

                if 0 <= hp < 24:
                    states.append(State(sp, fn, hp, fi))

    return states


# generate_states(pitch) の結果を保存して再利用する
# 元の generate_states() 自体は変更しない
@lru_cache(maxsize=None)
def generate_states_cached(pitch):
    return generate_states(pitch)



# 確率密度関数(Probability density function) ===========================================================
# 正規分布(normal distribution)
def normal_pdf(x, mu, sigma2):  # sigma2はグリッドサーチによって決定
    return (1 / math.sqrt(2 * math.pi * sigma2)) * math.exp(-((x - mu) ** 2) / (2 * sigma2))

# 式(4) ===============================================================================================
# 弦の移動幅
def C_SP_transition(sp_i, sp_j, sigma2_1 = 0.1):
    x = abs(sp_i - sp_j)  # x(SPi, Spj) = |SPi - SPj|

    denom = 0.0  # 分母(Denominator)の初期化
    for sp_p in Strings.keys():
        for sp_q in Strings.keys():
            xpq = abs(sp_p - sp_q)
            denom += normal_pdf(xpq, 0, sigma2_1)

    prob = normal_pdf(x, 0, sigma2_1) / denom # prob＝確率(probability)
    return -math.log(prob)

# 式(5) ===============================================================================================
# 手の移動幅
def C_HP_transition(hp_i, hp_j, sigma2_2 = 1):
    x = abs(hp_i - hp_j)

    denom = 0.0
    for hp_p in range(24):
        for hp_q in range(24):
            xpq = abs(hp_p - hp_q)
            denom += normal_pdf(xpq, 0, sigma2_2)

    prob = normal_pdf(x, 0, sigma2_2) / denom
    return -math.log(prob)

# 式(6) ===============================================================================================
# 指の間隔
def C_FI_transition(fi_i, fi_j, k1 = 3):     # k1はグリッドサーチによって決定
    
    if fi_i == fi_j:
        x = 0
    else:
        x = 1
    
    prob = (k1 + (1 - k1) * x) / (k1 + 1)
    return -math.log(prob)


# 式(3) ===============================================================================================
# 遷移コストの定義
@lru_cache(maxsize=None)
def transition_cost(state_i, state_j):
    cost_sp = C_SP_transition(state_i.sp, state_j.sp)
    cost_hp = C_HP_transition(state_i.hp, state_j.hp)
    cost_fi = C_FI_transition(state_i.fi, state_j.fi)
    return cost_sp + cost_hp + cost_fi



# 式(7) ===============================================================================================
# 押弦コストの定義
@lru_cache(maxsize=None)
def pressing_cost(state_i, pitch, e):
    if not is_valid_state(state_i, pitch):    # 有効な状態でなければ無限大コスト
        return float('inf')
    
    return(                                 # 有効なら各コストを計算
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
    
    # 開放弦のすぐ上の音は1の指
#    if semitone in [1, 2] and fn != 1:
#        return False
    
    return semitone == hp + finger_offset(fn, fi) + 1
    

# 式(8) ===============================================================================================
# SP eが小さいほどe=0、大きいほどe=1のコストに近づく
def C_SP_press(sp_i, e, sigma2_3 = 1):

    denom = 0.0
    for sp_p in Strings.keys():
        denom += normal_pdf(sp_p, 0, sigma2_3)

    # e = 0に近いとき弦に依存しない→1/4
    easy_part = (1 / 4) * (1 - e)

    # e = 1に近いとき太い弦の方が好まれる
    expression_part = (normal_pdf(sp_i, 0, sigma2_3) / denom) * e

    prob = easy_part + expression_part
    return -math.log(prob)


# 式(9) ===============================================================================================
# FN FN=4(小指)は難しく、0(開放)は容易

def C_FN_press(fn_i, e, k2 = 3, sigma2_4 = 5):
    
    # FN = 0のときx1(FN) = 0, FN = 1,2,3のときx1(FN) = 1, FN = 4のときx1(FN) = 2
    # e = 0においてx1(FN)が大きくなるほどコストが大きくなるように
    x1 = {0:0, 1:1, 2:1, 3:1, 4:2}
    
    #FN = 3,2,1,4,0がビブラートをかけやすい順 x2(FN) = 0,1,2,3,4
    #e = 1においてx2(FN)が大キックなるほどコストが大きくなるように
    x2 = {3:0, 2:1, 1:2, 4:3, 0:4}

    # e = 0
    easy_part = ((2 * k2 + (1 - k2) * x1[fn_i]) / (3 * (k2 + 1))) * (1 - e)

    # e = 1
    denom = 0.0
    for fn_p in Fingers:
        denom += normal_pdf(x2[fn_p], 0, sigma2_4)
    
    expression_part = (normal_pdf(x2[fn_i], 0, sigma2_4) / denom) * e

    prob = easy_part + expression_part
    
    return -math.log(prob)


# 式(10) ==============================================================================================
# HP 適切な順HP=1,0,4,2,3,5,6…
def C_HP_press(hp_i, sigma2_5 = 7):
    hp_order = [1, 0, 4, 2, 3] + list(range(5, 24))

    #x(HP) ex.HP=1はx=0,HP=0はx=1,HP=4はx=2
    #x(HP)はコスト
    hp_rank = {}
    for rank, hp in enumerate(hp_order):    # enumerate=列挙
        hp_rank[hp] = rank

    x = hp_rank[hp_i]

    denom = 0.0
    for hp_p in range(24):
        xp = hp_rank[hp_p]
        denom += normal_pdf(xp, 0, sigma2_5)

    prob = normal_pdf(x, 0, sigma2_5) / denom
    return -math.log(prob)


# 式(11) ==============================================================================================
# FI
def C_FI_press(fi_i, k3 = 3):
    half_count = fi_i.count(1)

    if half_count == 0 or half_count == 1:
        x = 0
    elif half_count == 2:
        x = 1
    else:
        x = 2

    prob = (2 * k3 + (1 - k3) * x) / (3 * (k3 + 1))
    return -math.log(prob)


# 式(12) ==============================================================================================
# 動的計画法

def estimate_fingering(pitches, note_lengths, L):
    if len(pitches) != len(note_lengths):
        raise ValueError("pitches と note_lengths の長さが一致していません")

    all_states = [generate_states_cached(pitch) for pitch in pitches]

    for i, states in enumerate(all_states):
        if len(states) == 0:
            raise ValueError(f"{i}番目の音で有効な状態がありません")

    N = len (pitches)   # N:音の個数

    dp = []     # 各状態の最小コストを保存
    back = []   # どこから来たか記録(前の状態を記録し経路を保存)
    
    # １音目
    first_dp = {}
    first_back = {}
    
    e0 = expression_degree(note_lengths[0], L)

    for state in all_states[0]:     # 最初の音の全ての弾き方を見る
        first_dp[state] = pressing_cost(state, pitches[0], e0)  # 最初の音の弾き方の押弦コスト
        first_back[state] = None    # どこから来たのかは最初の音なのでなし

    dp.append(first_dp)
    back.append(first_back)

    # ２音目以降
    for n in range(1, N):
        e = expression_degree(note_lengths[n], L)

        current_dp = {}     # 現在の音の点数
        current_back = {}   # どこから来たか

        for state_j in all_states[n]:   # 今の音を弾くためにどのルートのコストが一番低いかを調べる
            best_cost = math.inf        # 一番良い状態のときの点数(仮置き)
            best_prev = None            # best_costの点数を出したひとつ前の状態

            for state_i in all_states[n - 1]:   # state_i=ひとつ前の音
                cost = (
                    dp[n - 1][state_i]      # state_iになるまでの最小コスト
                    + transition_cost(state_i, state_j)     # 遷移コスト
                    + pressing_cost(state_j, pitches[n], e) # 押弦コスト
                )
            
                if cost < best_cost:
                    best_cost = cost
                    best_prev = state_i

            current_dp[state_j] = best_cost     # 現在の状態に来る最小コスト
            current_back[state_j] = best_prev   # その時の一つ前の状態

        dp.append(current_dp)       # 音の結果を保存(すべての運指候補とその最小コスト一覧)
        back.append(current_back)   # 経路を保存

    # 最後の音で最小コストの状態を探す
    last_state = min(dp[-1], key = dp[-1].get)      # コストが一番小さい状態を返す

    # 後ろからたどって状態列を復元
    best_path = [last_state]    # 最後の状態

    for n in range(N - 1, 0, -1):           # N-1:最後の音のインデックス　0:最初の音はループ処理されない -1:一つずつ戻る
        last_state = back[n][last_state]    # 前の状態に戻る
        best_path.append(last_state)        # 追加

    best_path.reverse()     # 順番が逆で保存されているので反対に
    return best_path        # 最適な運指列を返す




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
    note_length = []

    for element in score.flatten().notes:
        # 単音の場合
        if isinstance(element, note.Note):
            pitches.append(element.pitch.midi)
            note_length.append(float(element.quarterLength) * seconds_per_quarter)

        # 和音の場合→一番高い音だけ
        elif isinstance(element, chord.Chord):
            highest_note = element.pitches[-1]
            pitches.append(highest_note.midi)
            note_length.append(float(element.quarterLength) * seconds_per_quarter)

    print("BPM:", bpm)

    return pitches, note_length


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



# 実行部分 =============================================================================================

if __name__ == "__main__":
    xml_path = input("MusicXML_path:")

    pitches, note_lengths = load_musicxml(xml_path)

    print("pitch:", pitches)
    print("note_lengths:", note_lengths)

    # 初心者
    print("\nBeginner")
    L_easy = math.inf
    best_path_easy = estimate_fingering(pitches, note_lengths, L_easy)
    print_result(best_path_easy)

    #中級者
    print("\nIntermediate")
    L_mid = 0.1
    best_path_mid = estimate_fingering(pitches, note_lengths, L_mid)
    print_result(best_path_mid)

    # メモ化が効いているか確認するための表示
    print("\n--- cache info ---")
    print("generate_states_cached:", generate_states_cached.cache_info())
    print("transition_cost:", transition_cost.cache_info())
    print("pressing_cost:", pressing_cost.cache_info())


'''
    for s in generate_states(pitches[0]):
        print(s.fi)
'''        