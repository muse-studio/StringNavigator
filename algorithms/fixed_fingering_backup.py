
def filter_music_states_by_fixed_fingers(
    music_states,
    pitches,
    fixed_fingers
):
    """
    固定指番号に一致するMusicState候補だけを残す。

    music_states: MusicState候補のリストまたはタプル
    pitches: イベントのMIDI音高リスト
    fixed_fingers: {MIDI音高: 指番号}
    """

    if len(pitches) != len(set(pitches)):
        raise ValueError(
            "同一イベント内に重複する音高があります。"
            "音符IDによる識別が必要です。"
        )

    filtered = []

    for music_state in music_states:
        if all(
            music_state.states[i].fn == fixed_fingers[pitch]
            for i, pitch in enumerate(pitches)
            if pitch in fixed_fingers
        ):
            filtered.append(music_state)

    return filtered



def build_fixed_fingers_by_event(timeline_events, edits):
    """
    JSONの修正情報をイベント別の固定指番号に変換する。

    戻り値:
        [{MIDI音高: 指番号}, ...]
    """
    fixed_by_event = [
        {} for _ in timeline_events
    ]

    for edit in edits:
        offset = float(edit["offset"])
        midi = int(edit["midi"])
        finger = int(edit["fingering"])

        if finger not in range(5):
            raise ValueError(f"不正な指番号: {finger}")

        matches = []

        for i, event in enumerate(timeline_events):
            for item in event["items"]:
                if (
                    abs(float(item["start"]) - offset) < 1e-6
                    and int(item["pitch"]) == midi
                ):
                    matches.append(i)

        if len(matches) != 1:
            raise ValueError(
                f"修正対象を一意に特定できません: "
                f"offset={offset}, midi={midi}, "
                f"一致数={len(matches)}"
            )

        event_index = matches[0]

        existing = fixed_by_event[event_index].get(midi)
        if existing is not None and existing != finger:
            raise ValueError(
                f"固定指番号が競合しています: "
                f"event={event_index}, midi={midi}"
            )

        fixed_by_event[event_index][midi] = finger

    return fixed_by_event
