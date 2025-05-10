/**
 * 钢琴组件JavaScript
 * 实现钢琴键盘的交互和音符播放功能
 */

import { Notes } from './lib/notes.js';
import SampleLibrary from './lib/ToneInstruments.js';
import Midi from './lib/jsmidgen.js';

class Piano {
  constructor() {
    //新增生成MIDI的button
    this.pianoHTML = `
      <div class="piano-component" id="pianoComponent">
        <div class="piano-scroll-wrap">
          <div class="piano-wrap" id="pianoWrap">
            <div class="piano-band">
              <div class="piano-tip">+ 代表 shift 键</div>
            </div>
            <div class="piano-key-wrap" id="pianoKeyWrap">
              <!-- 白键和黑键将通过JavaScript动态生成 -->
            </div>
          </div>
        </div>

        <div class="piano-options">
          <div class="option-item-wrap">
            <div class="option-item">
              <label class="label">
                显示按键提示
                <input type="checkbox" id="keyname" checked />
                <i></i>
              </label>
            </div>

            <div class="option-item">
              <label class="label">
                显示音名
                <input type="checkbox" id="notename" />
                <i></i>
              </label>
            </div>
          </div>

        </div>

        <div class='button-group'>
            <button id="begin">开始记录</button>
            <button id="end">结束记录</button>
        </div>

        <canvas id="audioEffectCanvas"></canvas>
      </div>

      <script type="module" src="./lib/jsmidgen.js"></script>
    `;

    // 配置参数
    this.pianoShow = false;
    this.enableBlackKey = false; // 启用黑色按键
    this.showKeyName = true; // 显示键名
    this.showNoteName = false; // 显示音符名
    this.synth = null;
    this.keydownTimer = null;
    this.keyLock = false;
    this.lastKeyCode = '';
    this.audioContextStarted = false;
    this.audioLoaded = false;

    // 绑定方法的this
    this.init = this.init.bind(this);
    this.initPiano = this.initPiano.bind(this);
    this.computeEleSize = this.computeEleSize.bind(this);
    this.renderPianoKeys = this.renderPianoKeys.bind(this);
    this.bindKeyboardEvent = this.bindKeyboardEvent.bind(this);
    this.clickPianoKey = this.clickPianoKey.bind(this);
    this.getNoteByKeyCode = this.getNoteByKeyCode.bind(this);
    this.getNoteByName = this.getNoteByName.bind(this);
    this.playNoteByKeyCode = this.playNoteByKeyCode.bind(this);
    this.playNote = this.playNote.bind(this);
    this.startAudioContext = this.startAudioContext.bind(this);
    this.triggerKeyEffect = this.triggerKeyEffect.bind(this);
    this.triggerKeyByName = this.triggerKeyByName.bind(this);

    this.showLoadingIndicator = this.showLoadingIndicator.bind(this);
    this.hideLoadingIndicator = this.hideLoadingIndicator.bind(this);
    // 创建一个绑定后的事件处理函数引用，以便能够正确移除
    this.boundHideLoadingIndicator = this.hideLoadingIndicator.bind(this);

    // 新增：确保 generateMidiFromStorage 方法内的 this 指向 Piano 类实例
    this.generateMidiFromStorage = this.generateMidiFromStorage.bind(this);
    this.clearStoredNotes = this.clearStoredNotes.bind(this);
    this.recordBegin = this.recordBegin.bind(this);

    // 添加样式到DOM
    const style = document.createElement('style');
    style.textContent = `
          /* 按钮容器样式 */
          .piano-component .button-group {
            margin: 20px 0;
            display: flex;
            gap: 12px;
          }
    
          /* 通用按钮样式 */
          .piano-component button {
            flex: 1;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
          }
    
          /* 按钮悬浮效果 */
          .piano-component button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
          }
    
          /* 生成按钮渐变 */
          #end {
            background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%);
            color: white;
            box-shadow: 0 2px 6px rgba(33,150,243,0.3);
          }
    
          /* 清空按钮渐变 */
          #begin {
            background: linear-gradient(135deg, #FF5722 0%, #F4511E 100%);
            color: white;
            box-shadow: 0 2px 6px rgba(255,87,34,0.3);
          }
    
          /* 按钮图标样式 */
          .piano-component button::before {
            content: '';
            display: block;
            width: 18px;
            height: 18px;
            background-size: contain;
            filter: brightness(0) invert(1);
          }
    
          /* MIDI图标 */
          #end::before {
            background-image: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="white" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11zm-9-7h2v2H9v-2zm0-4h2v2H9v-2zm0-4h2v2H9V9z"/></svg>');
          }
    
          /* 清空图标 */
          #begin::before {
            background-image: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="white" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>');
          }
    
          /* 加载动画 */
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
          .loading {
            position: relative;
            padding-left: 40px;
          }
          .loading::after {
            content: "";
            position: absolute;
            left: 15px;
            top: 50%;
            width: 18px;
            height: 18px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            transform: translateY(-50%);
          }

          /* 按钮加载状态 */
          .button-loader {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 3px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 8px;
          }

          /* 成功状态 */
          button:not(:disabled)[innerHTML*="✓"] {
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%) !important;
            opacity: 0.9;
          }

          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `;
    document.head.appendChild(style);
  }

