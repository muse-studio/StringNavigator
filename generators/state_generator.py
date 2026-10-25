from functools import lru_cache
from itertools import product

from models.state import MusicState, State


Strings = {
    0: ("G", 55),
    1: ("D", 62),
    2: ("A", 69),
    3: ("E", 76),
}

Fingers = [0, 1, 2, 3, 4]

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


def finger_offset(fn, fi):
    """
    指番号とFIから、1指を基準にした半音数の差を求める。
    """
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

    raise ValueError(
        f"対応していない指番号です: fn={fn}"
    )


def generate_states(pitch):
    """
    1つのMIDIピッチから、演奏可能なState候補を生成する。
    """
    states = []

    for sp, (_, open_pitch) in Strings.items():
        semitone = pitch - open_pitch

        if semitone < 0:
            continue

        for fi in FI_PATTERNS:
            for fn in Fingers:

                # 開放弦の場合
                if fn == 0:
                    if semitone == 0:
                        states.append(
                            State(
                                sp=sp,
                                fn=fn,
                                hp=0,
                                fi=fi
                            )
                        )

                    continue

                # 押弦の場合
                offset = finger_offset(fn, fi)
                hp = semitone - offset - 1

                # 有効なポジションの場合だけ追加する
                if 0 <= hp < 24:
                    states.append(
                        State(
                            sp=sp,
                            fn=fn,
                            hp=hp,
                            fi=fi
                        )
                    )

    return tuple(states)

@lru_cache(maxsize=None)
def generate_states_cached(pitch):
    """
    generate_statesの結果をキャッシュする。
    """
    return generate_states(pitch)


def generate_single_music_states(
        pitch,
        generate_states_func
):
    """
    単音のState候補をMusicStateとしてまとめる。
    """
    return tuple(
        MusicState((state,))
        for state in generate_states_func(pitch)
    )


def is_valid_multiple_state_combination(states):
    """
    二重音・三重音・四重音のStateが演奏可能か判定する。
    """

    string_numbers = [
        state.sp
        for state in states
    ]

    # 同じ弦で複数の音は演奏できない
    if len(set(string_numbers)) != len(string_numbers):
        return False

    # 低い音から高い音へG-D-A-Eの順にする
    if string_numbers != sorted(string_numbers):
        return False

    # 使用する弦が隣り合っていること
    for i in range(len(string_numbers) - 1):
        if string_numbers[i + 1] - string_numbers[i] != 1:
            return False

    # 同じポジションで演奏する
    # 開放弦以外のHPを取得する
    pressed_positions = {
        state.hp
        for state in states
        if state.fn != 0
    }

    # 押弦している音同士は同じポジションにする
    if len(pressed_positions) > 1:
        return False

    # 開放弦以外のFIを取得する
    pressed_fi_patterns = {
        state.fi
        for state in states
        if state.fn != 0
    }

    # 押弦している音同士では同じFIを使用する
    if len(pressed_fi_patterns) > 1:
        return False

    return True



def generate_multiple_music_states(
        pitches,
        generate_states_func
):

    """
    二重音・三重音・四重音が演奏できるMusicState候補を生成する
    """

    state_groups = [
        generate_states_func(pitch)
        for pitch in pitches
    ]

    music_states = []

    for states in product(*state_groups):
        if not is_valid_multiple_state_combination(states):
            continue

        music_states.append(
            MusicState(tuple(states))
        )

    return tuple(music_states)



def generate_double_music_states(
        pitch_low,
        pitch_high,
        generate_states_func
):

    """
    二重音を演奏可能なMusicState候補を生成する
    """
    return generate_multiple_music_states(
        (pitch_low, pitch_high),
        generate_states_func
    )


def generate_triple_music_states(
        pitch_low,
        pitch_middle,
        pitch_high,
        generate_states_func
):

    """
    三重音を演奏可能なMusicState候補を生成する
    """
    return generate_multiple_music_states(
        (
        pitch_low,
        pitch_middle,
        pitch_high
        ),
        generate_states_func
    )

def generate_quadruple_music_states(
        pitch_1,
        pitch_2,
        pitch_3,
        pitch_4,
        generate_states_func
):
    """
    四重音を演奏可能なMusicState候補を生成する
    """
    return generate_multiple_music_states(
        (
            pitch_1,
            pitch_2,
            pitch_3,
            pitch_4,
        ),
        generate_states_func
    )

def generate_event_music_states(
        event,
        generate_states_func=generate_states_cached
):

    """
    単音・二重音・三重音・四重音のイベントから
    MusicState候補を生成する。

    eventの例:
        単音:   [69]
        二重音: [62, 69]
        三重音: [55, 62, 69]
        四重音: [55, 62, 69, 76]
    """

    if len(event) == 1:
        return generate_single_music_states(
            event[0],
            generate_states_func
        )

    if len(event) == 2:
        return generate_double_music_states(
            event[0],
            event[1],
            generate_states_func
        )

    if len(event) == 3:
        return generate_triple_music_states(
            event[0],
            event[1],
            event[2],
            generate_states_func
        )

    if len(event) == 4:
        return generate_quadruple_music_states(
            event[0],
            event[1],
            event[2],
            event[3],
            generate_states_func
        )

    raise ValueError(
        "１～４音に対応。"
    )



if __name__ == "__main__":
    test_events = [
        [69],
        [62, 69],
        [55, 62, 69],
        [55, 62, 69, 76],

        # 2声で同じ音が同時に鳴るケース
        [69, 69],
    ]

    for event in test_events:
        candidates = generate_event_music_states(event)

        print(f"\nevent={event}")
        print(f"音数={len(event)}")
        print(f"候補数={len(candidates)}")

        if candidates:
            print("候補を最大10個表示:")

            for candidate in candidates[:10]:
                print(candidate)