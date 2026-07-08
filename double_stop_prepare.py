# double_stop_prepare.py

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class MusicState:
    states: tuple

    def is_single(self):
        return len(self.states) == 1

    def is_double_stop(self):
        return len(self.states) == 2


def generate_single_music_states(pitch, generate_states_func):
    return tuple(
        MusicState((state,))
        for state in generate_states_func(pitch)
    )


def generate_double_stop_music_states(pitch_low, pitch_high, generate_states_func):
    low_states = generate_states_func(pitch_low)
    high_states = generate_states_func(pitch_high)

    music_states = []

    for low_state, high_state in product(low_states, high_states):

        # 同じ弦は除外
        if low_state.sp == high_state.sp:
            continue

        # 低音は低い弦、高音は高い弦
                # 低音は低い弦、高音は高い弦
        if low_state.sp >= high_state.sp:
            continue

        # 追加条件：
        # 二重音は同じポジションで取る
        if low_state.hp != high_state.hp:
            continue

        music_states.append(MusicState((low_state, high_state)))

    return tuple(music_states)


def generate_event_music_states(event, generate_states_func):
    if len(event) == 1:
        return generate_single_music_states(event[0], generate_states_func)

    if len(event) == 2:
        return generate_double_stop_music_states(
            event[0],
            event[1],
            generate_states_func
        )

    raise ValueError("今は単音と二重音のみ対応しています。")