  // 初始化，插入HTML并启动钢琴
  init(element) {
    // 将钢琴HTML插入到指定元素
    if (typeof element === 'string') {
      document.querySelector(element).insertAdjacentHTML('afterbegin', this.pianoHTML);
    } else if (element instanceof HTMLElement) {
      element.insertAdjacentHTML('afterbegin', this.pianoHTML);
    } else {
      document.body.insertAdjacentHTML('afterbegin', this.pianoHTML);
    }

    // 初始化钢琴
    this.initPiano();

    // 绑定开关事件
    document.getElementById('keyname').addEventListener('change', (e) => {
      this.showKeyName = e.target.checked;
      this.updateKeyDisplay();
    });

    document.getElementById('notename').addEventListener('change', (e) => {
      this.showNoteName = e.target.checked;
      this.updateKeyDisplay();
    });

    // 监听窗口大小变化，重新计算键盘尺寸
    window.addEventListener('resize', this.computeEleSize);

    // 在初始化代码中添加点击监听
    document.getElementById('end').addEventListener('click', async () => {
      await this.generateMidiFromStorage();   // 在生成函数内部清空
    });

    const beginButton = document.getElementById('begin');
    if (beginButton) {
      beginButton.addEventListener('click', this.recordBegin);
    }

    localStorage.setItem('beginTag', 'False');
    console.log("begin tag is initially false");
  }

  recordBegin() {
    console.log("record begins");
    localStorage.setItem('beginTag', 'True');
  }

  // 启动AudioContext
  startAudioContext() {
    if (this.audioContextStarted) return Promise.resolve();

    return Tone.start().then(() => {
      console.log('AudioContext已启动');
      this.audioContextStarted = true;
    }).catch(err => {
      console.error('AudioContext启动失败:', err);
    });
  }

  // 更新键盘显示
  updateKeyDisplay() {
    const keyNameElements = document.querySelectorAll('.keyname');
    const noteNameElements = document.querySelectorAll('.notename');

    keyNameElements.forEach(elem => {
      elem.style.display = this.showKeyName ? 'block' : 'none';
    });

    noteNameElements.forEach(elem => {
      elem.style.display = this.showNoteName ? 'block' : 'none';
    });
  }

  // 钢琴初始化
  async initPiano() {
    this.renderPianoKeys();

    setTimeout(() => {
      this.computeEleSize();
      document.getElementById('pianoWrap').classList.add('visible');
      this.pianoShow = true;
    }, 300);

    this.bindKeyboardEvent();

    // 加载钢琴音色
    try {
      this.synth = SampleLibrary.load({
        instruments: "piano",
        onload: () => {
          console.log('音频加载完成');
          this.audioLoaded = true;
        }
      });
    } catch (e) {
      console.error('音频加载失败:', e);
    }

    // 在用户点击钢琴键时启动AudioContext
    document.addEventListener('click', this.startAudioContext, { once: true });
  }

  // 计算元素尺寸
  computeEleSize() {
    const pianoKeyWrap = document.getElementById('pianoKeyWrap');
    const pianoWrap = document.getElementById('pianoWrap');
    const keysContainer = document.getElementById('piano-keys-container');

    // 设置钢琴键盘区域高度为固定高度200px
    pianoKeyWrap.style.height = '200px';
    keysContainer.style.height = '200px';

    // 设置黑键高度为固定高度的65%
    const bkeys = document.querySelectorAll('.bkey');
    bkeys.forEach(key => {
      key.style.height = '130px'; // 200px的65%
    });

    // 动态调整文字大小
    if (pianoWrap.offsetWidth < 800) {
      document.querySelectorAll('.wkey .keyname').forEach(elem => {
        elem.style.fontSize = '8px';
      });
      document.querySelectorAll('.wkey .notename').forEach(elem => {
        elem.style.fontSize = '7px';
      });
      document.querySelectorAll('.bkey .keyname').forEach(elem => {
        elem.style.fontSize = '6px';
      });
    }
  }

