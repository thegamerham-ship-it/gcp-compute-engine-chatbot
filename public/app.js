/**
 * 관동지방 포켓몬 도감 (Pokédex Kanto v1.0) & 간호순 누나 챗봇 프론트엔드
 * Supports:
 * - 1세대 포켓몬 도감 클래식 스타일 UI & 간호순 누나(Nurse Joy) 페르소나
 * - Gemini 3.8 Flash (도감 표준 분석) & 3.7 Flash (고속 검색) 멀티 모델 선택
 * - 멀티턴 대화 세션 유지 (previousInteractionId)
 * - Web Speech API 음성 인식 (한글 음성 지원)
 * - 한글 IME 중복 입력 방지 & 마크다운/코드 블록 렌더링
 */

(() => {
  // 상태 변수
  let activeModel = 'gemini-3.8-flash';
  let previousInteractionId = null;
  let isGenerating = false;
  let speechRecognizer = null;
  let isListening = false;

  const MODEL_META = {
    'gemini-3.8-flash': {
      label: '도감 표준 분석',
      badge: 'Flash 3.8'
    },
    'gemini-3.7-flash': {
      label: '고속 도감 검색',
      badge: 'Flash 3.7'
    },
    'antigravity-preview-05-2026': {
      label: '심층 연구 에이전트',
      badge: 'Agent'
    }
  };

  // DOM 요소 참조
  const geminiApp = document.getElementById('geminiApp');
  const landingView = document.getElementById('landingView');
  const chatView = document.getElementById('chatView');
  const chatMessages = document.getElementById('chatMessages');
  const inputSection = document.getElementById('inputSection');
  const promptInput = document.getElementById('promptInput');
  const sendBtn = document.getElementById('sendBtn');
  const attachBtn = document.getElementById('attachBtn');
  const micBtn = document.getElementById('micBtn');
  const newChatBtn = document.getElementById('newChatBtn');
  const brandBtn = document.getElementById('brandBtn');
  const apiStatusChip = document.getElementById('apiStatusChip');
  const statusText = document.getElementById('statusText');
  const headerModelBadge = document.getElementById('headerModelBadge');

  // 모델 선택기 요소
  const modelSelectBtn = document.getElementById('modelSelectBtn');
  const modelDropdownMenu = document.getElementById('modelDropdownMenu');
  const activeModelLabel = document.getElementById('activeModelLabel');
  const optionModel38 = document.getElementById('optionModel38');
  const optionModel37 = document.getElementById('optionModel37');
  const optionModelAgent = document.getElementById('optionModelAgent');

  // 음성 토스트 요소
  const voiceToast = document.getElementById('voiceToast');
  const voiceStopBtn = document.getElementById('voiceStopBtn');

  // 추천 질문 칩
  const suggestionChips = document.querySelectorAll('.suggestion-chip');

  // --------------------------------------------------------------------------
  // 1. 초기 서버 및 API 상태 확인
  // --------------------------------------------------------------------------
  async function checkServerStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        apiStatusChip.classList.remove('offline');
        apiStatusChip.classList.add('online');
        statusText.textContent = data.hasApiKey ? '도감 시스템 온라인' : 'API 키 등록 필요';
      } else {
        throw new Error('Status check failed');
      }
    } catch (e) {
      apiStatusChip.classList.remove('online');
      apiStatusChip.classList.add('offline');
      statusText.textContent = '도감 시스템 오프라인';
    }
  }

  // --------------------------------------------------------------------------
  // 2. 모델 드롭다운 선택 로직
  // --------------------------------------------------------------------------
  function toggleModelDropdown(e) {
    e.stopPropagation();
    const isExpanded = modelDropdownMenu.classList.toggle('show');
    modelSelectBtn.setAttribute('aria-expanded', isExpanded);
  }

  function closeModelDropdown() {
    if (modelDropdownMenu.classList.contains('show')) {
      modelDropdownMenu.classList.remove('show');
      modelSelectBtn.setAttribute('aria-expanded', 'false');
    }
  }

  function selectModel(modelId) {
    if (activeModel === modelId) {
      closeModelDropdown();
      return;
    }

    activeModel = modelId;
    const meta = MODEL_META[modelId] || { label: '도감 표준 분석', badge: 'Flash 3.8' };

    activeModelLabel.textContent = meta.label;
    if (headerModelBadge) {
      headerModelBadge.textContent = meta.badge;
    }

    optionModel38.classList.toggle('active', modelId === 'gemini-3.8-flash');
    optionModel37.classList.toggle('active', modelId === 'gemini-3.7-flash');
    if (optionModelAgent) {
      optionModelAgent.classList.toggle('active', modelId === 'antigravity-preview-05-2026');
    }

    closeModelDropdown();
  }

  // --------------------------------------------------------------------------
  // 3. 입력 필드 자동 높이 & 전송 버튼 활성화
  // --------------------------------------------------------------------------
  function updateInputState() {
    const val = promptInput.value.trim();
    if (val.length > 0 && !isGenerating) {
      sendBtn.classList.add('active');
      sendBtn.removeAttribute('disabled');
    } else {
      sendBtn.classList.remove('active');
      sendBtn.setAttribute('disabled', 'true');
    }

    // 높이 자동 조절
    promptInput.style.height = 'auto';
    promptInput.style.height = Math.min(promptInput.scrollHeight, 140) + 'px';
  }

  // --------------------------------------------------------------------------
  // 4. 안전한 마크다운 파서
  // --------------------------------------------------------------------------
  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function parseMarkdown(mdText) {
    if (!mdText) return '';

    // 1. 코드 블록 (```lang ... ```)
    const codeBlocks = [];
    let text = mdText.replace(/```([a-zA-Z0-9_\-+]*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const id = `__CODE_BLOCK_${codeBlocks.length}__`;
      const language = lang.trim() || 'code';
      const escapedCode = escapeHtml(code.trim());
      const blockHtml = `
        <div class="code-block-wrapper">
          <div class="code-block-header">
            <span>${language}</span>
            <button class="code-copy-btn" onclick="copyCode(this)">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              <span>복사</span>
            </button>
          </div>
          <pre><code>${escapedCode}</code></pre>
        </div>
      `;
      codeBlocks.push(blockHtml);
      return id;
    });

    // 2. 일반 HTML 이스케이프
    text = escapeHtml(text);

    // 3. 인라인 코드
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 4. 제목 헤딩
    text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // 5. 굵게 및 기울임꼴
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 6. 글머리 기호 목록
    text = text.replace(/^\s*[\-\*]\s+(.*)$/gim, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
    text = text.replace(/<\/ul>\s*<ul>/g, '');

    // 7. 번호 매기기 목록
    text = text.replace(/^\s*(\d+)\.\s+(.*)$/gim, '<li>$2</li>');

    // 8. 문단 및 줄바꿈
    const lines = text.split('\n\n');
    text = lines
      .map((seg) => {
        seg = seg.trim();
        if (!seg) return '';
        if (seg.startsWith('<h') || seg.startsWith('<ul>') || seg.startsWith('__CODE_BLOCK_')) {
          return seg;
        }
        return `<p>${seg.replace(/\n/g, '<br>')}</p>`;
      })
      .join('');

    // 코드 블록 복원
    codeBlocks.forEach((blockHtml, i) => {
      text = text.replace(`__CODE_BLOCK_${i}__`, blockHtml);
      text = text.replace(`<p>__CODE_BLOCK_${i}__</p>`, blockHtml);
    });

    return text;
  }

  // --------------------------------------------------------------------------
  // 5. 대화 인터랙션 제어
  // --------------------------------------------------------------------------
  function enterChatMode() {
    if (!geminiApp.classList.contains('in-chat')) {
      geminiApp.classList.add('in-chat');
      landingView.classList.add('hidden');
      landingView.style.display = 'none';
      chatView.classList.remove('hidden');
      chatView.style.display = 'flex';
    }
  }

  function resetChat() {
    previousInteractionId = null;
    isGenerating = false;
    chatMessages.innerHTML = '';
    geminiApp.classList.remove('in-chat');
    chatView.classList.add('hidden');
    chatView.style.display = 'none';
    landingView.classList.remove('hidden');
    landingView.classList.remove('fade-out');
    landingView.style.display = 'flex';
    promptInput.value = '';
    updateInputState();
    promptInput.focus();
  }

  function scrollToBottom(smooth = true) {
    requestAnimationFrame(() => {
      chatView.scrollTo({
        top: chatView.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto'
      });
    });
  }

  // 트레이너 (사용자) 메시지 추가
  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row user';

    const wrapper = document.createElement('div');
    wrapper.className = 'user-content-wrapper';

    const userTag = document.createElement('div');
    userTag.className = 'user-tag';
    userTag.textContent = '🔴 트레이너';

    const bubble = document.createElement('div');
    bubble.className = 'user-bubble';
    bubble.textContent = text;

    wrapper.appendChild(userTag);
    wrapper.appendChild(bubble);
    row.appendChild(wrapper);

    chatMessages.appendChild(row);
    scrollToBottom(false);
    return row;
  }

  // 간호순 누나 (AI 어시스턴트) 답변 플레이스홀더 생성
  function appendAssistantPlaceholder(modelName) {
    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const avatar = document.createElement('div');
    avatar.className = 'assistant-avatar pokedex-joy-avatar';
    avatar.innerHTML = `
      <img src="/nurse_joy.jpg" alt="간호순 누나" class="nurse-joy-chat-avatar" onerror="this.src='/nurse_joy.jpg'" />
    `;

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'assistant-content-wrapper';

    // 간호순 누나 & 모델 태그
    const meta = document.createElement('div');
    meta.className = 'assistant-meta';
    meta.innerHTML = `<span class="assistant-model-pill">💖 간호순 누나 · ${modelName}</span>`;

    // 도감 사고 및 검색 카드 (Thinking Box)
    const thoughtCard = document.createElement('div');
    thoughtCard.className = 'thought-card';
    thoughtCard.innerHTML = `
      <div class="thought-header">
        <div class="thought-title-group">
          <span class="thought-sparkle">✦</span>
          <span class="thought-title-text">도감 데이터베이스 검색 및 분석 중...</span>
        </div>
        <button class="thought-toggle-btn" type="button">숨기기</button>
      </div>
      <div class="thought-body">
        트레이너님의 질문을 관동 도감 데이터와 비교하여 최선의 가이드를 준비하고 있어요.
      </div>
    `;

    // 토글 이벤트
    const toggleBtn = thoughtCard.querySelector('.thought-toggle-btn');
    const thoughtBody = thoughtCard.querySelector('.thought-body');
    toggleBtn.addEventListener('click', () => {
      const isHidden = thoughtBody.classList.toggle('hidden');
      toggleBtn.textContent = isHidden ? '펼치기' : '숨기기';
    });

    // 본문 컨테이너 (로딩 도트 포함)
    const body = document.createElement('div');
    body.className = 'assistant-body';
    body.innerHTML = `
      <div class="loading-dots">
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
      </div>
    `;

    contentWrapper.appendChild(meta);
    contentWrapper.appendChild(thoughtCard);
    contentWrapper.appendChild(body);

    row.appendChild(avatar);
    row.appendChild(contentWrapper);
    chatMessages.appendChild(row);
    scrollToBottom();

    return { row, thoughtCard, body };
  }

  // 메시지 전송 로직
  async function handleSend() {
    const text = promptInput.value.trim();
    if (!text || isGenerating) return;

    isGenerating = true;
    updateInputState();
    promptInput.value = '';
    promptInput.style.height = 'auto';

    enterChatMode();
    appendUserMessage(text);

    let modelDisplayName = '도감 표준 분석';
    if (activeModel === 'gemini-3.7-flash') modelDisplayName = '고속 검색';
    if (activeModel === 'antigravity-preview-05-2026') modelDisplayName = '심층 연구';
    const { thoughtCard, body } = appendAssistantPlaceholder(modelDisplayName);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input: text,
          model: activeModel,
          previousInteractionId: previousInteractionId
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || '답변을 생성하지 못했습니다.');
      }

      // 멀티턴 세션 ID 갱신
      if (data.interactionId) {
        previousInteractionId = data.interactionId;
      }

      // 생각 카드 완료 업데이트
      const thoughtTitle = thoughtCard.querySelector('.thought-title-text');
      thoughtTitle.textContent = '도감 데이터 검색 완료';
      const thoughtBody = thoughtCard.querySelector('.thought-body');

      let toolsText = '';
      if (data.toolsUsed) {
        const used = [];
        if (data.toolsUsed.googleSearch) used.push('🔍 실시간 포켓몬 생태 검색');
        if (data.toolsUsed.codeExecution) used.push('💻 도감 통계 계산 엔진');
        if (used.length > 0) {
          toolsText = `<br><span style="display:inline-block; margin-top:4px; font-size:0.78rem; color:#4ade80;">연동 시스템: ${used.join(', ')}</span>`;
        }
      }

      thoughtBody.innerHTML = `간호순 누나가 트레이너님을 위한 포켓몬 도감 조언을 정리했습니다!${toolsText}`;

      // 마크다운 답변 렌더링
      body.innerHTML = parseMarkdown(data.reply);

      // 답변 복사 버튼 추가
      const actionRow = document.createElement('div');
      actionRow.className = 'assistant-actions';
      actionRow.innerHTML = `
        <button class="action-icon-btn copy-reply-btn" title="답변 복사">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
          <span>복사</span>
        </button>
      `;

      actionRow.querySelector('.copy-reply-btn').addEventListener('click', () => {
        navigator.clipboard.writeText(data.reply).then(() => {
          const span = actionRow.querySelector('span');
          span.textContent = '복사됨!';
          setTimeout(() => (span.textContent = '복사'), 2000);
        });
      });

      body.parentElement.appendChild(actionRow);
    } catch (err) {
      body.innerHTML = `
        <div style="color: #ff6b8b; font-size: 0.95rem; padding: 6px 0;">
          ⚠️ ${escapeHtml(err.message)}
        </div>
      `;
      thoughtCard.style.display = 'none';
    } finally {
      isGenerating = false;
      updateInputState();
      scrollToBottom();
      promptInput.focus();
    }
  }

  // --------------------------------------------------------------------------
  // 6. 코드 블록 복사 전역 함수
  // --------------------------------------------------------------------------
  window.copyCode = function (btn) {
    const pre = btn.closest('.code-block-wrapper').querySelector('pre code');
    if (!pre) return;
    navigator.clipboard.writeText(pre.innerText).then(() => {
      const span = btn.querySelector('span');
      if (span) {
        const orig = span.textContent;
        span.textContent = '복사됨!';
        setTimeout(() => (span.textContent = orig), 2000);
      }
    });
  };

  // --------------------------------------------------------------------------
  // 7. 음성 인식 (Web Speech API)
  // --------------------------------------------------------------------------
  function initSpeechRecognition() {
    const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechClass) {
      micBtn.title = '이 브라우저는 음성 인식을 지원하지 않습니다.';
      return;
    }

    speechRecognizer = new SpeechClass();
    speechRecognizer.lang = 'ko-KR';
    speechRecognizer.continuous = false;
    speechRecognizer.interimResults = true;

    speechRecognizer.onstart = () => {
      isListening = true;
      micBtn.classList.add('listening');
      voiceToast.classList.remove('hidden');
    };

    speechRecognizer.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      promptInput.value = transcript;
      updateInputState();
    };

    speechRecognizer.onerror = (event) => {
      console.warn('Speech recognition error:', event.error);
      stopSpeechRecognition();
    };

    speechRecognizer.onend = () => {
      stopSpeechRecognition();
    };
  }

  function toggleSpeechRecognition() {
    if (!speechRecognizer) {
      alert('현재 브라우저 환경에서는 Web Speech API 음성 인식을 지원하지 않습니다. Chrome 브라우저 사용을 권장합니다.');
      return;
    }

    if (isListening) {
      speechRecognizer.stop();
    } else {
      try {
        speechRecognizer.start();
      } catch (e) {
        console.warn('Speech start error:', e);
      }
    }
  }

  function stopSpeechRecognition() {
    isListening = false;
    micBtn.classList.remove('listening');
    voiceToast.classList.add('hidden');
  }

  // --------------------------------------------------------------------------
  // 8. 이벤트 리스너 등록
  // --------------------------------------------------------------------------
  promptInput.addEventListener('input', updateInputState);

  promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      // 한글 IME 조합 중(e.isComposing 또는 keyCode 229) 엔터 중복 발송 방지
      if (e.isComposing || e.keyCode === 229) {
        return;
      }
      e.preventDefault();
      handleSend();
    }
  });

  sendBtn.addEventListener('click', handleSend);

  attachBtn.addEventListener('click', () => {
    promptInput.focus();
    alert('포켓몬 사진 판별 기능은 추후 업데이트 예정입니다. 질문을 바로 입력해 보세요!');
  });

  // 모델 드롭다운
  modelSelectBtn.addEventListener('click', toggleModelDropdown);
  optionModel38.addEventListener('click', () => selectModel('gemini-3.8-flash'));
  optionModel37.addEventListener('click', () => selectModel('gemini-3.7-flash'));
  if (optionModelAgent) {
    optionModelAgent.addEventListener('click', () => selectModel('antigravity-preview-05-2026'));
  }

  document.addEventListener('click', (e) => {
    if (!modelSelectBtn.contains(e.target) && !modelDropdownMenu.contains(e.target)) {
      closeModelDropdown();
    }
  });

  // 마이크 버튼
  micBtn.addEventListener('click', toggleSpeechRecognition);
  voiceStopBtn.addEventListener('click', () => {
    if (speechRecognizer) speechRecognizer.stop();
  });

  // 대화 초기화 및 도감 브랜드 클릭
  newChatBtn.addEventListener('click', resetChat);
  brandBtn.addEventListener('click', resetChat);

  // 추천 질문 칩 클릭
  suggestionChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) {
        promptInput.value = prompt;
        updateInputState();
        handleSend();
      }
    });
  });

  // --------------------------------------------------------------------------
  // 9. 초기 로드
  // --------------------------------------------------------------------------
  checkServerStatus();
  initSpeechRecognition();
  updateInputState();
  promptInput.focus();
})();
