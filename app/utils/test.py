import os
import mido


def average_pitch(track):
    notes = [msg.note for msg in track if msg.type in ['note_on', 'note_off']]
    if not notes:
        return 0
    return sum(notes) / len(notes)


def analyze_folder(folder_path):
    total_files = 0
    abnormal_count = 0
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.mid', '.midi')):
                filepath = os.path.join(root, file)
                try:
                    midi = mido.MidiFile(filepath)
                    if len(midi.tracks) < 2:
                        continue
                    pitch0 = average_pitch(midi.tracks[0])
                    pitch1 = average_pitch(midi.tracks[1])
                    total_files += 1
                    if pitch1 > pitch0:
                        abnormal_count += 1
                        print(f"[异常] {file}: track[0]={pitch0:.2f}, track[1]={pitch1:.2f}")
                except Exception as e:
                    print(f"❌ 处理失败: {file} 错误: {e}")

    print(f"\n总共处理 {total_files} 个文件")
    print(f"其中 {abnormal_count} 个文件的 track[1] 平均音高高于 track[0]（疑似左右手顺序异常）")


if __name__ == "__main__":
    folder_path = r"autodl-tmp/newdata/freescore_withtrack"  # 替换为你的文件夹路径
    analyze_folder(folder_path)
