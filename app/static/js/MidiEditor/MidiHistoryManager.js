/**
 * MIDI 历史管理器 - 提供类似 VSCode 的撤销/重做功能
 */

import { deleteByNoteInAll, deleteByNoteInTrack, noteNameToMidi } from "./pianoRoll.js";
import { noteInTrackMap, noteToIndexMap, spatialIndex } from "./hashTable.js";
import { removeNoteFromSpatialIndex, addNoteToSpatialIndex } from "./mapAndLocate.js";

const canvas = document.getElementById("pianoRoll");
const ctx = canvas.getContext("2d");
const noteHeight = 18;
const timeScale = 200;
const pitchBase = 21; // A0
const visibleRange = 88;

export class MidiHistoryManager {
    constructor(midi, allNotes, trackVisibility, options = {}) {
        // 直接获得piano roll中currentMidi和allNotes的引用
        // allNotes.note和track.notes中的note引用同一个对象
        this.currentMidi = midi;
        this.allNotes = allNotes;
        this.trackVisibility = trackVisibility;

        // 历史记录相关
        this.history = [];
        this.pointer = -1;
        this.batchGroup = null;

        // 配置项
        this.maxHistorySize = options.maxHistorySize || 10;
        this.mergeThreshold = options.mergeThreshold || 10;

        // 事件系统
        this.EVENTS = {
            CHANGE: 'change',
            UNDO: 'undo',
            REDO: 'redo',
            BATCH_START: 'batchStart',
            BATCH_END: 'batchEnd'
        };

        this.listeners = {
            [this.EVENTS.CHANGE]: [],
            [this.EVENTS.UNDO]: [],     // 可以高亮显示，触发提示，重绘画布等
            [this.EVENTS.REDO]: [],
            [this.EVENTS.BATCH_START]: [],
            [this.EVENTS.BATCH_END]: []         // 可以统计修改数量等
        };

        // 保存点管理
        this.savePoints = new Set();
        this.shortcuts = {
            undo: ['Ctrl+Z', 'Command+Z'],
            redo: ['Ctrl+Y', 'Command+Y', 'Ctrl+Shift+Z']
        };
    }

    // 深克隆方法，初始化使用
    _cloneMidi(midi) {
        return JSON.parse(JSON.stringify(midi));
    }

    // 触发事件
    _trigger(event, data = {}) {
        const listeners = this.listeners[event];
        listeners.forEach(listener => {
            if (typeof listener === 'function') {
                listener(this.currentMidi);
            }
        });
    }

    // 注册事件监听器
    on(event, listener) {
        if (!this.EVENTS[event] || typeof listener !== 'function') {
            return;
        }

        const _event = this.EVENTS[event];       // 小写的事件名

        if (!this.listeners[_event]) {
            this.listeners[_event] = [];
        }

        this.listeners[_event].push(listener);
        return () => {
            this.listeners[_event] = this.listeners[_event].filter(l => l !== listener);
        };
    }

    // 批量操作优化
    beginBatch(label = "批量操作") {
        console.log("beginBatch triggered");

        if (this.batchGroup) {
            this.batchGroup = {
                // 类似链表，存储父批量组
                parent: this.batchGroup,
                label,
                changes: [],
                timestamp: new Date()
            };
        } else {
            this.batchGroup = {
                parent: null,
                label,
                changes: [],
                timestamp: new Date()
            };
        }

        this._trigger(this.EVENTS.BATCH_START, { label });
    }

    // 结束批量操作
    endBatch() {
        if (!this.batchGroup) {
            console.warn("In endBatch, batchGroup not found");
            return;
        }

        console.log("endBatch triggered");

        const batchChanges = this.batchGroup.changes;

        if (batchChanges.length > 0) {
            this._addHistoryEntry({
                type: "batch",
                label: this.batchGroup.label,
                changes: batchChanges,
                timestamp: new Date(),
            });
        }
        else {
            console.warn("There is nothing in batchGroup!");
        }

        // 恢复上层批量操作或清空
        this.batchGroup = this.batchGroup.parent; // ???初始为null，会不断恢复成null
        this._trigger(this.EVENTS.BATCH_END, { label: this.batchGroup?.label });
    }