  // 渲染钢琴键 - 标准钢琴布局：白黑白黑白白黑白黑白黑白
  renderPianoKeys() {
    const pianoKeyWrap = document.getElementById('pianoKeyWrap');

    // 添加一个内部容器，用于放置钢琴键
    pianoKeyWrap.innerHTML = '<div id="piano-keys-container"></div>';
    const keysContainer = document.getElementById('piano-keys-container');

    let html = '';

    // 先绘制所有白键
    const whiteKeys = Notes.Piano.filter(note => note.type === 'white');
    html += whiteKeys.map(note => `
      <div class="piano-key wkey" data-keycode="${note.keyCode}" data-name="${note.name}">
        <div class="keytip">
          <div class="keyname" ${!this.showKeyName ? 'style="display:none"' : ''}>${note.key}</div>
          <div class="notename" ${!this.showNoteName ? 'style="display:none"' : ''}>${note.name}</div>
        </div>
      </div>
    `).join('');

    // 再绘制黑键，但排除C7组最后三个黑键（F#7, G#7, A#7）
    const blackKeys = Notes.Piano.filter(note =>
      note.type === 'black' &&
      !['F#7', 'G#7', 'A#7'].includes(note.name)
    );

    html += blackKeys.map(note => `
      <div class="piano-key bkey" data-keycode="${note.keyCode}" data-name="${note.name}">
        <div class="keytip">
          <div class="keyname" ${!this.showKeyName ? 'style="display:none"' : ''}>${note.key}</div>
        </div>
      </div>
    `).join('');

    // 添加到容器DOM
    keysContainer.innerHTML = html;

    // 绑定点击事件
    const pianoKeys = document.querySelectorAll('.piano-key');
    pianoKeys.forEach(key => {
      key.addEventListener('mousedown', async (e) => {
        // 确保点击时启动AudioContext
        await this.startAudioContext();

        const keyCode = key.getAttribute('data-keycode');
        this.clickPianoKey(e, keyCode);
      });
    });

    // 验证黑白键布局
    console.log("已渲染键盘布局: 白键数量 =", whiteKeys.length, "黑键数量 =", blackKeys.length);
  }

  // 键盘事件绑定
  bindKeyboardEvent() {
    const ShiftKeyCode = 16;

    document.addEventListener('keydown', async (e) => {
      // 确保按键时启动AudioContext
      await this.startAudioContext();

      let keyCode = e.keyCode;

      // 按住Shift键，则启用黑色按键
      if (keyCode == ShiftKeyCode) {
        this.enableBlackKey = true;
        return;
      }

      if (this.enableBlackKey) keyCode = 'b' + keyCode;

      if (keyCode == this.lastKeyCode) {
        // 连续触发同一个键时，应节流 + 延音
        if (!this.keyLock) {
          this.playNoteByKeyCode(keyCode);
          this.lastKeyCode = keyCode;
          this.keyLock = true;
        }

        if (this.keydownTimer) {
          clearTimeout(this.keydownTimer);
          this.keydownTimer = null;
        }

        this.keydownTimer = setTimeout(() => {
          this.keyLock = false;
        }, 120);
      } else {
        this.playNoteByKeyCode(keyCode);
        this.lastKeyCode = keyCode;
      }
    });

    document.addEventListener('keyup', (e) => {
      let keyCode = e.keyCode;

      // 释放Shift键，则禁用黑色按键
      if (keyCode == ShiftKeyCode) {
        this.enableBlackKey = false;
        return;
      }

      if (keyCode == this.lastKeyCode) {
        this.lastKeyCode = '';
      }
    });
  }

  // 通过键码获取音符对象
  getNoteByKeyCode(keyCode) {
    return Notes.Piano.find(note => note.keyCode == keyCode) || null;
  }

  // 通过音名获取音符对象
  getNoteByName(name = 'C4') {
    return Notes.Piano.find(note => note.name == name) || null;
  }

