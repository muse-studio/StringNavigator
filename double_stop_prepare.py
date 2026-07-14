# =========================
# 重音の指の形コスト
# =========================

def double_finger_shape_cost(low_state, high_state, pitch_low, pitch_high):
    interval = pitch_high - pitch_low
    fingers = (low_state.fn, high_state.fn)

    # 開放弦を含む場合は、指の形コストはかけない
    if low_state.fn == 0 or high_state.fn == 0:
        return 0.0

    # 3度：1-3, 2-4
    if interval in [3, 4]:
        if fingers in [(1, 3), (2, 4)]:
            return 0.0
        return 4.0

    # 5度：同じ指
    if interval == 7:
        if low_state.fn == high_state.fn:
            return 0.0
        return 4.0

    # 6度：1-2, 2-3, 3-4
    if interval in [8, 9]:
        if fingers in [(1, 2), (2, 3), (3, 4)]:
            return 0.0
        return 4.0

    # オクターブ：1-4
    if interval == 12:
        if fingers == (1, 4):
            return 0.0
        return 6.0

    # それ以外の音程はいったん弱く評価
    return 1.0


# =========================
# 重音専用 押弦コスト
# =========================

def double_pressing_cost(
        music_state,
        event,
        e,
        C_HP_press,
        C_FI_press
):
    if not music_state.is_double():
        raise ValueError("double_pressing_cost には二重音 MusicState を渡してください。")

    low_state, high_state = music_state.states

    cost = 0.0

    # ① 重音として自然な指の形か
    cost += double_finger_shape_cost(
        low_state,
        high_state,
        event[0],
        event[1]
    )

    # ② 開放弦を含む場合は弾きやすい
    if low_state.fn == 0 or high_state.fn == 0:
        cost += 0.0
    else:
        cost += 1.0

    # ③ 小指を含む場合は少し難しい
    if low_state.fn == 4 or high_state.fn == 4:
        cost += 1.0

    # ④ HPはローポジション優先
    cost += C_HP_press(low_state.hp)

    # ⑤ FIはいったん先行研究の FI 押弦コストを利用
    cost += C_FI_press(low_state.fi)
    cost += C_FI_press(high_state.fi)

    return cost


def music_state_pressing_cost(
        music_state,
        event,
        e,
        single_pressing_cost_func,
        C_HP_press,
        C_FI_press
):
    if music_state.is_single():
        state = music_state.states[0]
        pitch = event[0]
        return single_pressing_cost_func(state, pitch, e)

    if music_state.is_double():
        return double_pressing_cost(
            music_state,
            event,
            e,
            C_HP_press,
            C_FI_press
        )

    raise ValueError("単音と二重音のみ対応しています。")


# =========================
# MusicState 用 遷移コスト（仮）
# =========================

def music_state_transition_cost(
        prev_music_state,
        next_music_state,
        single_transition_cost_func
):
    cost = 0.0

    for prev_state in prev_music_state.states:
        for next_state in next_music_state.states:
            cost += single_transition_cost_func(prev_state, next_state)

    return cost