    // 添加历史记录 --> pointer用于指向当前所在的历史位置
    _addHistoryEntry(entry) {
        console.log("_addHistoryEntry triggered");

        // 防御性拷贝
        const safeEntry = this._cloneMidi(entry);

        // 清除未来历史
        if (this.pointer < this.history.length - 1) {
            this.history = this.history.slice(0, this.pointer + 1);
        }

        // 智能合并
        if (this._canMerge(safeEntry)) {
            this._mergeLastEntry(safeEntry);
            this._trigger(this.EVENTS.CHANGE, this.getStatus());
            return;
        }

        // 添加新记录
        this.history.push(safeEntry);
        // 直接在最后添加
        this.pointer = this.history.length - 1;

        while (this.history.length > this.maxHistorySize) {
            this.savePoints.delete(0); // 删除最早保存点
            this.history.shift();
            this.pointer--;
        }

        // 更新历史记录表
        this._trigger(this.EVENTS.CHANGE, this.getStatus());
    }

    // 检查是否可以合并操作 --> 连续修改同一个音符时，直接合并
    _canMerge(newEntry) {
        if (this.history.length === 0) return false;

        const lastEntry = this.history[this.pointer];
        const isSameType = lastEntry.type === newEntry.type;
        const isRecent = new Date() - lastEntry.timestamp < this.mergeThreshold;

        // 支持修改、添加、删除操作合并
        const supportedTypes = ['modify', 'add', 'delete', 'modifyTime', 'dragNote', 'modifyName'];
        return isSameType && supportedTypes.includes(newEntry.type) && isRecent;
    }

    // 合并最后一条记录
    _mergeLastEntry(newEntry) {
        console.log("_mergeLastEntry triggered");

        const lastEntry = this.history[this.pointer];

        // 合并逻辑示例（以修改操作为例）
        if (lastEntry.type === 'modify' && newEntry.type === 'modify') {
            lastEntry.changes = lastEntry.changes.concat(newEntry.changes);
            lastEntry.timestamp = newEntry.timestamp;
            lastEntry.label = `合并操作: ${lastEntry.label} 和 ${newEntry.label}`;
        } else if (lastEntry.type === 'modifyTime' && newEntry.type === 'modifyTime') {
            // 合并时间修改操作
            lastEntry.changes = lastEntry.changes.concat(newEntry.changes);
            lastEntry.timestamp = newEntry.timestamp;
            lastEntry.label = `合并时间修改: ${lastEntry.label}`;
        }
    }

    // 状态获取
    getStatus() {
        return {
            canUndo: this.pointer >= 0,
            canRedo: this.pointer < (this.history.length - 1),
            currentStep: this.pointer,
            totalSteps: this.history.length,
            hasUnsavedChanges: this._hasUnsavedChanges(),
            currentSavePoint: this.savePoints.size ? [...this.savePoints][0] : null,
            history: this.history.map((entry, index) => ({
                ...entry,
                isCurrent: index === this.pointer,
                isSavePoint: this.savePoints.has(index)
            }))
        };
    }

    // 检查是否有未保存的更改
    _hasUnsavedChanges() {
        // 简单比较，实际应用中可能需要更复杂的比较逻辑
        return this.pointer !== -1;
    }

    // 设置保存点
    setSavePoint() {
        if (this.history.length === 0 || this.pointer < 0) {
            console.warn("In setSavePoint, cannot find available history");
            return;
        }

        console.log("setSavePoint triggered");

        // 最多保留3个保存点
        this.savePoints.add(this.pointer);
        while (this.savePoints.size > 3) {
            this.savePoints.delete(Math.min(...this.savePoints));
        }

        this._trigger(this.EVENTS.CHANGE, this.getStatus());
    }

    restoreToHistory(index) {
        if (index < 0) {
            console.warn("Cannot find aimed history");
            return;
        }
        console.log(`Restore ${this.pointer} to corresponding history, index = ${index}`);

        if (index >= this.pointer) {
            console.warn("只能还原到历史");
            return;
        }

        try {
            // 撤销/重做操作直到到达保存点
            while (this.pointer > index) {
                this.undo();
            }

            this._trigger(this.EVENTS.CHANGE, this.getStatus());
            return true;
        } catch (error) {
            console.error("还原到历史记录失败:", error);
            return false;
        }
    }