  // 触发按键视觉效果
  triggerKeyEffect(key, duration = 300) {
    if (!key) return;

    const keyClass = key.classList.contains('wkey') ? 'wkey' : 'bkey';
    key.classList.add(keyClass + '-active');

    // 指定时间后移除active样式
    setTimeout(() => {
      key.classList.remove(keyClass + '-active');
    }, duration);
  }

  // 点击钢琴键处理
  clickPianoKey(e, keyCode) {
    let target = e.target;
    // 确保我们点击的是钢琴键本身
    while (target && !target.classList.contains('piano-key')) {
      target = target.parentElement;
    }

    if (!target) return;

    // 添加视觉效果
    this.triggerKeyEffect(target);

    // 播放声音
    this.playNoteByKeyCode(keyCode);
  }

  // 通过键码播放音符
  async playNoteByKeyCode(keyCode) {
    const note = this.getNoteByKeyCode(keyCode);
    if (!note) return;

    // 将note.name的第一个字母由大写变为小写
    const lowerCaseNoteName = note.name.charAt(0).toLowerCase() + note.name.slice(1);

    // 添加视觉效果
    const key = document.querySelector(`.piano-key[data-keycode="${keyCode}"]`);
    this.triggerKeyEffect(key);

    // 播放音符
    try {
      await this.playNote(note.name);
    } catch (err) {
      console.error('播放音符失败:', err);
    }

    console.log(`Store note: ${note.name}`);
    const beginTag = localStorage.getItem('beginTag');
    if (beginTag === 'True') this.noteStorage(lowerCaseNoteName);
  }

  //音符字符串的存储
  noteStorage(noteName) {
    const storageKey = 'playedNotes';
    const playedNotes = JSON.parse(localStorage.getItem(storageKey)) || [];

    playedNotes.push(noteName); // 添加新音符
    localStorage.setItem(storageKey, JSON.stringify(playedNotes)); // 更新存储
  }

  clearStoredNotes() {
    localStorage.removeItem('playedNotes');
    alert('已清空存储的音符');
    localStorage.setItem('beginTag', 'False');
  }

  // 根据音符名称触发键盘效果
  triggerKeyByName(noteName, duration = 300) {
    if (!noteName) return;

    const key = document.querySelector(`.piano-key[data-name="${noteName}"]`);
    this.triggerKeyEffect(key, duration);
  }

  async generateMidiFromStorage() {
    const generateButton = document.getElementById('end');
    const originalHTML = generateButton.innerHTML;
    let midiGenerated = false;

    try {
      // 进入加载状态
      generateButton.innerHTML = `
        <div class="button-loader"></div>
        正在生成...
      `;
      generateButton.disabled = true;

      // 检查本地存储
      const storedNotes = localStorage.getItem('playedNotes');
      if (!storedNotes || JSON.parse(storedNotes).length === 0) {
        throw new Error('没有找到存储的音符数据');
      }

      // 异步生成MIDI数据
      const midiBlob = await new Promise((resolve, reject) => {
        try {
          // 创建MIDI文件
          const file = new Midi.File();
          const track = new Midi.Track();
          file.addTrack(track);

          // MIDI参数设置
          track.setTempo(120);
          track.addEvent(new Midi.MetaEvent({
            type: Midi.MetaEvent.TIME_SIG,
            data: [4, 2, 24, 8]
          }));
          track.setInstrument(0, 0); // 钢琴音色

          // 添加音符事件
          const notes = JSON.parse(storedNotes);
          notes.forEach((noteName, index) => {
            const octave = parseInt(noteName.slice(-1), 1);
            const duration = this.calculateNoteDuration(octave);
            const velocity = Math.floor(Math.random() * 20) + 70;
            track.addNote(0, noteName, duration, 0, velocity);
          });

          // 生成二进制数据
          const bytes = file.toBytes();
          const buffer = new Uint8Array(bytes.split('').map(c => c.charCodeAt(0)));
          resolve(new Blob([buffer], { type: 'audio/midi' }));
        } catch (e) {
          reject(e);
        }
      });


      const filename = 'pianonotes.mid';
      // 创建文件对象
      const midiFile = new File([midiBlob], filename, { type: 'audio/midi' });
      // 显示加载指示器
      this.showLoadingIndicator();

      // 找到文件输入元素和上传按钮
      const fileInput = document.getElementById('file-input');
      const uploadBtn = document.getElementById('upload-btn');
      const selectedFileText = document.getElementById('selected-file');

      // 创建DataTransfer对象并添加文件
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(midiFile);

      // 设置文件输入的文件
      if (fileInput) {
        fileInput.files = dataTransfer.files;

        // 触发change事件，确保文件被正确识别
        const event = new Event('change', { bubbles: true });
        fileInput.dispatchEvent(event);

        // 更新选择文件的显示文本
        if (selectedFileText) {
          selectedFileText.textContent = `已选择: ${filename}`;
        }

        // 启用并自动点击上传按钮
        if (uploadBtn) {
          uploadBtn.disabled = false;
          setTimeout(() => {
            uploadBtn.click();
          }, 500); // 延迟500毫秒确保UI更新完成
        }
      } else {
        console.error('未找到文件输入元素');
        // 隐藏加载指示器，因为无法完成操作
        this.hideLoadingIndicator();
      }

      // 触发下载
      const url = URL.createObjectURL(midiBlob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `composition_${new Date().toISOString().slice(0, 10)}.mid`;
      document.body.appendChild(anchor);
      anchor.click();

      // 清理资源
      setTimeout(() => {
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
      }, 1000);

      midiGenerated = true;
    } catch (error) {
      console.error('MIDI生成失败:', error);
      alert(`生成失败: ${error.message}`);
    } finally {
      // 恢复按钮状态
      generateButton.disabled = false;
      generateButton.innerHTML = midiGenerated
        ? '✓ 生成成功!'
        : originalHTML;

      // 成功状态短暂显示
      if (midiGenerated) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        generateButton.innerHTML = originalHTML;
      }
    }

    this.clearStoredNotes();
  }

