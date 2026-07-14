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


def generate_double_music_states(
        pitch_low,
        pitch_high,
        generate_states_func
):
    """
    二重音を演奏可能なMusicState候補を生成する。
    """
    low_states = generate_states_func(pitch_low)
    high_states = generate_states_func(pitch_high)

    music_states = []

    for low_state, high_state in product(
        low_states,
        high_states
    ):
        # 同じ弦は使用できない
        if low_state.sp == high_state.sp:
            continue

        # 低音は低い弦、高音は高い弦で演奏する
        if low_state.sp >= high_state.sp:
            continue

        # 二重音は同じポジションで演奏する
        if low_state.hp != high_state.hp:
            continue

        music_states.append(
            MusicState(
                (
                    low_state,
                    high_state
                )
            )
        )

    return tuple(music_states)


def generate_event_music_states(
        event,
        generate_states_func=generate_states_cached
):
    """
    単音または二重音のイベントからMusicState候補を生成する。

    eventの例:
        単音: [69]
        二重音: [62, 69]
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

    raise ValueError(
        "今は単音と二重音のみ対応しています。"
    )