    // 恢复到最近的保存点
    restoreToSavePoint() {
        if (this.savePoints.size === 0) {
            console.warn("没有保存点可恢复");
            return false;
        }

        console.log("restoreToSavePoint triggered");

        // 获取最近的保存点（最大的索引值）
        const latestSavePoint = Math.max(...this.savePoints);

        try {
            // 撤销/重做操作直到到达保存点
            while (this.pointer > latestSavePoint) {
                this.undo();
            }

            while (this.pointer < latestSavePoint) {
                this.redo();
            }

            this._trigger(this.EVENTS.CHANGE, this.getStatus());
            return true;
        } catch (error) {
            console.error("恢复到保存点失败:", error);
            return false;
        }
    }

    // 重置操作
    reset() {
        this.currentMidi = this._cloneMidi(this.originalMidi);
        this.history = [];
        this.pointer = -1;
        this.batchGroup = null;
        this.savePoints.clear();
        this._trigger(this.EVENTS.CHANGE, this.getStatus());
    }

    // 重做操作
    redo() {
        // 需要先有undo，才能有redo
        if (this.pointer >= this.history.length - 1) {
            console.warn(`Pointer error, history length = ${this.history.length}, pointer = ${this.pointer}`);
            return false;
        }
        else if (this.history.length === 0) {
            console.warn("no history");
            return false;
        }

        try {
            // undo只是指针移动，并未真正删除存储的entry
            this.pointer++;
            const entry = this.history[this.pointer];
            this._applyChanges(entry.changes, 'redo');
            this._trigger(this.EVENTS.REDO, entry);
            return true;
        } catch (error) {
            console.error('重做操作失败:', error);
            this.pointer--;
            return false;
        }
    }

    // 撤销操作
    undo() {
        if (this.pointer < 0 || this.history.length === 0) {
            console.warn(`undo操作异常, pointer = ${this.pointer}, history.length = ${this.history.length}`);
            // 重置指针到有效位置
            this.pointer = Math.max(0, this.pointer);
            return false;
        }

        console.log("Undo triggered!");
        console.log(`Undo! pointer = ${this.pointer}`);

        try {
            const entry = this.history[this.pointer];

            console.log(entry);

            this._applyChanges(entry.changes.reverse(), 'undo');        // reverse确保撤销按照正确顺序回滚
            this.pointer--;

            console.log("After changes applied, redraw");
            // showMidi(this.currentMidi);
            // 需要传输midi文件来重绘画布
            this._trigger(this.EVENTS.UNDO, this.currentMidi);

            return true;
        } catch (error) {
            console.error('撤销操作失败:', error);
            return false;
        }
    }

    // 应用变更通用方法，direction为调用这个函数的位置对应的标志？
    _applyChanges(changes, direction) {
        // 取出了change对象，处理的不是数组
        changes.forEach(change => {
            switch (change.type) {
                case 'modify':
                    this._applyModify(change, direction);
                    break;
                case 'add':
                    if (direction === 'undo') {
                        console.log("add undo");
                        this._applyDelete(change, direction);
                    }
                    else if (direction === 'redo') {
                        console.log("add redo");
                        this._applyAdd(change, direction);
                    }
                    break;
                case 'delete':
                    // undo撤销操作
                    if (direction === 'undo') {
                        console.log("delete undo");
                        this._applyAdd(change, direction);
                    }
                    // redo重新执行被撤销的操作
                    else if (direction === 'redo') {
                        console.log("delete redo");
                        this._applyDelete(change, direction);
                    }
                    break;
                case 'modifyTime':
                    this._applyModifyTime(change, direction);
                    break;
                case 'dragNote':
                    this._applyDragNote(change, direction);
                    break;
                case 'modifyName':
                    // 目前没有实现
                    this._applyModifyNoteName(change, direction);
                    break;
                case 'toggleTrackVisibility':
                    this._applyTrackVisibility(change, direction);
                    break;
                // 其他操作类型扩展
            }
        });
        this._trigger(this.EVENTS.CHANGE, this.getStatus());
    }

