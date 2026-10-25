# =========================
# 2音間の指の形コスト
# =========================

def double_finger_shape_cost(
        low_state,
        high_state,
        pitch_low,
        pitch_high
):
    interval = pitch_high - pitch_low
    fingers = (low_state.fn, high_state.fn)

    # 開放弦を含む場合は、指の形コストをかけない
    if low_state.fn == 0 or high_state.fn == 0:
        return 0.0

    # 3度：1-3、2-4
    if interval in [3, 4]:
        if fingers in [(1, 3), (2, 4)]:
            return 0.0

        return 4.0

    # 5度：同じ指
    if interval == 7:
        if low_state.fn == high_state.fn:
            return 0.0

        return 4.0

    # 6度：1-2、2-3、3-4
    if interval in [8, 9]:
        if fingers in [
            (1, 2),
            (2, 3),
            (3, 4)
        ]:
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
# 2～4重音の指の形コスト
# =========================

def multiple_finger_shape_cost(
        music_state,
        event
):
    states = music_state.states

    if len(states) != len(event):
        raise ValueError(
            "MusicStateのState数とeventの音数が一致していません。"
        )

    cost = 0.0

    # 隣り合う弦の2音ずつ評価する
    for i in range(len(states) - 1):
        cost += double_finger_shape_cost(
            states[i],
            states[i + 1],
            event[i],
            event[i + 1]
        )

    return cost


# =========================
# 2～4重音専用の押弦コスト
# =========================

def multiple_pressing_cost(
        music_state,
        event,
        e,
        C_HP_press,
        C_FI_press
):
    note_count = music_state.note_count()

    if note_count < 2 or note_count > 4:
        raise ValueError(
            "multiple_pressing_costには"
            "二重音・三重音・四重音のMusicStateを渡してください。"
        )

    if note_count != len(event):
        raise ValueError(
            "MusicStateのState数とeventの音数が一致していません。"
        )

    states = music_state.states
    cost = 0.0

    # ① 隣り合う音同士の指の形を評価
    cost += multiple_finger_shape_cost(
        music_state,
        event
    )

    # ② 開放弦を含む場合は弾きやすい
    if any(state.fn == 0 for state in states):
        cost += 0.0
    else:
        cost += 1.0

    # ③ 小指を含む場合は少し難しい
    if any(state.fn == 4 for state in states):
        cost += 1.0

    # 開放弦以外のStateを取得する
    pressed_states = [
        state
        for state in states
        if state.fn != 0
    ]

    # ④ 押弦している音のHPを評価する
    if pressed_states:
        cost += C_HP_press(
            pressed_states[0].hp
        )

    # ⑤ 開放弦以外のFI押弦コストを加える
    for state in pressed_states:
        cost += C_FI_press(state.fi)

    return cost


# =========================
# 単音・2～4重音の押弦コスト
# =========================

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

        return single_pressing_cost_func(
            state,
            pitch,
            e
        )

    if (
        music_state.is_double()
        or music_state.is_triple()
        or music_state.is_quadruple()
    ):
        return multiple_pressing_cost(
            music_state,
            event,
            e,
            C_HP_press,
            C_FI_press
        )

    raise ValueError(
        "1音から4音までのMusicStateに対応しています。"
    )


# =========================
# MusicState用の遷移コスト（仮）
# =========================

def music_state_transition_cost(
        prev_music_state,
        next_music_state,
        single_transition_cost_func
):
    # 前のイベントで押弦しているState
    prev_pressed_states = [
        state
        for state in prev_music_state.states
        if state.fn != 0
    ]

    # 次のイベントで押弦しているState
    next_pressed_states = [
        state
        for state in next_music_state.states
        if state.fn != 0
    ]

    # どちらかが開放弦だけの場合、
    # 左手のポジション遷移は評価しない
    if not prev_pressed_states or not next_pressed_states:
        return 0.0

    # 同一重音内ではHPとFIを統一しているため、
    # 最初の押弦Stateを手全体の代表として使用する
    prev_representative = prev_pressed_states[0]
    next_representative = next_pressed_states[0]

    return single_transition_cost_func(
        prev_representative,
        next_representative
    )

    return cost