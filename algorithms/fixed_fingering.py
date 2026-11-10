
def filter_music_states_by_fixed_fingers(
    music_states,
    pitches,
    fixed_fingers
):
    """
    固定指番号に一致するMusicState候補だけを残す。

    fixed_fingers:
        {イベント内の音符インデックス: 指番号}
    """

    filtered = []

    for music_state in music_states:
        if all(
            music_state.states[i].fn == finger
            for i, finger in fixed_fingers.items()
        ):
            filtered.append(music_state)

    return filtered



def build_fixed_fingers_by_event(timeline_events, edits):
    """
    編集した指番号をイベントごとの固定条件に変換する。

    戻り値:
        [{イベント内の音符インデックス: 指番号}, ...]
    """
    fixed_by_event = [{} for _ in timeline_events]

    for edit in edits:
        offset = float(edit["offset"])
        midi = int(edit["midi"])
        finger = int(edit["fingering"])

        if finger not in range(5):
            raise ValueError(f"不正な指番号: {finger}")

        # 元の音符をsource_idで識別する
        matching_source_ids = set()

        for event in timeline_events:
            for item in event["items"]:
                if (
                    abs(float(item["start"]) - offset) < 1e-6
                    and int(item["pitch"]) == midi
                ):
                    matching_source_ids.add(item["source_id"])

        if len(matching_source_ids) != 1:
            raise ValueError(
                "修正対象の音符を一意に特定できません: "
                f"offset={offset}, midi={midi}, "
                f"source_id数={len(matching_source_ids)}"
            )

        source_id = next(iter(matching_source_ids))

        # 同じ音符が継続する全イベントに固定条件を設定
        for event_index, event in enumerate(timeline_events):
            for note_index, item in enumerate(event["items"]):
                if item["source_id"] != source_id:
                    continue

                existing = fixed_by_event[event_index].get(note_index)

                if existing is not None and existing != finger:
                    raise ValueError(
                        "固定指番号が競合しています: "
                        f"event={event_index}, "
                        f"note_index={note_index}"
                    )

                fixed_by_event[event_index][note_index] = finger

    return fixed_by_event