    // 应用修改操作
    _applyModify(change, direction) {
        if (!change) {
            console.warn("Change not defined");
        }
        const track = this.currentMidi.tracks[change.trackIndex];
        if (!track) {
            console.log("Change has invalid value");
            return;
        }

        console.log("_applyModify triggered");

        // const noteInTrack = track.notes.find(note => note.midi === change.note.midi && note.time === change.note.time);
        const key = `${change.trackIndex}-${change.note.time}-${change.note.midi}`;  // 自定义哈希键
        let noteInTrack;
        noteInTrack = noteInTrackMap.get(key);
        if (!noteInTrack) {
            console.warn("noteInTrack not found")
            return;
        }

        // const noteInAll = this.allNotes.find(thisNote => thisNote.note.midi === change.note.midi && thisNote.note.time === change.note.time);
        let noteInAll;

        noteInAll = this.allNotes.get(key);

        if (!noteInAll) {
            console.warn("noteInAll not found");
            return;
        }

        // 此处的两者引用是否相同？
        if (direction == 'undo') {
            noteInTrack.duration = change.initDuration;
            noteInAll.width = change.initDuration * timeScale;
        }
        else if (direction == 'redo') {
            // 是否有通过引用一同被更改？？？
            console.log("modify duration redo");
            noteInTrack.duration = change.newDuration;
            noteInAll.width = change.newDuration * timeScale;
        }
    }

    // 应用添加操作
    _applyAdd(change, direction) {
        const trackIndex = change.trackIndex;
        const track = this.currentMidi.tracks[trackIndex];
        if (!track) {
            console.warn("Track not found");
            return;
        }

        console.log("Apply add invoked.");

        if (!change) {
            console.log("change undefined");
            return;
        }

        console.log(`${change.changedNote.note.name} added!!!`);

        track.notes.splice(0, 0, change.changedNote.note);
        track.notes.sort((a, b) => a.time - b.time);

        // this.allNotes.push(change.changedNote);
        const key = `${trackIndex}-${change.changedNote.note.time}-${change.changedNote.note.midi}`;  // 自定义哈希键
        this.allNotes.set(key, change.changedNote);  // 存入哈希表 
        noteInTrackMap.set(key, change.changedNote.note);
        // 如何优化？
        const idx = track.notes.findIndex(note => note === change.changedNote.note);
        noteToIndexMap.set(key, { trackIndex, idx });
    }

    // 应用删除操作
    _applyDelete(change, direction) {
        const track = this.currentMidi.tracks[change.trackIndex];
        if (!track) {
            console.log("Track not found");
            return;
        }

        const _note = change.changedNote.note;
        // 此处没有共用引用，直接通过属性进行比较
        // const index1 = track.notes.findIndex(note => note.midi == _note.midi && note.time == _note.time && note.duration == _note.duration);
        let index1;
        const key = `${change.trackIndex}-${_note.time}-${_note.midi}`;
        index1 = noteToIndexMap.get(key).idx;

        if (index1 < 0) {
            console.log(`index1 is ${index1}, return`);
            return;
        }
        track.notes.splice(index1, 1);
        noteToIndexMap.delete(key);
        noteInTrackMap.delete(key);
        removeNoteFromSpatialIndex(change.changedNote);
        // 删除的是pianoRoll中的allNotes内容 -- 引用一致
        deleteByNoteInAll(change.changedNote);
    }