  // 辅助方法：计算音符时长
  calculateNoteDuration(octave) {
    const baseDuration = 100; // 基准时长（毫秒）
    const durationMap = {
      3: 1.2,  // 低八度延长
      4: 1.0,   // 标准时长
      5: 0.8,   // 高八度缩短
      6: 0.6
    };
    return Math.floor(baseDuration * (durationMap[octave] || 1.0));
  }

  // 显示加载指示器
  showLoadingIndicator() {
    // 检查是否已存在加载指示器
    let loadingIndicator = document.getElementById('loading-indicator');

    if (!loadingIndicator) {
      // 创建加载指示器
      loadingIndicator = document.createElement('div');
      loadingIndicator.id = 'loading-indicator';
      loadingIndicator.className = 'loading-indicator';
      loadingIndicator.innerHTML = `
          <div class="spinner"></div>
          <p>正在处理MIDI文件并生成乐谱，请稍候...</p>
        `;

      // 插入到可视化琴键和PDF查看器之间
      const pianoComponent = document.getElementById('pianoComponent');
      if (pianoComponent) {
        pianoComponent.parentNode.insertBefore(loadingIndicator, pianoComponent.nextSibling);
      } else {
        // 如果找不到钢琴组件，则插入到body
        document.body.appendChild(loadingIndicator);
      }
    } else {
      // 显示已存在的加载指示器
      loadingIndicator.style.display = 'flex';
    }

    // 添加事件监听器，监听PDF生成完成事件，使用保存的绑定函数引用
    document.addEventListener('pdf-generation-complete', this.boundHideLoadingIndicator);

    // 设置一个超时，如果10秒内没有收到完成事件，也隐藏加载指示器
    setTimeout(() => this.hideLoadingIndicator(), 10000);
  }

  // 隐藏加载指示器
  hideLoadingIndicator() {
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
      loadingIndicator.style.display = 'none';
    }

    // 移除事件监听器，使用保存的绑定函数引用
    document.removeEventListener('pdf-generation-complete', this.boundHideLoadingIndicator);
  }

  // 播放音符
  async playNote(notename = 'C4', duration = '8n') {
    if (!this.audioLoaded || !this.synth) {
      console.warn('音频尚未加载完成');
      return;
    }

    try {
      // 确保AudioContext已启动
      await this.startAudioContext();

      // 触发键盘视觉效果
      this.triggerKeyByName(notename);

      // 播放音符
      this.synth.triggerAttackRelease(notename, duration);
    } catch (e) {
      console.error('播放音符错误:', e);
    }
  }
}

export default Piano; 
