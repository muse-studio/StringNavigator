export default async function(component) {
    const { data, parentElement, setStateValue } = component;
    const xml = data?.musicxml;

    if (!xml) {
        console.log("MusicXMLはまだ渡されていません");
        return;
    }

    console.log(`MusicXML受信成功（${xml.length}文字）`);

    // OSMDの読み込み完了を待つ
    if (!window.opensheetmusicdisplay) {
        await new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src =
                "https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.9.5/build/opensheetmusicdisplay.min.js";

            script.onload = resolve;
            script.onerror = () => reject(
                new Error("OSMDの読み込みに失敗しました")
            );

            document.head.appendChild(script);
        });
    }

    console.log("OSMDライブラリの読み込み完了");

    // 楽譜表示領域を取得
    const scoreElement = parentElement.querySelector("#score");

    if (!scoreElement) {
        console.error("楽譜表示領域が見つかりません");
        return;
    }

    // OSMDの初期化
    const osmd = new window.opensheetmusicdisplay.OpenSheetMusicDisplay(
        scoreElement,
        {
            autoResize: true,
            backend: "svg"
        }
    );

    // MusicXMLを読み込んで楽譜を表示
    await osmd.load(xml);
    osmd.render();

    // 現在選択している音符
    let selectedSourceNote = null;
    // 現在青色で表示している符頭
    let selectedNotehead = null;
    // 選択した音符の識別情報
    let selectedNoteInfo = null;

    let selectedChordInfo = null;

    // 指番号の修正履歴
    const editedNotes = [];

    // 楽譜上の符頭をクリックしたときの処理
    scoreElement.addEventListener("click", function(event) {

        // クリックされた符頭を取得
        const notehead = event.target.closest(".vf-notehead");

        if (!notehead) {
            return;
        }

        console.log("符頭がクリックされました:", notehead);

        // VexFlowの音符を取得
        const staveNote = notehead.closest(".vf-stavenote");

        if (!staveNote) {
            console.log("VexFlowの音符が見つかりません");
            return;
        }

        // SVGのIDから接頭辞「vf-」を除去
        const vexflowId = staveNote.id.replace(/^vf-/, "");

        console.log("VexFlowの音符ID:", vexflowId);

        // OSMD内部の音符データを検索
        for (const measureRow of osmd.GraphicSheet.measureList) {
            for (const measure of measureRow) {
                if (!measure) continue;

                for (const staffEntry of measure.staffEntries) {
                    for (const voiceEntry of staffEntry.graphicalVoiceEntries) {

                        const vfNote = voiceEntry.mVexFlowStaveNote;

                        // VexFlowのIDが一致する音符を探す
                        if (vfNote?.attrs?.id === vexflowId) {

                            // 重音に含まれる音符と符頭の対応関係を調査
                            console.log("=== 重音の調査 ===");

                            console.log(
                                "重音に含まれる音符数:",
                                voiceEntry.notes.length
                            );

                            voiceEntry.notes.forEach((note, index) => {
                                console.log(
                                    `音符[${index}] MIDI:`,
                                    note.sourceNote?.halfTone + 12
                                );
                            });

                            console.log(
                                "クリックした符頭:",
                                notehead.outerHTML
                            );

                            console.log(
                                "符頭の親要素:",
                                notehead.parentElement?.outerHTML.slice(0, 500)
                            );

                            // 同じ重音に含まれる符頭をすべて取得
                            const noteheads = Array.from(
                                staveNote.querySelectorAll(".vf-notehead")
                            );

                            // 画面上の縦位置を取得して上から順番に並べる
                            const sortedNoteheads = noteheads
                                .map(head => ({
                                    element: head,
                                    y: head.getBoundingClientRect().top +
                                       head.getBoundingClientRect().height / 2
                                }))
                                .sort((a, b) => a.y - b.y);

                            // クリックした符頭が上から何番目か取得
                            const clickedIndex = sortedNoteheads.findIndex(
                                item => item.element === notehead
                            );

                            // OSMD内部の音符を音高の高い順に並べる
                            const sortedNotes = [...voiceEntry.notes].sort(
                                (a, b) =>
                                    b.sourceNote.halfTone - a.sourceNote.halfTone
                            );

                            // 符頭と音符の数が一致するか確認
                            if (
                                clickedIndex < 0 ||
                                sortedNoteheads.length !== sortedNotes.length
                            ) {
                                console.warn("符頭と音符の対応付けに失敗しました");
                                return;
                            }

                            // クリックした符頭に対応する音符を取得
                            const graphicalNote = sortedNotes[clickedIndex];

                            if (!graphicalNote) {
                                return;
                            }

                            console.log(
                                "クリックした符頭のMIDI:",
                                graphicalNote.sourceNote.halfTone + 12
                            );

                            const sourceNote = graphicalNote.sourceNote;

                            // 重音の指番号を高音から低音の順番で取得
                            const fingeringText =
                                voiceEntry.notes
                                    .map(note => note.sourceNote?.Fingering?.value)
                                    .find(value => value !== undefined && value !== null);

                            const fingeringValues = String(fingeringText ?? "")
                                .split(/\r?\n/)
                                .map(value => value.trim());

                            // クリックした音符は高音から低音に並べた配列の何番目か
                            const fingerIndex = sortedNotes.indexOf(graphicalNote);

                            // 対応する変更前の指番号
                            const originalFinger =
                                fingeringValues.length === sortedNotes.length &&
                                fingerIndex >= 0 &&
                                /^[0-4]$/.test(fingeringValues[fingerIndex])
                                    ? Number(fingeringValues[fingerIndex])
                                    : null;

                            console.log(
                                "個別取得した指番号:",
                                sourceNote.halfTone + 12,
                                originalFinger
                            );

                            selectedChordInfo = {
                                notes: sortedNotes,
                                fingers: [...fingeringValues],
                                selectedIndex: fingerIndex
                            };

                            // ==========================================
                            // 変更前の指番号データを調査
                            // ==========================================

                            console.log("=== 指番号データの調査 ===");

                            console.log(
                                "sourceNote.Fingering:",
                                sourceNote.Fingering
                            );

                            console.log(
                                "sourceNote.Fingering.value:",
                                sourceNote.Fingering?.value
                            );

                            console.log(
                                "sourceNote全体:",
                                sourceNote
                            );

                            // ==========================================
                            // 重音に含まれる各音符の指番号を調査
                            // ==========================================

                            console.log("=== 各音符の指番号調査 ===");

                            voiceEntry.notes.forEach((note, index) => {
                                console.log(
                                    `音符[${index}]`,
                                    "MIDI:", note.sourceNote?.halfTone + 12,
                                    "Fingering:", note.sourceNote?.Fingering,
                                    "Fingering.value:",
                                    JSON.stringify(note.sourceNote?.Fingering?.value)
                                );
                            });

                            // ==========================================
                            // 重音の指番号と音高の並び順を調査
                            // ==========================================

                            console.log("=== 重音の指番号対応調査 ===");

                            console.log(
                                "元の音符順:",
                                voiceEntry.notes.map(
                                    note => note.sourceNote.halfTone + 12
                                )
                            );

                            console.log(
                                "高音から低音:",
                                sortedNotes.map(
                                    note => note.sourceNote.halfTone + 12
                                )
                            );

                            console.log(
                                "指番号の配列:",
                                String(
                                    voiceEntry.notes[0].sourceNote.Fingering?.value ?? ""
                                ).split(/\r?\n/)
                            );

                            // 現在選択している音符を記録
                            selectedSourceNote = sourceNote;

                            // 音符の開始位置を取得（music21の四分音符単位）
                            const measureStart = sourceNote.voiceEntry
                                ?.parentSourceStaffEntry
                                ?.verticalContainerParent
                                ?.parentMeasure
                                ?.absoluteTimestamp
                                ?.realValue;

                            const noteStart =
                                sourceNote.voiceEntry?.Timestamp?.realValue;

                            const absoluteOffset =
                                (measureStart + noteStart) * 4;

                            // 選択した音符の識別情報を記録
                            selectedNoteInfo = {
                                partId: sourceNote.voiceEntry?.ParentVoice?.parent?.idString,
                                voiceId: sourceNote.voiceEntry?.ParentVoice?.voiceId,
                                measureNumber: measure.measureNumber,
                                offset: absoluteOffset,
                                midi: sourceNote.halfTone + 12,
                                fingering: originalFinger
                            };

                            console.log(
                            "選択した音符の識別情報:",
                            JSON.stringify(selectedNoteInfo, null, 2)
                        );

                            // 音符情報をConsoleに表示
                            console.log(
                                "小節番号:",
                                measure.measureNumber
                            );

                            console.log(
                                "音高（MIDI）:",
                                sourceNote.halfTone + 12
                            );

                            console.log(
                                "指番号:",
                                sourceNote.Fingering?.value ?? "なし"
                            );

                            // 選択した音符の情報を画面に表示
                            parentElement.querySelector("#measure-number").textContent =
                                measure.measureNumber;

                            parentElement.querySelector("#note-pitch").textContent =
                                sourceNote.halfTone + 12;

                            // 指番号の選択欄を有効にする
                            const fingerSelect =
                                parentElement.querySelector("#finger-select");

                            fingerSelect.disabled = false;
                            fingerSelect.value = originalFinger ?? "";

                            // 前に選択した符頭の色を元に戻す
                            if (
                                selectedNotehead &&
                                selectedNotehead !== notehead
                            ) {
                                selectedNotehead.style.fill = "";

                                selectedNotehead.querySelectorAll("path").forEach(
                                    path => {
                                        path.style.fill = "";
                                    }
                                );
                            }

                            // 新しく選択した符頭を青色にする
                            notehead.style.fill = "blue";

                            notehead.querySelectorAll("path").forEach(path => {
                                path.style.fill = "blue";
                            });

                            // 現在選択している符頭を記録
                            selectedNotehead = notehead;

                            return;
                        }
                    }
                }
            }
        }

        console.log("対応する音符が見つかりませんでした");
    });

    // 指番号の変更処理
    const fingerSelect = parentElement.querySelector("#finger-select");

    fingerSelect.addEventListener("change", function(event) {

        // 音符が選択されていない場合
        if (!selectedSourceNote) {
            return;
        }

        const newFinger = event.target.value;

        if (newFinger === "") {
            return;
        }

        // 単音の場合のみ、指番号データがなければ作成する
        if (
            (!selectedChordInfo || selectedChordInfo.notes.length === 1) &&
            !selectedSourceNote.Fingering
        ) {
            selectedSourceNote.Fingering = {
                value: newFinger
            };

            console.log("新しい指番号データを作成しました");
        }

        // 選択時に取得した変更前の指番号を使用
        const beforeFinger = selectedNoteInfo.fingering;

        console.log("変更前:", beforeFinger);

        // 指番号を変更
        if (
            selectedChordInfo &&
            selectedChordInfo.notes.length > 1 &&
            selectedChordInfo.fingers.length === selectedChordInfo.notes.length
        ) {
            // 重音の場合：選択した音符の指番号だけを変更
            selectedChordInfo.fingers[selectedChordInfo.selectedIndex] =
                newFinger;

            const updatedFingering =
                selectedChordInfo.fingers.join("\n");

            // 指番号が格納されている元の音符を探す
            const ownerNote = selectedChordInfo.notes.find(
                note => note.sourceNote?.Fingering
            );

            if (ownerNote) {
                ownerNote.sourceNote.Fingering.value =
                    updatedFingering;
            }

            console.log(
                "更新後の重音指番号:",
                updatedFingering
            );

        } else {
            // 単音の場合
            selectedSourceNote.Fingering.value = newFinger;
        }

        // 修正した音符の情報を作成
        const editedNote = {
            ...selectedNoteInfo,
            before_fingering:
                beforeFinger === null || beforeFinger === undefined
                    ? null
                    : Number(beforeFinger),
            fingering: Number(newFinger)
        };

        // 同じ音符がすでに修正されているか確認
        const existingIndex = editedNotes.findIndex(note =>
            note.partId === editedNote.partId &&
            note.voiceId === editedNote.voiceId &&
            note.measureNumber === editedNote.measureNumber &&
            note.offset === editedNote.offset &&
            note.midi === editedNote.midi
        );

        // 同じ音符なら上書き、なければ追加
        if (existingIndex >= 0) {
            editedNotes[existingIndex] = editedNote;
        } else {
            editedNotes.push(editedNote);
        }

        console.log(
            "保存された修正情報:",
            JSON.stringify(editedNotes, null, 2)
        );

        // 修正情報をStreamlitのPython側へ送信
        setStateValue("edited_notes", [...editedNotes]);

        console.log("修正情報をPython側へ送信しました");

        console.log(
            "変更後:",
            selectedSourceNote.Fingering?.value ??
                "重音の共有指番号を更新"
        );

        // 楽譜を再描画
        osmd.render();

        console.log("指番号を変更して楽譜を再描画しました");
    });

    console.log("Streamlit内で楽譜の表示が完了しました");
}