    // 应用修改时间操作
    _applyModifyTime(change, direction) {
        if (!change) {
            console.warn("change为空, 异常退出_applyModifyTime");
            return;
        }

        const track = this.currentMidi.tracks[change.trackIndex];
        if (!track) {
            console.warn("不存在该track, 异常退出_applyModifyTime");
            return;
        }

        console.log("_applyModifyTime triggered");

        if (direction === 'undo') {
            // change.originalNote.note是未经更新的，而this.currentMidi是已经通过引用更新的
            // const timeModifiedNote = track.notes.find(note => note.midi === change.newValue.note.midi && note.duration === change.newValue.note.duration);
            let timeModifiedNote;
            const key = `${change.trackIndex}-${change.newValue.note.time}-${change.newValue.note.midi}`;  // 自定义哈希键
            timeModifiedNote = noteInTrackMap.get(key);

            if (!timeModifiedNote) {
                console.warn("Cannot find corresponding note in track.notes");
                return;
            }

            let note2;
            // 增设id？
            note2 = this.allNotes.get(key);

            if (!note2) {
                console.warn("Cannot find the note in allNotes");
                return;
            }

            console.log("Modify time undo");
            timeModifiedNote.time = change.originalNote.x / timeScale;
            note2.x = change.originalNote.x;
        }
        else if (direction === 'redo') {
            // change.originalNote.note是未经更新的，而this.currentMidi是已经通过引用更新的
            // const timeModifiedNote = track.notes.find(note => note.midi === change.originalNote.note.midi && note.duration === change.originalNote.note.duration);

            const key = `${change.trackIndex}-${change.originalNote.note.time}-${change.originalNote.note.midi}`;  // 自定义哈希键
            let timeModifiedNote;
            timeModifiedNote = noteInTrackMap.get(key);

            if (!timeModifiedNote) {
                console.warn("Cannot find corresponding note in track.notes");
                return;
            }

            let note2;
            note2 = this.allNotes.get(key);

            if (!note2) {
                console.warn("Cannot find the note in allNotes");
                return;
            }

            console.log("modify time redo");
            console.log(change.newValue.x);
            timeModifiedNote.time = change.newValue.time;
            note2.x = change.newValue.time * timeScale;
        }
    }

    // 应用修改音符名称操作
    _applyModifyNoteName(change, direction) {
        if (!change) {
            console.warn("change为空, 异常退出_applyModifyNoteName");
            return;
        }

        const track = this.currentMidi.tracks[change.trackIndex];
        if (!track) {
            console.warn("不存在该track, 异常退出_applyModifyNoteName");
            return;
        }

        console.log("_applyModifyNoteName triggered");

        let noteKey;
        let noteInTrack, noteInAllNotes;

        if (direction === 'undo') {
            // 撤销修改名称，恢复为 initName
            const newMidi = noteNameToMidi(change.newName);
            noteKey = `${change.trackIndex}-${change.note.time}-${newMidi}`;
            noteInTrack = noteInTrackMap.get(noteKey);
            noteInAllNotes = this.allNotes.get(noteKey);

            if (!noteInTrack) {
                console.warn("Cannot find the note in track");
                return;
            }
            if (!noteInAllNotes) {
                console.warn("Cannot find the note in allNotes");
                return;
            }

            const initMidi = noteNameToMidi(change.initName);

            console.log("Modify note name undo");
            noteInTrack.name = change.initName;
            noteInTrack.midi = initMidi;
            noteInAllNotes.note.name = change.initName;
            noteInAllNotes.note.midi = initMidi;
            noteInAllNotes.y = canvas.height - ((initMidi - pitchBase + 1) * noteHeight); // 更新y坐标

            const newKey = `${change.trackIndex}-${change.note.time}-${initMidi}`;

            noteInTrackMap.delete(noteKey); // 删除旧的键
            noteInTrackMap.set(newKey, noteInTrack); // 使用新的键存储音符
            this.allNotes.delete(noteKey);
            this.allNotes.set(newKey, noteInAllNotes); // 使用新的键存储音符

        } else if (direction === 'redo') {
            // 重做修改名称，应用 newName
            const initMidi = noteNameToMidi(change.initName);
            noteKey = `${change.trackIndex}-${change.note.time}-${initMidi}`;
            noteInTrack = noteInTrackMap.get(noteKey);
            noteInAllNotes = this.allNotes.get(noteKey);

            if (!noteInTrack) {
                console.warn("Cannot find the note in track");
                console.log("Using key:", noteKey);
                console.log(noteInTrackMap);
                return;
            }
            if (!noteInAllNotes) {
                console.warn("Cannot find the note in allNotes");
                return;
            }

            const newMidi = noteNameToMidi(change.newName);

            console.log("Modify note name redo");
            noteInTrack.name = change.newName;
            noteInTrack.midi = newMidi;
            noteInAllNotes.note.name = change.newName;
            noteInAllNotes.note.midi = newMidi;
            noteInAllNotes.y = canvas.height - ((newMidi - pitchBase + 1) * noteHeight); // 更新y坐标

            const newKey = `${change.trackIndex}-${change.note.time}-${newMidi}`;

            noteInTrackMap.delete(noteKey); // 删除旧的键
            noteInTrackMap.set(newKey, noteInTrack); // 使用新的键存储音符
            this.allNotes.delete(noteKey);
            this.allNotes.set(newKey, noteInAllNotes); // 使用新的键存储音符
        }
    }


    // 应用拖拽音符操作
    _applyDragNote(change, direction) {
        if (!change) {
            console.warn("Change is undefined");
            return;
        }

        console.log("_applyDragNote triggered");

        const track = this.currentMidi.tracks[change.trackIndex];
        if (!track) {
            alert("Track does not exist!");
            return;
        }

        if (direction === 'undo') {
            // 判断不够精确，可能产生冲突
            // const draggedNoteInTrackIndex = track.notes.findIndex(note => note.midi === change.newNote.note.midi && note.duration === change.newNote.note.duration);

            // newNote如果记录的是最后的位置，那么使用time应当毫无问题 ！！！
            // 将当前的note从数组和映射中删除
            const key1 = `${change.newNote.trackIndex}-${change.newNote.note.time}-${change.newNote.note.midi}`;
            // 并非找不到，而是idx本身就被设置为了-1
            const draggedNoteInTrackIndex = noteToIndexMap.get(key1).idx;

            if (draggedNoteInTrackIndex < 0) {
                console.warn("Cannot find in track.notes");
                return;
            }
            else {
                console.log(`In undo, get old index ${draggedNoteInTrackIndex} from track.notes`);
            }

            track.notes.splice(draggedNoteInTrackIndex, 1);
            noteToIndexMap.delete(key1);
            noteInTrackMap.delete(key1);
            // 如何删除？
            removeNoteFromSpatialIndex(change.newNote);


            track.notes.push(change.originalNote.note);
            track.notes.sort((a, b) => a.time - b.time);

            // note已经跟着track.notes的一起修改了
            let draggedNoteInAll = {};
            draggedNoteInAll.x = change.originalNote.x;
            draggedNoteInAll.y = change.originalNote.y;
            draggedNoteInAll.width = change.originalNote.width;
            draggedNoteInAll.height = change.originalNote.height;
            draggedNoteInAll.trackIndex = change.originalNote.trackIndex;

            draggedNoteInAll.note = change.originalNote.note;
            // this.allNotes.push(draggedNoteInAll);

            const key = `${draggedNoteInAll.trackIndex}-${draggedNoteInAll.note.time}-${draggedNoteInAll.note.midi}`;  // 自定义哈希键
            this.allNotes.set(key, draggedNoteInAll);  // 存入哈希表 
            noteInTrackMap.set(key, change.originalNote.note);
            // 如何优化？
            const idx = track.notes.findIndex(note => note === change.originalNote.note);
            console.log(`When undo, set new index ${idx} in track.notes`);
            console.log(`Dragged note updated to ${draggedNoteInAll.note.name} at time ${draggedNoteInAll.note.time}`);
            const trackIndex = draggedNoteInAll.trackIndex;
            noteToIndexMap.set(key, { trackIndex, idx });
            addNoteToSpatialIndex(draggedNoteInAll);
        }
        else if (direction == 'redo') {
            console.log("drag note redo");

            // 通过旧的信息找到音符
            // const draggedNoteInTrackIndex = track.notes.findIndex(note => note.midi === change.originalNote.note.midi && note.duration === change.originalNote.note.duration);

            const key1 = `${change.originalNote.trackIndex}-${change.originalNote.note.time}-${change.originalNote.note.midi}`;  // 自定义哈希键
            // 查找出现问题
            const draggedNoteInTrackIndex = noteToIndexMap.get(key1).idx;

            if (draggedNoteInTrackIndex < 0) {
                console.warn("Cannot find in track.notes");
                return;
            }

            // 使用新的信息修改音符
            track.notes.splice(draggedNoteInTrackIndex, 1);
            noteInTrackMap.delete(key1);
            noteToIndexMap.delete(key1);

            track.notes.push(change.newNote.note);
            track.notes.sort((a, b) => a.time - b.time);

            let draggedNoteInAll = {};
            draggedNoteInAll.x = change.newNote.x;
            draggedNoteInAll.y = change.newNote.y;
            draggedNoteInAll.width = change.newNote.width;
            draggedNoteInAll.height = change.newNote.height;
            draggedNoteInAll.trackIndex = change.newNote.trackIndex;
            draggedNoteInAll.note = change.newNote.note;

            const key = `${draggedNoteInAll.trackIndex}-${draggedNoteInAll.note.time}-${draggedNoteInAll.note.midi}`;  // 自定义哈希键
            this.allNotes.set(key, draggedNoteInAll);  // 存入哈希表 
            noteInTrackMap.set(key, change.newNote.note);
            // 如何优化？
            const idx = track.notes.findIndex(note => note === change.newNote.note);
            console.log(`When redo, set ${idx} in track.notes`);
            console.log(`Dragged note updated to ${draggedNoteInAll.note.name} at time ${draggedNoteInAll.note.time}`);
            const trackIndex = draggedNoteInAll.trackIndex;
            noteToIndexMap.set(key, { trackIndex, idx });
        }
    }

    // 应用轨道可见性变更
    _applyTrackVisibility(change, direction) {
        const track = this.currentMidi.tracks[change.trackIndex];
        if (!track) return;

        track._isVisible = direction === 'undo'
            ? change.originalValue
            : change.newValue;
    }

    // 音符修改操作
    modifyNote(trackIndex, changedNote, initDuration, newDuration) {
        if (!this.currentMidi.tracks[trackIndex] || !changedNote || !newDuration) {
            console.warn("Invalid input value");
            return false;
        }

        // 记录变更
        const change = {
            type: 'modify',
            trackIndex,
            note: changedNote.note,
            initDuration,
            newDuration,
            timestamp: new Date()
        };

        // 添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
        } else {
            this._addHistoryEntry({
                type: 'modify',
                label: `修改音符 (轨道 ${trackIndex + 1}, 音符 ${change.note.name})`,
                changes: [change],
                timestamp: new Date(),
            });
        }

        return true;
    }

    // 修改音符名称
    modifyNoteName(trackIndex, newNote, initName, newName) {
        if (!this.currentMidi.tracks[trackIndex] || !newNote || !initName || !newName) {
            console.warn("Invalid function input !");
            return;
        }

        // 记录变更
        const change = {
            type: 'modifyName',
            trackIndex,
            // 引用track.notes中的新信息
            note: newNote,
            initName,
            newName,
            timestamp: new Date()
        };

        // 添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
        } else {
            this._addHistoryEntry({
                type: 'modifyName',
                label: `修改音符名称 (轨道 ${trackIndex + 1}, 从 ${initName} 到 ${newName})`,
                changes: [change],
                timestamp: new Date(),
            });
        }

        return true;
    }

    // 添加音符
    addNote(trackIndex, changedNote) {
        if (!this.currentMidi.tracks[trackIndex]) return false;

        const track = this.currentMidi.tracks[trackIndex];

        // 记录变更
        const change = {
            type: 'add',
            trackIndex,
            changedNote,
            timestamp: new Date()
        };

        // 添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
        } else {
            this._addHistoryEntry({
                type: 'add',
                label: `添加音符 (轨道 ${trackIndex + 1})`,
                changes: [change],
                timestamp: new Date(),
            });
        }

        return true;
    }

    // 删除音符
    deleteNote(trackIndex, backupNote) {
        if (!this.currentMidi.tracks[trackIndex] || !backupNote) {
            console.warn("Track index not exists, or deleted note is undefined!");
            console.warn(`Track index = ${trackIndex}`);
            return false;
        }

        console.log("deleteNote triggered.");

        // 记录变更
        const change = {
            type: 'delete',
            trackIndex,
            changedNote: { ...backupNote },
            timestamp: new Date()
        };

        // 添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
        } else {
            this._addHistoryEntry({
                type: 'delete',
                label: `删除音符 (轨道 ${trackIndex + 1}, 音符 ${backupNote.note.name})`,
                changes: [change],
                timestamp: new Date(),
            });
        }

        return true;
    }

    // 修改音符时间
    modifyNoteTime(trackIndex, originalNote, newTime) {
        if (!this.currentMidi.tracks[trackIndex] || !originalNote) {
            console.warn("Argument invalid!!!");
            return false;
        }

        const newValue = { ...originalNote, time: newTime };

        console.log(`modifyNoteTime triggered, new time = ${newTime}`);

        // 记录变更
        const change = {
            type: 'modifyTime',
            trackIndex,
            originalNote,
            newValue,
            timestamp: new Date()
        };

        // 添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
        } else {
            this._addHistoryEntry({
                type: 'modifyTime',
                label: `修改音符时间 (轨道 ${trackIndex + 1}, 音符 ${originalNote.note.name})`,
                changes: [change],
                timestamp: new Date(),
            });
        }

        return true;
    }

    // 记录音符拖拽操作
    recordNoteDrag(trackIndex, originalNote, newNote) {
        if (!this.currentMidi.tracks[trackIndex] || !originalNote || !newNote) {
            console.log("Invalid input");
            return;
        }

        // 记录变更
        const change = {
            type: 'dragNote',
            trackIndex,
            // 引用不属于track.notes的旧信息，经过了深拷贝
            originalNote,
            // 引用track.notes中的新信息
            newNote,
            timestamp: new Date()
        };

        console.log(`newNote time ${newNote.note.time}`);

        // 在进行批量操作时，先不添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
            // 这里的direction输入还有待商榷
            this._applyDragNote(change, 'dragNote');
        } else {
            // 添加到历史记录
            this._addHistoryEntry({
                type: 'dragNote',
                label: `拖拽音符 (轨道 ${trackIndex + 1}, 音符 ${originalNote.note.name})`,
                changes: [change],
                timestamp: new Date(),
            });
        }
    }

    // 切换轨道可见性
    toggleTrackVisibility(trackIndex, isVisible) {
        if (!this.currentMidi.tracks[trackIndex]) return false;

        const originalValue = this.currentMidi.tracks[trackIndex]._isVisible ?? true;
        this.currentMidi.tracks[trackIndex]._isVisible = isVisible;

        // 记录变更
        const change = {
            type: 'toggleTrackVisibility',
            trackIndex,
            originalValue,
            newValue: isVisible,
            timestamp: new Date()
        };

        // 添加到历史记录
        if (this.batchGroup) {
            this.batchGroup.changes.push(change);
        } else {
            this._addHistoryEntry({
                type: 'toggleTrackVisibility',
                label: `${isVisible ? '显示' : '隐藏'}轨道 (轨道 ${trackIndex + 1})`,
                changes: [change],
                timestamp: new Date(),
            });
        }

        return true;
    }

    // 处理快捷键
    handleShortcut(event) {
        // 立即阻止浏览器默认行为
        if (this.isModifierKey(event) || this.isShortcutKey(event)) {
            event.preventDefault();
        }

        console.log("handleShortCut triggered");

        const keyCombination = `${event.ctrlKey || event.metaKey ? 'Ctrl+' : ''}${event.shiftKey ? 'Shift+' : ''}${event.key.toUpperCase()}`;

        console.log('快捷键按下:', keyCombination);

        if (this.shortcuts.undo.includes(keyCombination)) {
            console.log('执行撤销操作');
            this.undo();
            return true;
        }

        if (this.shortcuts.redo.includes(keyCombination)) {
            console.log('执行重做操作');
            this.redo();
            return true;
        }

        return false;
    }

    isModifierKey(event) {
        return event.ctrlKey || event.metaKey || event.shiftKey || event.altKey;
    }

    isShortcutKey(event) {
        const shortcutKeys = ['z', 'y'];
        return shortcutKeys.includes(event.key.toLowerCase());
    }
}    