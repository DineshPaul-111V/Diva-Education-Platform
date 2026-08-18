
    const sections = [];
    const clientQuiz = [];
    
    // ── Supported Indian & Global Languages Configuration ──
    const INDIAN_LANG_CONFIG = {
        'English': { code: 'en-US', label: '🇬🇧 English', prefixes: ['en'], names: ['Natural', 'Jenny', 'Samantha', 'Google UK English Female', 'Victoria', 'en-US', 'en-IN'] },
        'Tamil':   { code: 'ta-IN', label: '🇮🇳 தமிழ் (Tamil)', prefixes: ['ta'], names: ['tamil', 'தமிழ்', 'ta-in', 'valluvar', 'iniya'] },
        'Telugu':  { code: 'te-IN', label: '🇮🇳 తెలుగు (Telugu)', prefixes: ['te'], names: ['telugu', 'తెలుగు', 'te-in', 'mohan', 'shruti'] },
        'Bengali': { code: 'bn-IN', label: '🇮🇳 বাংলা (Bengali)', prefixes: ['bn'], names: ['bengali', 'bangla', 'বাংলা', 'bn-in', 'bn-bd', 'tanishaa', 'bashkar'] },
        'Marathi': { code: 'mr-IN', label: '🇮🇳 मराठी (Marathi)', prefixes: ['mr'], names: ['marathi', 'मराठी', 'mr-in', 'aarohi', 'manohar'] },
        'Hindi':   { code: 'hi-IN', label: '🇮🇳 हिंदी (Hindi)', prefixes: ['hi'], names: ['hindi', 'हिंदी', 'hi-in', 'madhur', 'swara', 'kalpana'] }
    };

    function getActiveLanguage() {
        const match = document.cookie.match(/(^| )preferred_language=([^;]+)/);
        if (match) {
            const decoded = decodeURIComponent(match[2]);
            if (INDIAN_LANG_CONFIG[decoded]) return decoded;
            const lower = decoded.toLowerCase();
            for (let k in INDIAN_LANG_CONFIG) {
                if (k.toLowerCase() === lower) return k;
            }
        }
        return 'English';
    }

    function syncVoicePlayerLanguageUI() {
        const activeLang = getActiveLanguage();
        const cfg = INDIAN_LANG_CONFIG[activeLang] || INDIAN_LANG_CONFIG['English'];
        
        const badge = document.getElementById('player-lang-badge');
        if (badge) badge.innerText = cfg.label;

        const select = document.getElementById('voice-player-lang-select');
        if (select) select.value = activeLang;

        const sub = document.getElementById('player-status-subtitle');
        if (sub && (typeof isNarratingSection === 'undefined' || !isNarratingSection)) {
            sub.innerText = `Narrating with Diva AI Voice in ${cfg.label}`;
        }
    }

    function changeVoiceLanguage(lang) {
        document.cookie = "preferred_language=" + encodeURIComponent(lang) + "; path=/; max-age=31536000";
        syncVoicePlayerLanguageUI();
        if (typeof initSpeechSynthesis === 'function') initSpeechSynthesis();
        if (typeof recognition !== 'undefined' && recognition) {
            const cfg = INDIAN_LANG_CONFIG[lang] || INDIAN_LANG_CONFIG['English'];
            recognition.lang = cfg.code;
        }
        const navSel = document.getElementById('languageSelector');
        if (navSel) navSel.value = lang;
    }

    let activeSecIdx = 0;
    let viewedSections = new Set();
    let quizSelectedAnswers = {}; // Map of questionId -> optionIndex

    // ── Configure Mermaid.js for modern interactive flowcharts ──
    if (typeof mermaid !== 'undefined') {
        try {
            mermaid.initialize({
                startOnLoad: false,
                theme: 'dark',
                themeVariables: {
                    darkMode: true,
                    background: '#0b0f19',
                    primaryColor: '#6366f1',
                    primaryTextColor: '#f8fafc',
                    primaryBorderColor: '#818cf8',
                    lineColor: '#38bdf8',
                    secondaryColor: '#0f172a',
                    tertiaryColor: '#1e1b4b'
                }
            });
        } catch (e) {
            console.warn("Mermaid init notice:", e);
        }
    }

    // ── Configure Marked Renderer for Mermaid & Code blocks ──
    const customRenderer = new marked.Renderer();
    const defaultCodeRenderer = customRenderer.code.bind(customRenderer);
    customRenderer.code = function(code, language) {
        if (language === 'mermaid') {
            return `<div class="mermaid">${code}</div>`;
        }
        return defaultCodeRenderer(code, language);
    };
    marked.setOptions({ renderer: customRenderer, breaks: true });

    // ── Universal Numeral & Code Normalizer (All Languages & Scripts) ──
    function normalizeNumeralsClient(text) {
        if (!text) return "";
        const numeralMap = {
            '०':'0','१':'1','२':'2','३':'3','४':'4','५':'5','६':'6','७':'7','८':'8','९':'9',
            '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9',
            '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9',
            '௦':'0','௧':'1','௨':'2','௩':'3','௪':'4','௫':'5','௬':'6','௭':'7','௮':'8','௯':'9',
            '౦':'0','౧':'1','౨':'2','౩':'3','౪':'4','౫':'5','౬':'6','౭':'7','౮':'8','౯':'9',
            '০':'0','১':'1','২':'2','৩':'3','৪':'4','৫':'5','৬':'6','৭':'7','৮':'8','৯':'9'
        };
        return text.replace(/[०-९٠-٩۰-۹௦-௯౦-౯০-৯]/g, m => numeralMap[m] || m);
    }

    // ── Auto-Fence ASCII Art / Box Diagrams ──
    function autoFenceAsciiArtClient(markdownText) {
        if (!markdownText) return "";
        if (markdownText.includes('\\n')) {
            markdownText = markdownText.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\t/g, '\t');
        }
        markdownText = markdownText.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        markdownText = normalizeNumeralsClient(markdownText);
        const lines = markdownText.split("\n");
        const newLines = [];
        let inCodeBlock = false;
        let asciiBuffer = [];

        function isAsciiLine(line) {
            const t = line.trim();
            if (!t) return false;
            if (/^\|[^|]+\|.*\|$/.test(t)) return false; // markdown table
            if (/^\+[-+=]+\+.*$/.test(t)) return true;
            if ((t.includes("| ----") || t.includes("| --->") || t.includes("+ --->") || t.includes("---->")) && (t.includes("|") || t.includes("+"))) return true;
            if (t.startsWith("+--") || t.endsWith("--+")) return true;
            return false;
        }

        for (const line of lines) {
            if (line.trim().startsWith("```")) {
                if (asciiBuffer.length > 0) {
                    newLines.push("```text");
                    newLines.push(...asciiBuffer);
                    newLines.push("```");
                    asciiBuffer = [];
                }
                inCodeBlock = !inCodeBlock;
                newLines.push(line);
                continue;
            }
            if (inCodeBlock) {
                newLines.push(line);
                continue;
            }
            if (isAsciiLine(line)) {
                asciiBuffer.push(line);
            } else {
                if (asciiBuffer.length > 0) {
                    newLines.push("```text");
                    newLines.push(...asciiBuffer);
                    newLines.push("```");
                    asciiBuffer = [];
                }
                newLines.push(line);
            }
        }
        if (asciiBuffer.length > 0) {
            newLines.push("```text");
            newLines.push(...asciiBuffer);
            newLines.push("```");
        }
        return newLines.join("\n");
    }

    // ── Voice & Audio Visualizer State ──
    let voiceTTSEnabled = true;
    let isListening = false;
    let isSpeaking = false;
    let recognition = null;
    let voiceChartCanvas = null;
    let voiceChartCtx = null;
    let animationFrameId = null;
    let voiceChartActive = true;
    let preferredDivaVoice = null;

    function safeCreateIcons() {
        try {
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        } catch (e) {
            console.warn("Lucide icons failed to load or render:", e);
        }
    }

    document.addEventListener("DOMContentLoaded", function() {
        // Sync voice player language UI with cookie
        syncVoicePlayerLanguageUI();

        // Load first section
        setActiveSection(0);
        
        // Initialize Voice Visualizers and Speech Synthesis
        initVoiceChartVisualizer();
        initPlayerSpectrum();
        initSpeechSynthesis();
        initSpeechRecognition();
    });

    function setActiveSection(idx) {
        if (idx < 0 || idx >= sections.length) return;
        activeSecIdx = idx;
        viewedSections.add(idx);
        
        // Hide other panels
        document.getElementById('subtopic-panel').classList.remove('hidden');
        document.getElementById('quiz-panel').classList.add('hidden');
        document.getElementById('remediation-panel').classList.add('hidden');

        // Toggle Active styles on TOC
        for (let i = 0; i < sections.length; i++) {
            const btn = document.getElementById(`toc-btn-${i}`);
            if (btn) {
                if (i === idx) {
                    btn.className = "w-full flex items-center justify-between text-left p-3 rounded-xl border border-brand-500 bg-brand-500/10 text-white transition-all duration-200";
                } else {
                    btn.className = "w-full flex items-center justify-between text-left p-3 rounded-xl border border-white/5 bg-dark-900/40 hover:bg-white/5 transition-all duration-200";
                }
            }
            
            // Mark viewed icons
            const tocCheck = document.getElementById(`toc-check-${i}`);
            if (tocCheck && viewedSections.has(i)) {
                tocCheck.innerHTML = '<i data-lucide="check" class="w-3 h-3 text-emerald-400"></i>';
            }
        }
        document.getElementById('toc-btn-quiz').classList.remove('border-brand-500', 'bg-brand-500/20');
        document.getElementById('toc-btn-quiz').classList.add('border-brand-500/20', 'bg-brand-500/10');

        const sec = sections[idx];
        document.getElementById('section-badge').innerText = `Section ${idx + 1} of ${sections.length}`;
        document.getElementById('section-title').innerText = sec.title;
        
        // Format & render markdown with auto-fenced ASCII and Mermaid
        const rawContent = sec.content || '';
        const safeMarkdown = autoFenceAsciiArtClient(rawContent);
        document.getElementById('section-markdown-content').innerHTML = marked.parse(safeMarkdown);
        
        // Enhance all code blocks with 1-click Copy and Run in Runner buttons
        decorateCodeBlocks();

        // Render any Mermaid flowcharts/diagrams
        if (typeof mermaid !== 'undefined') {
            setTimeout(() => {
                const nodes = document.querySelectorAll('#section-markdown-content .mermaid');
                if (nodes.length > 0) {
                    mermaid.run({ nodes: nodes }).catch(err => console.warn("Mermaid render notice:", err));
                }
            }, 60);
        }
        
        // Example box
        if (sec.example) {
            document.getElementById('section-example-box').classList.remove('hidden');
            document.getElementById('section-example-content').innerText = sec.example;
        } else {
            document.getElementById('section-example-box').classList.add('hidden');
        }

        // Update Prev / Next button states
        const prevBtn = document.getElementById('prev-sec-btn');
        const nextBtn = document.getElementById('next-sec-btn');
        const nextText = document.getElementById('next-sec-text');

        if (idx === 0) {
            prevBtn.classList.add('opacity-40', 'pointer-events-none');
        } else {
            prevBtn.classList.remove('opacity-40', 'pointer-events-none');
        }

        if (idx === sections.length - 1) {
            nextText.innerText = "Proceed to Mastery Quiz";
        } else {
            nextText.innerText = "Next Section";
        }

        // Render 3 Practice MCQs for this section
        renderSectionMCQs(idx);

        safeCreateIcons();
    }

    // ── Module Practice MCQs (3 questions per section) ──
    let sectionMCQState = {}; // Key: `${secIdx}_${qIdx}` -> { selectedChoice: int, isCorrect: bool }

    function renderSectionMCQs(secIdx) {
        const container = document.getElementById('section-mcq-list');
        const badge = document.getElementById('mcq-status-badge');
        if (!container) return;

        const sec = sections[secIdx];
        if (!sec) return;

        const mcqs = sec.mcqQuestions || [];
        if (mcqs.length === 0) {
            document.getElementById('section-mcq-box').classList.add('hidden');
            return;
        }
        document.getElementById('section-mcq-box').classList.remove('hidden');

        let answeredCount = 0;
        let correctCount = 0;
        container.innerHTML = '';

        const optionLetters = ['A', 'B', 'C', 'D'];

        mcqs.forEach((mcq, qIdx) => {
            const stateKey = `${secIdx}_${qIdx}`;
            const state = sectionMCQState[stateKey];
            const hasAnswered = state !== undefined;
            if (hasAnswered) {
                answeredCount++;
                if (state.isCorrect) correctCount++;
            }

            let optionsHtml = '';

            mcq.options.forEach((opt, oIdx) => {
                let btnStyle = 'border-white/10 hover:bg-white/5 hover:border-brand-500/30 text-gray-300';
                let letterStyle = 'bg-white/10 text-gray-400 border-white/10 group-hover:bg-brand-500/20 group-hover:text-brand-300';
                let checkIcon = '';

                if (hasAnswered) {
                    if (oIdx === mcq.correctIndex) {
                        btnStyle = 'border-emerald-500 bg-emerald-500/15 text-emerald-200 font-semibold shadow-lg shadow-emerald-500/10';
                        letterStyle = 'bg-emerald-500 text-dark-950 font-bold border-emerald-400';
                        checkIcon = '<i data-lucide="check-circle" class="w-4 h-4 text-emerald-400 ml-auto flex-shrink-0"></i>';
                    } else if (state.selectedChoice === oIdx && !state.isCorrect) {
                        btnStyle = 'border-rose-500 bg-rose-500/15 text-rose-200 font-medium';
                        letterStyle = 'bg-rose-500 text-white font-bold border-rose-400';
                        checkIcon = '<i data-lucide="x-circle" class="w-4 h-4 text-rose-400 ml-auto flex-shrink-0"></i>';
                    } else {
                        btnStyle = 'border-white/5 opacity-40 text-gray-500';
                    }
                }

                const clickHandler = hasAnswered ? '' : `onclick="selectSectionMCQOption(${secIdx}, ${qIdx}, ${oIdx})"`;

                optionsHtml += `
                    <button type="button" ${clickHandler} class="w-full flex items-center p-3.5 rounded-xl border ${btnStyle} transition-all duration-200 text-left text-xs md:text-sm group ${hasAnswered ? 'cursor-default' : 'cursor-pointer'}">
                        <span class="w-6 h-6 rounded-lg ${letterStyle} flex items-center justify-center text-xs font-bold mr-3 flex-shrink-0 border transition">
                            ${optionLetters[oIdx] || (oIdx + 1)}
                        </span>
                        <span class="flex-grow">${opt}</span>
                        ${checkIcon}
                    </button>
                `;
            });

            // Explanation / feedback card
            let explanationHtml = '';
            if (hasAnswered) {
                const expBorder = state.isCorrect ? 'border-emerald-500/30 bg-emerald-950/40 text-emerald-300' : 'border-rose-500/30 bg-rose-950/30 text-rose-300';
                const statusTitle = state.isCorrect ? '✓ Correct Answer!' : '✗ Needs review';
                explanationHtml = `
                    <div class="p-3.5 rounded-xl border ${expBorder} text-xs space-y-1 mt-2">
                        <div class="font-bold flex items-center space-x-1.5">
                            <span>${statusTitle}</span>
                        </div>
                        <p class="text-gray-300 leading-relaxed text-[11px] md:text-xs">${mcq.explanation || 'Key concept reinforced for this module.'}</p>
                    </div>
                `;
            }

            container.innerHTML += `
                <div class="p-5 rounded-2xl bg-dark-900/60 border border-white/5 space-y-3">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center space-x-2">
                            <span class="text-[11px] font-bold uppercase tracking-wider text-brand-400">
                                Question ${qIdx + 1} of ${mcqs.length}
                            </span>
                            <button onclick="narrateMcq(${secIdx}, ${qIdx})" class="bg-brand-600/15 hover:bg-brand-600/25 text-brand-300 border border-brand-500/20 px-2 py-0.5 rounded text-[10px] font-semibold flex items-center space-x-1 transition cursor-pointer" title="Listen to question in Diva Voice">
                                <i data-lucide="volume-2" class="w-3 h-3"></i>
                                <span>Listen</span>
                            </button>
                        </div>
                        ${hasAnswered ? `<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full ${state.isCorrect ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'}">${state.isCorrect ? '+10 XP Earned' : 'Reviewed'}</span>` : ''}
                    </div>
                    <p class="text-sm font-semibold text-white leading-snug">${mcq.question}</p>
                    <div class="grid grid-cols-1 gap-2.5 pt-1">
                        ${optionsHtml}
                    </div>
                    ${explanationHtml}
                </div>
            `;
        });

        // Update status badge
        if (badge) {
            if (answeredCount === mcqs.length) {
                badge.innerText = `Score: ${correctCount} / ${mcqs.length} Correct`;
                badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30";
            } else {
                badge.innerText = `${answeredCount} of ${mcqs.length} Answered`;
                badge.className = "text-xs font-semibold px-3 py-1 rounded-full bg-brand-500/10 text-brand-300 border border-brand-500/20";
            }
        }

        safeCreateIcons();
    }

    function selectSectionMCQOption(secIdx, qIdx, oIdx) {
        const sec = sections[secIdx];
        if (!sec || !sec.mcqQuestions) return;
        const mcq = sec.mcqQuestions[qIdx];
        if (!mcq) return;

        const isCorrect = (oIdx === mcq.correctIndex);
        const stateKey = `${secIdx}_${qIdx}`;
        sectionMCQState[stateKey] = {
            selectedChoice: oIdx,
            isCorrect: isCorrect
        };

        renderSectionMCQs(secIdx);
    }

    function prevSection() {
        if (activeSecIdx > 0) {
            setActiveSection(activeSecIdx - 1);
            document.getElementById('content-pane').scrollTop = 0;
        }
    }

    function nextSection() {
        if (activeSecIdx < sections.length - 1) {
            setActiveSection(activeSecIdx + 1);
            document.getElementById('content-pane').scrollTop = 0;
        } else {
            showQuizSection();
        }
    }

    function askTutorAboutCurrentTopic() {
        const sec = sections[activeSecIdx];
        const topicName = sec ? sec.title : "[]";
        
        // Ensure tutor drawer is open
        const drawer = document.getElementById('tutor-drawer');
        if (drawer.classList.contains('translate-x-full')) {
            toggleTutorDrawer();
        }
        
        const prompt = `Can you explain "${topicName}" in simple terms with a key example?`;
        appendChatMessage('user', prompt);
        callTutorAPI(prompt);
    }

    function showQuizSection() {
        // Deselect TOC
        for (let i = 0; i < sections.length; i++) {
            const btn = document.getElementById(`toc-btn-${i}`);
            if (btn) btn.className = "w-full flex items-center justify-between text-left p-3 rounded-xl border border-white/5 bg-dark-900/40 hover:bg-white/5 transition-all duration-200";
        }
        const qBtn = document.getElementById('toc-btn-quiz');
        qBtn.className = "w-full flex items-center justify-between text-left p-3.5 rounded-xl border border-brand-500 bg-brand-500/20 text-white transition-all duration-200";

        document.getElementById('subtopic-panel').classList.add('hidden');
        document.getElementById('remediation-panel').classList.add('hidden');
        document.getElementById('flashcard-panel').classList.add('hidden');
        document.getElementById('quiz-panel').classList.remove('hidden');
        document.getElementById('content-pane').scrollTop = 0;

        renderQuiz();
    }

    // ── Active Recall & Concept Flashcards ──
    let flashcards = [];
    let currentCardIdx = 0;
    let cardFlipped = false;
    let masteredCards = new Set();

    function initFlashcards() {
        flashcards = [];
        currentCardIdx = 0;
        cardFlipped = false;
        masteredCards.clear();
        
        sections.forEach((sec, sIdx) => {
            flashcards.push({
                category: "CORE PRINCIPLE",
                front: `What is the core intuition behind "${sec.title}"?`,
                back: `In Diva Ideas architecture, ${sec.title} focuses on mastering the underlying mental model, parameter syntax, and execution flow.`,
                code: sec.example ? sec.example.substring(0, 160) : ""
            });
            
            if (sec.mcqQuestions && sec.mcqQuestions.length > 0) {
                sec.mcqQuestions.forEach((q, qIdx) => {
                    const correctOpt = q.options[q.correctIndex] || "Correct Principle";
                    flashcards.push({
                        category: "DIAGNOSTIC RECALL",
                        front: q.question,
                        back: `✅ Answer: ${correctOpt}\n\n💡 ${q.explanation || 'Key engineering concept.'}`,
                        code: ""
                    });
                });
            }
        });

        if (flashcards.length === 0) {
            flashcards.push({
                category: "SUMMARY",
                front: `Key takeaways for []`,
                back: `Review the syntax blueprint, time complexity bounds, and enterprise patterns.`,
                code: ""
            });
        }
    }

    function showFlashcardsSection() {
        if (flashcards.length === 0) initFlashcards();
        
        for (let i = 0; i < sections.length; i++) {
            const btn = document.getElementById(`toc-btn-${i}`);
            if (btn) btn.className = "w-full flex items-center justify-between text-left p-3 rounded-xl border border-white/5 bg-dark-900/40 hover:bg-white/5 transition-all duration-200";
        }
        const qBtn = document.getElementById('toc-btn-quiz');
        if (qBtn) qBtn.className = "w-full flex items-center justify-between text-left p-3.5 rounded-xl border border-brand-500/20 bg-brand-500/10 hover:bg-brand-500/20 transition-all duration-200";
        
        const fcBtn = document.getElementById('toc-btn-flashcards');
        if (fcBtn) fcBtn.className = "w-full flex items-center justify-between text-left p-3.5 rounded-xl border border-purple-500 bg-purple-500/20 text-white transition-all duration-200";

        document.getElementById('subtopic-panel').classList.add('hidden');
        document.getElementById('quiz-panel').classList.add('hidden');
        document.getElementById('remediation-panel').classList.add('hidden');
        document.getElementById('flashcard-panel').classList.remove('hidden');
        document.getElementById('content-pane').scrollTop = 0;

        renderFlashcard();
    }

    function renderFlashcard() {
        if (flashcards.length === 0) return;
        const card = flashcards[currentCardIdx];
        cardFlipped = false;

        const inner = document.getElementById('flashcard-inner');
        if (inner) inner.classList.remove('flashcard-flipped');

        document.getElementById('card-index-indicator').innerText = `Card ${currentCardIdx + 1} of ${flashcards.length}`;
        document.getElementById('card-front-category').innerText = card.category || 'CONCEPT RECALL';
        document.getElementById('card-front-text').innerText = card.front;
        document.getElementById('card-back-text').innerText = card.back;

        const codeEl = document.getElementById('card-back-code');
        if (card.code && card.code.trim()) {
            codeEl.classList.remove('hidden');
            codeEl.innerText = card.code;
        } else {
            codeEl.classList.add('hidden');
        }

        const dotsContainer = document.getElementById('card-dots-container');
        if (dotsContainer) {
            dotsContainer.innerHTML = flashcards.map((_, i) => {
                let color = 'bg-white/20';
                if (i === currentCardIdx) color = 'bg-brand-500 w-4';
                else if (masteredCards.has(i)) color = 'bg-emerald-400';
                return `<div class="h-1.5 w-1.5 rounded-full ${color} transition-all duration-300"></div>`;
            }).join('');
        }

        const prevBtn = document.getElementById('card-prev-btn');
        if (currentCardIdx === 0) {
            prevBtn.classList.add('opacity-40', 'pointer-events-none');
        } else {
            prevBtn.classList.remove('opacity-40', 'pointer-events-none');
        }

        safeCreateIcons();
    }

    function flipCurrentFlashcard() {
        const inner = document.getElementById('flashcard-inner');
        if (!inner) return;
        cardFlipped = !cardFlipped;
        if (cardFlipped) {
            inner.classList.add('flashcard-flipped');
        } else {
            inner.classList.remove('flashcard-flipped');
        }
    }

    function rateCurrentCard(rating, event) {
        if (event) event.stopPropagation();
        if (rating === 'mastered') {
            masteredCards.add(currentCardIdx);
            if (typeof confetti === 'function') {
                confetti({
                    particleCount: 35,
                    spread: 60,
                    origin: { y: 0.7 }
                });
            }
        }
        if (currentCardIdx < flashcards.length - 1) {
            setTimeout(() => nextFlashcard(), 250);
        } else {
            renderFlashcard();
        }
    }

    function nextFlashcard() {
        if (currentCardIdx < flashcards.length - 1) {
            currentCardIdx++;
            renderFlashcard();
        } else {
            alert("🎉 Awesome! You completed all flashcards in this module. Ready for the Mastery Quiz!");
            showQuizSection();
        }
    }

    function prevFlashcard() {
        if (currentCardIdx > 0) {
            currentCardIdx--;
            renderFlashcard();
        }
    }

    // ── Consolidated Study Guide Modal ──
    function openStudyGuideModal() {
        const modal = document.getElementById('study-guide-modal');
        const content = document.getElementById('study-guide-content');
        if (!modal || !content) return;

        let combinedMarkdown = `# 📖 [] — Complete Study Guide\n\n`;
        combinedMarkdown += `*Domain: [] | Level: []*\n\n---\n\n`;

        sections.forEach((sec, idx) => {
            combinedMarkdown += `## Section ${idx + 1}: ${sec.title}\n\n`;
            combinedMarkdown += `${autoFenceAsciiArtClient(sec.content || '')}\n\n`;
            if (sec.example) {
                combinedMarkdown += `### 💻 Worked Example\n\`\`\`text\n${sec.example}\n\`\`\`\n\n`;
            }
            combinedMarkdown += `---\n\n`;
        });

        content.innerHTML = marked.parse(combinedMarkdown);

        if (typeof mermaid !== 'undefined') {
            setTimeout(() => {
                const nodes = content.querySelectorAll('.mermaid');
                if (nodes.length > 0) {
                    mermaid.run({ nodes: nodes }).catch(e => console.warn(e));
                }
            }, 50);
        }

        modal.classList.remove('hidden');
        safeCreateIcons();
    }

    function closeStudyGuideModal() {
        const modal = document.getElementById('study-guide-modal');
        if (modal) modal.classList.add('hidden');
    }

    // ── Download & Export Helpers ──
    function downloadLessonPDF() {
        window.location.href = "[]";
    }

    // ── 1-Click Code Runner & Copy Decorator ──
    function decorateCodeBlocks() {
        const preBlocks = document.querySelectorAll('#section-markdown-content pre');
        preBlocks.forEach((pre) => {
            if (pre.dataset.decorated === "true") return;
            pre.dataset.decorated = "true";
            pre.classList.add('relative', 'group');

            const code = pre.querySelector('code');
            const codeText = code ? code.innerText : pre.innerText;

            let lang = "CODE";
            if (code && code.className) {
                const m = code.className.match(/language-([a-zA-Z0-9_-]+)/);
                if (m) lang = m[1].toUpperCase();
            }

            const toolbar = document.createElement('div');
            toolbar.className = "absolute top-2.5 right-2.5 flex items-center space-x-1.5 opacity-80 group-hover:opacity-100 transition-opacity z-10 select-none";
            toolbar.innerHTML = `
                <span class="text-[9px] font-mono font-bold px-2 py-0.5 rounded bg-white/10 text-gray-400 border border-white/10 uppercase tracking-wider">${lang}</span>
                <button type="button" class="copy-code-btn text-[10px] font-semibold bg-dark-900/90 hover:bg-dark-800 text-gray-300 hover:text-white border border-white/10 hover:border-brand-500/40 px-2 py-1 rounded-lg flex items-center space-x-1 transition shadow cursor-pointer" title="Copy code">
                    <i data-lucide="copy" class="w-3 h-3"></i>
                    <span>Copy</span>
                </button>
                <button type="button" class="run-code-btn text-[10px] font-semibold bg-emerald-600/90 hover:bg-emerald-500 text-white px-2.5 py-1 rounded-lg flex items-center space-x-1 transition shadow-lg shadow-emerald-500/20 cursor-pointer" title="Run code in live runner">
                    <i data-lucide="play" class="w-3 h-3 fill-current"></i>
                    <span>Run</span>
                </button>
            `;

            const copyBtn = toolbar.querySelector('.copy-code-btn');
            copyBtn.onclick = (e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(codeText);
                const span = copyBtn.querySelector('span');
                span.innerText = "Copied!";
                copyBtn.classList.add('text-emerald-400', 'border-emerald-500/40');
                setTimeout(() => {
                    span.innerText = "Copy";
                    copyBtn.classList.remove('text-emerald-400', 'border-emerald-500/40');
                }, 2000);
            };

            const runBtn = toolbar.querySelector('.run-code-btn');
            runBtn.onclick = (e) => {
                e.stopPropagation();
                sendCodeToRunner(codeText, lang);
            };

            pre.appendChild(toolbar);
        });
        safeCreateIcons();
    }

    function sendCodeToRunner(codeStr, codeLang) {
        if (!codeStr || !codeStr.trim()) return;

        // 1. Detect & set appropriate programming language
        const langSelect = document.getElementById('drawer-lang-select');
        if (langSelect) {
            let detected = (codeLang || "").toLowerCase().trim();
            if (!detected || detected === "code" || detected === "text") {
                const domainStr = "[]".toLowerCase();
                if (domainStr.includes("python")) detected = "python";
                else if (domainStr.includes("sql")) detected = "sql";
                else if (domainStr.includes("rust")) detected = "rust";
                else if (domainStr.includes("go") || domainStr.includes("golang")) detected = "go";
                else if (domainStr.includes("c++") || domainStr.includes("cpp")) detected = "c++";
                else if (domainStr.includes("typescript") || domainStr.includes("ts")) detected = "typescript";
                else if (domainStr.includes("javascript") || domainStr.includes("js") || domainStr.includes("node") || domainStr.includes("react")) detected = "javascript";
                else if (domainStr.includes("java")) detected = "java";
                else if (domainStr.includes(" c ") || domainStr.endsWith(" c")) detected = "c";
                else detected = "python";
            }
            // Normalize aliases
            if (detected === "py" || detected === "python3") detected = "python";
            if (detected === "js" || detected === "node") detected = "javascript";
            if (detected === "ts") detected = "typescript";
            if (detected === "cpp") detected = "c++";
            if (detected === "rs") detected = "rust";
            if (detected === "golang") detected = "go";

            // Check if select has this option
            const hasOption = Array.from(langSelect.options).some(opt => opt.value === detected);
            if (hasOption) {
                langSelect.value = detected;
            }
        }

        // 2. Put cleaned code into editor
        const codeEditor = document.getElementById('drawer-code-editor');
        if (codeEditor) {
            codeEditor.value = cleanCodeSnippet(codeStr);
        }

        // 3. Open runner drawer if currently closed
        const runnerDrawer = document.getElementById('runner-drawer');
        if (runnerDrawer && runnerDrawer.classList.contains('translate-x-full')) {
            toggleRunnerDrawer();
        }

        // 4. Immediately execute code and display results
        runDrawerCode();
    }

    function renderQuiz() {
        const container = document.getElementById('quiz-questions-list');
        container.innerHTML = '';
        clientQuiz.forEach((q, qidx) => {
            let optionsHtml = '';
            q.options.forEach((opt, oidx) => {
                const isSelected = quizSelectedAnswers[q.id] === oidx;
                const borderClass = isSelected ? 'border-brand-500 bg-brand-500/10' : 'border-white/10 hover:bg-white/5';
                const dotClass = isSelected ? 'bg-brand-500 border-brand-500' : 'border-white/20';
                optionsHtml += `
                    <button onclick="selectQuizOption('${q.id}', ${oidx})" class="w-full flex items-center justify-between text-left p-4 rounded-xl border ${borderClass} transition-all duration-200">
                        <span class="text-gray-300 text-sm">${opt}</span>
                        <div class="w-4 h-4 rounded-full border flex items-center justify-center ${dotClass} flex-shrink-0 ml-4">
                            ${isSelected ? '<div class="w-2 h-2 rounded-full bg-white"></div>' : ''}
                        </div>
                    </button>
                `;
            });

            container.innerHTML += `
                <div class="glass p-6 rounded-2xl border shadow-xl space-y-4">
                    <span class="text-xs font-semibold text-gray-400">Question ${qidx + 1}</span>
                    <h3 class="font-bold text-white text-lg">${q.question}</h3>
                    <div class="grid grid-cols-1 gap-3 mt-4">
                        ${optionsHtml}
                    </div>
                </div>
            `;
        });
    }

    function selectQuizOption(qId, oIdx) {
        quizSelectedAnswers[qId] = oIdx;
        renderQuiz();
    }

    function submitQuiz() {
        const total = clientQuiz.length;
        const answersSubmitted = Object.keys(quizSelectedAnswers).length;
        if (answersSubmitted < total) {
            alert("Please answer all questions before submitting.");
            return;
        }

        const formatted = Object.keys(quizSelectedAnswers).map(k => ({
            id: k,
            selectedIndex: quizSelectedAnswers[k]
        }));

        fetch(`/learning/lesson/[]/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answers: formatted })
        })
        .then(res => res.json())
        .then(data => {
            if (data.passed) {
                // Confetti trigger
                try {
                    confetti({
                        particleCount: 100,
                        spread: 70,
                        origin: { y: 0.6 }
                    });
                } catch(e){}
                alert(`Congratulations! You passed with ${data.score}%!`);
                window.location.href = "[]";
            } else {
                // Failed, display remediation
                document.getElementById('quiz-panel').classList.add('hidden');
                document.getElementById('remediation-panel').classList.remove('hidden');
                document.getElementById('remediation-text').innerHTML = marked.parse(data.remediation.remediationText);
                
                // Update quiz variable to load the retry quiz
                clientQuiz.length = 0;
                data.retryQuiz.forEach(q => clientQuiz.push(q));
                quizSelectedAnswers = {};
                document.getElementById('content-pane').scrollTop = 0;
            }
        })
        .catch(err => alert("Failed to submit quiz."));
    }

    function startRetry() {
        document.getElementById('remediation-panel').classList.add('hidden');
        document.getElementById('quiz-panel').classList.remove('hidden');
        renderQuiz();
    }

    // ── AI Tutor Drawer toggle ──
    function toggleTutorDrawer() {
        const drawer = document.getElementById('tutor-drawer');
        const floatingActions = document.getElementById('floating-actions');
        const isClosed = drawer.classList.contains('translate-x-full');
        
        if (isClosed) {
            // Close code runner drawer if open
            const runnerDrawer = document.getElementById('runner-drawer');
            if (!runnerDrawer.classList.contains('translate-x-full')) {
                runnerDrawer.classList.add('translate-x-full');
            }
            drawer.classList.remove('translate-x-full');
            // Hide floating action buttons
            floatingActions.classList.add('opacity-0', 'pointer-events-none', 'translate-x-12');
            setTimeout(() => document.getElementById('tutor-input').focus(), 250);
        } else {
            drawer.classList.add('translate-x-full');
            // Stop speech when drawer closes
            stopAllSpeech();
            // Show floating action buttons again
            floatingActions.classList.remove('opacity-0', 'pointer-events-none', 'translate-x-12');
        }
        safeCreateIcons();
    }

    function sendTutorMessage() {
        const input = document.getElementById('tutor-input');
        const message = input.value.trim();
        if (message === '') return;

        // If currently recognizing speech, stop it
        if (isListening && recognition) {
            recognition.stop();
        }

        appendChatMessage('user', message);
        input.value = '';

        callTutorAPI(message);
    }

    function sendQuickAction(action) {
        appendChatMessage('user', `Quick Action: ${action.replace('_', ' ')}`);
        callTutorAPI(`Perform action: ${action}`, action);
    }

    function callTutorAPI(msg, action = null) {
        const historyDiv = document.getElementById('chat-history');
        // Add loading block
        const loadId = `load-${Date.now()}`;
        historyDiv.innerHTML += `
            <div id="${loadId}" class="bg-brand-500/5 border border-brand-500/10 rounded-2xl p-4 text-gray-300 animate-pulse text-xs flex items-center space-x-2">
                <i data-lucide="sparkles" class="w-3.5 h-3.5 text-brand-400 animate-spin"></i>
                <span>Diva is thinking...</span>
            </div>
        `;
        safeCreateIcons();
        historyDiv.scrollTop = historyDiv.scrollHeight;

        updateVoiceStatus("thinking", "Diva is analyzing context...");

        fetch('/tutor/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                learningPathId: "[]",
                message: msg,
                quickAction: action
            })
        })
        .then(res => res.json())
        .then(data => {
            const loadEl = document.getElementById(loadId);
            if (loadEl) loadEl.remove();
            const reply = data.reply || "I am ready to help.";
            appendChatMessage('bot', reply);
            
            // Speak response if voice TTS is enabled
            if (voiceTTSEnabled) {
                speakDivaResponse(reply);
            } else {
                updateVoiceStatus("idle", "Voice Ready • Click Mic or type");
            }
        })
        .catch(err => {
            const loadEl = document.getElementById(loadId);
            if (loadEl) loadEl.remove();
            appendChatMessage('bot', 'An error occurred while connecting to Diva AI Tutor.');
            updateVoiceStatus("idle", "Ready to talk");
        });
    }

    function appendChatMessage(sender, text) {
        const historyDiv = document.getElementById('chat-history');
        const isUser = sender === 'user';
        const classes = isUser ? 'bg-brand-600 text-white self-end ml-8' : 'bg-white/5 border border-white/5 text-gray-300 mr-4';
        const msgId = `msg-${Date.now()}-${Math.floor(Math.random()*1000)}`;
        
        let audioBtnHtml = '';
        if (!isUser) {
            const cleanText = escapeQuotesForJS(stripMarkdownForTTS(text));
            audioBtnHtml = `
                <div class="flex items-center justify-between pt-2 mt-2 border-t border-white/5 text-[11px]">
                    <span class="text-brand-400 font-medium flex items-center gap-1">
                        <i data-lucide="sparkles" class="w-3 h-3"></i> Diva AI
                    </span>
                    <button onclick="speakDivaResponse('${cleanText}')" class="text-gray-400 hover:text-brand-300 flex items-center space-x-1 transition" title="Listen to this explanation">
                        <i data-lucide="volume-2" class="w-3.5 h-3.5"></i>
                        <span>Listen</span>
                    </button>
                </div>
            `;
        }

        historyDiv.innerHTML += `
            <div id="${msgId}" class="p-3.5 rounded-2xl ${classes} text-xs space-y-1">
                <div>${isUser ? text : marked.parse(text)}</div>
                ${audioBtnHtml}
            </div>
        `;
        historyDiv.scrollTop = historyDiv.scrollHeight;
        safeCreateIcons();

        // Render any Mermaid diagrams in the AI response
        if (!isUser && typeof mermaid !== 'undefined') {
            setTimeout(() => {
                const chatMermaidNodes = document.querySelectorAll(`#${msgId} .mermaid`);
                if (chatMermaidNodes.length > 0) {
                    mermaid.run({ nodes: chatMermaidNodes });
                }
            }, 60);
        }
    }

    // ── Voice Chart & Audio Visualizer Canvas ──
    let audioCtx = null;
    let analyserNode = null;
    let micStream = null;
    let micDataArray = null;

    function initVoiceChartVisualizer() {
        voiceChartCanvas = document.getElementById('voice-chart-canvas');
        if (!voiceChartCanvas) return;
        voiceChartCtx = voiceChartCanvas.getContext('2d');
        
        let phase = 0;
        const numBars = 36;

        function drawVisualizer() {
            if (!voiceChartCtx || !voiceChartCanvas) return;
            const width = voiceChartCanvas.width;
            const height = voiceChartCanvas.height;
            voiceChartCtx.clearRect(0, 0, width, height);

            const barWidth = (width / numBars) - 2;
            phase += 0.09;

            // Get live mic audio frequency data if available
            if (analyserNode && isListening && micDataArray) {
                analyserNode.getByteFrequencyData(micDataArray);
            }

            for (let i = 0; i < numBars; i++) {
                let barHeight = 4;

                if (isListening) {
                    if (analyserNode && micDataArray && micDataArray.length > 0) {
                        const freqIdx = Math.floor((i / numBars) * (micDataArray.length / 2));
                        const val = micDataArray[freqIdx] || 0;
                        barHeight = Math.max(4, (val / 255) * (height - 6));
                    } else {
                        // Procedural reactive wave while user is speaking
                        const sinVal = Math.sin(phase * 2.5 + i * 0.45);
                        const noise = Math.sin(phase * 5 + i * 0.9) * 0.5;
                        barHeight = Math.max(6, (Math.abs(sinVal + noise) * (height - 6)));
                    }
                } else if (isSpeaking) {
                    // Energetic harmonic spectrum when Diva is talking
                    const harmonic1 = Math.sin(phase * 3.2 + i * 0.35);
                    const harmonic2 = Math.cos(phase * 1.8 + i * 0.25);
                    barHeight = Math.max(5, (Math.abs(harmonic1 * harmonic2) * (height - 6)));
                } else {
                    // Subtle ambient breathing wave when idle
                    const wave = Math.sin(phase + i * 0.22);
                    barHeight = 4 + Math.abs(wave) * 8;
                }

                const x = i * (barWidth + 2) + 1;
                const y = (height - barHeight) / 2;

                // Vibrant high-tech colors
                if (isListening) {
                    voiceChartCtx.fillStyle = '#f43f5e'; // Rose 500
                    voiceChartCtx.shadowColor = '#f43f5e';
                    voiceChartCtx.shadowBlur = 4;
                } else if (isSpeaking) {
                    voiceChartCtx.fillStyle = '#10b981'; // Emerald 500
                    voiceChartCtx.shadowColor = '#10b981';
                    voiceChartCtx.shadowBlur = 4;
                } else {
                    voiceChartCtx.fillStyle = '#6366f1'; // Brand Indigo
                    voiceChartCtx.shadowColor = 'transparent';
                    voiceChartCtx.shadowBlur = 0;
                }

                voiceChartCtx.beginPath();
                voiceChartCtx.roundRect(x, y, barWidth, barHeight, [2, 2, 2, 2]);
                voiceChartCtx.fill();
            }

            animationFrameId = requestAnimationFrame(drawVisualizer);
        }

        drawVisualizer();
    }

    function toggleVoiceChartPanel() {
        const panel = document.getElementById('voice-chart-panel');
        if (panel) {
            panel.classList.toggle('hidden');
        }
    }

    function updateVoiceStatus(state, message) {
        const statusText = document.getElementById('voice-status-text');
        const statusDot = document.getElementById('voice-status-dot');
        const statusPing = document.getElementById('voice-status-ping');
        const stopBtn = document.getElementById('voice-stop-btn');
        const micIcon = document.getElementById('tutor-mic-icon');
        const micPulse = document.getElementById('tutor-mic-pulse');
        const micBtn = document.getElementById('tutor-mic-btn');
        const modeBadge = document.getElementById('voice-mode-indicator');

        if (statusText) statusText.innerText = message;

        if (state === 'listening') {
            isListening = true;
            isSpeaking = false;
            if (modeBadge) {
                modeBadge.innerText = "MIC RECORDING";
                modeBadge.className = "text-[9px] font-mono font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse";
            }
            if (statusDot) statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500 shadow-sm shadow-rose-400";
            if (statusPing) {
                statusPing.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75";
                statusPing.classList.remove('hidden');
            }
            if (stopBtn) stopBtn.classList.remove('hidden');
            if (micPulse) micPulse.classList.remove('hidden');
            if (micBtn) micBtn.className = "w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-500 text-rose-300 transition flex items-center justify-center relative flex-shrink-0 shadow-lg shadow-rose-500/25";
        } else if (state === 'speaking') {
            isSpeaking = true;
            isListening = false;
            if (modeBadge) {
                modeBadge.innerText = "DIVA SPEAKING";
                modeBadge.className = "text-[9px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse";
            }
            if (statusDot) statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400 shadow-sm shadow-emerald-400";
            if (statusPing) {
                statusPing.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
                statusPing.classList.remove('hidden');
            }
            if (stopBtn) stopBtn.classList.remove('hidden');
            if (micPulse) micPulse.classList.add('hidden');
            if (micBtn) micBtn.className = "w-10 h-10 rounded-xl bg-dark-900 hover:bg-brand-600/20 border border-white/10 hover:border-brand-500/40 text-gray-300 hover:text-brand-400 transition flex items-center justify-center relative flex-shrink-0 shadow-sm";
        } else if (state === 'thinking') {
            isListening = false;
            isSpeaking = false;
            if (modeBadge) {
                modeBadge.innerText = "ANALYZING";
                modeBadge.className = "text-[9px] font-mono font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse";
            }
            if (statusDot) statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400 shadow-sm shadow-amber-400";
            if (statusPing) {
                statusPing.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75";
                statusPing.classList.remove('hidden');
            }
            if (stopBtn) stopBtn.classList.add('hidden');
            if (micPulse) micPulse.classList.add('hidden');
            if (micBtn) micBtn.className = "w-10 h-10 rounded-xl bg-dark-900 hover:bg-brand-600/20 border border-white/10 hover:border-brand-500/40 text-gray-300 hover:text-brand-400 transition flex items-center justify-center relative flex-shrink-0 shadow-sm";
        } else {
            isListening = false;
            isSpeaking = false;
            if (modeBadge) {
                modeBadge.innerText = "SPECTRUM 48kHz";
                modeBadge.className = "text-[9px] font-mono font-medium px-2 py-0.5 rounded-full bg-brand-500/15 text-brand-300 border border-brand-500/20";
            }
            if (statusDot) statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-brand-500 shadow-sm shadow-brand-400";
            if (statusPing) statusPing.classList.add('hidden');
            if (stopBtn) stopBtn.classList.add('hidden');
            if (micPulse) micPulse.classList.add('hidden');
            if (micBtn) micBtn.className = "w-10 h-10 rounded-xl bg-dark-900 hover:bg-brand-600/20 border border-white/10 hover:border-brand-500/40 text-gray-300 hover:text-brand-400 transition flex items-center justify-center relative flex-shrink-0 shadow-sm";
        }
        safeCreateIcons();
    }

    // ── Speech-to-Text (STT) Recognition (Multi-Lingual) ──
    function initSpeechRecognition() {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRec) {
            console.warn("Speech Recognition API not supported in this browser.");
            return;
        }

        try {
            recognition = new SpeechRec();
            recognition.continuous = false;
            recognition.interimResults = true;
            
            const activeLang = getActiveLanguage();
            const cfg = INDIAN_LANG_CONFIG[activeLang] || INDIAN_LANG_CONFIG['English'];
            recognition.lang = cfg.code;

            recognition.onstart = function() {
                updateVoiceStatus('listening', `Listening in ${cfg.label}... Speak now`);
            };

            recognition.onresult = function(event) {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }

                const input = document.getElementById('tutor-input');
                if (input) {
                    input.value = finalTranscript || interimTranscript;
                }
            };

            recognition.onerror = function(event) {
                console.warn("Speech recognition error:", event.error);
                updateVoiceStatus('idle', 'Voice mic stopped • Click to talk');
            };

            recognition.onend = function() {
                updateVoiceStatus('idle', 'Voice Ready • Click Mic or type');
                const input = document.getElementById('tutor-input');
                if (input && input.value.trim().length > 1) {
                    sendTutorMessage();
                }
            };
        } catch (e) {
            console.warn("Speech recognition init error:", e);
        }
    }

    function toggleSpeechRecognition() {
        if (!recognition) {
            initSpeechRecognition();
            if (!recognition) {
                alert("Speech recognition is not supported in this browser. Please use Google Chrome, Edge, or a modern browser with microphone support.");
                return;
            }
        }

        if (isListening) {
            recognition.stop();
            updateVoiceStatus('idle', 'Voice Ready');
        } else {
            stopAllSpeech();
            
            // Sync recognition language before starting
            const activeLang = getActiveLanguage();
            const cfg = INDIAN_LANG_CONFIG[activeLang] || INDIAN_LANG_CONFIG['English'];
            recognition.lang = cfg.code;

            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia && !audioCtx) {
                navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                    micStream = stream;
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const source = audioCtx.createMediaStreamSource(stream);
                    analyserNode = audioCtx.createAnalyser();
                    analyserNode.fftSize = 64;
                    analyserNode.smoothingTimeConstant = 0.75;
                    source.connect(analyserNode);
                    micDataArray = new Uint8Array(analyserNode.frequencyBinCount);
                }).catch(e => {
                    console.log("Procedural visualizer active:", e);
                });
            }

            try {
                recognition.start();
            } catch (e) {
                recognition.stop();
                setTimeout(() => recognition.start(), 200);
            }
        }
    }

    // ── Multi-Lingual Speech Synthesis (TTS) Engine with Sentence Chunking ──
    let divaVoiceRate = 1.0;
    let narrationQueue = [];
    let narrationIndex = 0;
    let isNarratingSection = false;
    let activeUtterance = null;

    function initSpeechSynthesis() {
        if (!('speechSynthesis' in window)) return;

        function loadVoices() {
            const voices = window.speechSynthesis.getVoices();
            if (!voices || voices.length === 0) return;

            const activeLang = getActiveLanguage();
            preferredDivaVoice = findBestVoiceForLanguage(activeLang, voices);
        }

        loadVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
            window.speechSynthesis.onvoiceschanged = loadVoices;
        }
    }

    function findBestVoiceForLanguage(langName, voices) {
        if (!voices) voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
        if (!voices || voices.length === 0) return null;

        const cfg = INDIAN_LANG_CONFIG[langName] || INDIAN_LANG_CONFIG['English'];
        
        // 1. Try matching specific regional voice names
        for (let nameKw of cfg.names) {
            const found = voices.find(v => v.name.toLowerCase().includes(nameKw.toLowerCase()));
            if (found) return found;
        }

        // 2. Try matching language code prefixes
        for (let p of cfg.prefixes) {
            const found = voices.find(v => v.lang.toLowerCase().startsWith(p.toLowerCase()));
            if (found) return found;
        }

        // 3. Fallback to natural female / English / first voice
        const fallback = voices.find(v => v.lang.toLowerCase().includes('en-in')) ||
                         voices.find(v => v.lang.toLowerCase().startsWith('en')) ||
                         voices[0];
        return fallback;
    }

    function setPlayerVoiceSpeed(rate, btn) {
        divaVoiceRate = rate;
        const container = document.getElementById('player-speed-controls');
        if (container) {
            const btns = container.querySelectorAll('button');
            btns.forEach(b => {
                b.className = "px-1.5 py-0.5 rounded text-gray-400 hover:text-white";
            });
            if (btn) {
                btn.className = "px-1.5 py-0.5 rounded bg-brand-500/20 text-brand-300 font-bold";
            }
        }
        // Also sync drawer voice speed buttons
        const drawerSelector = document.getElementById('voice-speed-selector');
        if (drawerSelector) {
            const dBtns = drawerSelector.querySelectorAll('button');
            dBtns.forEach(b => {
                b.className = "px-2 py-0.5 rounded-md bg-white/5 hover:bg-white/10 text-gray-400 font-mono transition";
                if (b.innerText.includes(rate + 'x') || (rate === 1.0 && b.innerText === '1.0x')) {
                    b.className = "px-2 py-0.5 rounded-md bg-brand-500/20 text-brand-300 border border-brand-500/30 font-mono font-bold transition";
                }
            });
        }
    }

    function setVoiceSpeed(rate, btn) {
        setPlayerVoiceSpeed(rate, null);
        if (btn) {
            const drawerSelector = document.getElementById('voice-speed-selector');
            if (drawerSelector) {
                drawerSelector.querySelectorAll('button').forEach(b => {
                    b.className = "px-2 py-0.5 rounded-md bg-white/5 hover:bg-white/10 text-gray-400 font-mono transition";
                });
                btn.className = "px-2 py-0.5 rounded-md bg-brand-500/20 text-brand-300 border border-brand-500/30 font-mono font-bold transition";
            }
        }
    }

    function toggleVoiceTTS() {
        voiceTTSEnabled = !voiceTTSEnabled;
        const icon = document.getElementById('tts-toggle-icon');
        const btn = document.getElementById('tutor-tts-toggle');
        const badge = document.getElementById('voice-mode-badge');

        if (voiceTTSEnabled) {
            btn.className = "w-8 h-8 rounded-lg bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 flex items-center justify-center transition border border-brand-500/20";
            btn.title = "Voice Read Aloud: Enabled";
            badge.innerText = "Voice Ready";
            badge.className = "text-[9px] font-bold bg-brand-500/20 text-brand-300 border border-brand-500/30 px-1.5 py-0.5 rounded-full uppercase tracking-wider";
            if (icon) icon.setAttribute('data-lucide', 'volume-2');
        } else {
            stopAllSpeech();
            btn.className = "w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 flex items-center justify-center transition border border-white/10";
            btn.title = "Voice Read Aloud: Muted";
            badge.innerText = "Text Only";
            badge.className = "text-[9px] font-bold bg-white/5 text-gray-400 border border-white/10 px-1.5 py-0.5 rounded-full uppercase tracking-wider";
            if (icon) icon.setAttribute('data-lucide', 'volume-x');
        }
        safeCreateIcons();
    }

    // ── Deep Dive Sentence-Chunked Narration Engine ──
    function splitIntoNarrationSentences(text) {
        if (!text) return [];
        const clean = stripMarkdownForTTS(text);
        // Split on sentences (period, question mark, exclamation, danda, semicolon)
        const rawChunks = clean.split(/(?<=[.?!।\n;])\s+/);
        const result = [];
        for (let c of rawChunks) {
            const trimmed = c.trim();
            if (!trimmed || trimmed.length < 2) continue;
            if (trimmed.length > 180) {
                const sub = trimmed.split(/,\s+/);
                for (let s of sub) {
                    if (s.trim()) result.push(s.trim());
                }
            } else {
                result.push(trimmed);
            }
        }
        return result;
    }

    function toggleSectionNarration() {
        if (isNarratingSection) {
            stopSectionNarration();
        } else {
            startSectionNarration();
        }
    }

    function startSectionNarration() {
        const sec = sections[activeSecIdx];
        if (!sec) return;

        stopAllSpeech();

        const activeLang = getActiveLanguage();
        const cfg = INDIAN_LANG_CONFIG[activeLang] || INDIAN_LANG_CONFIG['English'];

        // Prepare full narrative text
        let fullText = `${sec.title}. `;
        if (sec.content) fullText += sec.content;
        if (sec.example) fullText += ` Worked example: ${sec.example}`;

        narrationQueue = splitIntoNarrationSentences(fullText);
        if (narrationQueue.length === 0) return;

        narrationIndex = 0;
        isNarratingSection = true;

        updatePlayerUI('playing', `Diva Voice Narrating: ${sec.title}`);
        updateVoiceStatus('speaking', `Diva Voice (${cfg.label}) • Deep Dive Audio Active`);

        playNextNarrationSentence();
    }

    function playNextNarrationSentence() {
        if (!isNarratingSection || narrationIndex >= narrationQueue.length) {
            stopSectionNarration();
            return;
        }

        if (!('speechSynthesis' in window)) return;

        const sentence = narrationQueue[narrationIndex];
        const activeLang = getActiveLanguage();
        const cfg = INDIAN_LANG_CONFIG[activeLang] || INDIAN_LANG_CONFIG['English'];

        // Update live subtitle bar
        const subtitleEl = document.getElementById('player-live-sentence');
        if (subtitleEl) {
            subtitleEl.innerText = sentence;
            subtitleEl.classList.remove('hidden');
        }

        const utterance = new SpeechSynthesisUtterance(sentence);
        utterance.lang = cfg.code;
        
        const voices = window.speechSynthesis.getVoices();
        const voice = findBestVoiceForLanguage(activeLang, voices);
        if (voice) utterance.voice = voice;

        utterance.rate = divaVoiceRate || 1.0;
        utterance.pitch = 1.05;

        utterance.onend = function() {
            narrationIndex++;
            if (isNarratingSection) {
                playNextNarrationSentence();
            }
        };

        utterance.onerror = function(e) {
            console.warn("Sentence TTS notice:", e);
            narrationIndex++;
            if (isNarratingSection) {
                playNextNarrationSentence();
            }
        };

        activeUtterance = utterance;
        window.speechSynthesis.speak(utterance);
    }

    function stopSectionNarration() {
        isNarratingSection = false;
        narrationQueue = [];
        narrationIndex = 0;
        activeUtterance = null;

        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }

        updatePlayerUI('idle', 'Listen to AI audio narration in your language');
        updateVoiceStatus('idle', 'Voice Ready • Click Mic or type');
    }

    function updatePlayerUI(state, text) {
        const playBtn = document.getElementById('player-play-btn');
        const playIcon = document.getElementById('player-play-icon');
        const playText = document.getElementById('player-play-text');
        const stopBtn = document.getElementById('player-stop-btn');
        const subTitle = document.getElementById('player-status-subtitle');
        const subtitleEl = document.getElementById('player-live-sentence');

        if (state === 'playing') {
            if (playBtn) {
                playBtn.className = "flex-shrink-0 bg-gradient-to-r from-emerald-600 to-teal-600 text-white font-bold text-xs px-4 py-2 rounded-xl shadow-lg shadow-emerald-500/25 flex items-center space-x-2 transition active:scale-95 cursor-pointer";
            }
            if (playIcon) playIcon.setAttribute('data-lucide', 'pause');
            if (playText) playText.innerText = "Pause Audio";
            if (stopBtn) stopBtn.classList.remove('hidden');
            if (subTitle) subTitle.innerText = text;
        } else {
            if (playBtn) {
                playBtn.className = "flex-shrink-0 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white font-bold text-xs px-4 py-2 rounded-xl shadow-lg shadow-brand-500/25 flex items-center space-x-2 transition active:scale-95 cursor-pointer";
            }
            if (playIcon) playIcon.setAttribute('data-lucide', 'play');
            if (playText) playText.innerText = "Listen to Section";
            if (stopBtn) stopBtn.classList.add('hidden');
            if (subTitle) subTitle.innerText = text;
            if (subtitleEl) subtitleEl.classList.add('hidden');
        }
        safeCreateIcons();
    }

    function narrateWorkedExample() {
        const sec = sections[activeSecIdx];
        if (!sec || !sec.example) return;
        const text = `Worked Example code walkthrough for ${sec.title}. ${sec.example}`;
        speakDivaResponse(text);
    }

    function narrateMcq(secIdx, qIdx) {
        const sec = sections[secIdx];
        if (!sec || !sec.mcqQuestions || !sec.mcqQuestions[qIdx]) return;
        const q = sec.mcqQuestions[qIdx];
        let text = `Practice Question: ${q.question}. `;
        q.options.forEach((opt, idx) => {
            text += ` Option ${idx + 1}: ${opt}. `;
        });
        if (q.explanation) {
            text += ` Explanation: ${q.explanation}`;
        }
        speakDivaResponse(text);
    }

    function speakDivaResponse(text) {
        if (!('speechSynthesis' in window)) return;
        stopAllSpeech();

        const cleanText = stripMarkdownForTTS(text);
        if (!cleanText) return;

        const activeLang = getActiveLanguage();
        const cfg = INDIAN_LANG_CONFIG[activeLang] || INDIAN_LANG_CONFIG['English'];

        const sentences = splitIntoNarrationSentences(cleanText);
        if (sentences.length === 0) return;

        let curIdx = 0;
        isSpeaking = true;
        updateVoiceStatus('speaking', `Diva is speaking in ${cfg.label}...`);

        function speakNext() {
            if (!isSpeaking || curIdx >= sentences.length) {
                isSpeaking = false;
                updateVoiceStatus('idle', 'Voice Ready • Click Mic or type');
                return;
            }

            const utt = new SpeechSynthesisUtterance(sentences[curIdx]);
            utt.lang = cfg.code;
            
            const voices = window.speechSynthesis.getVoices();
            const voice = findBestVoiceForLanguage(activeLang, voices);
            if (voice) utt.voice = voice;

            utt.rate = divaVoiceRate || 1.0;
            utt.pitch = 1.05;

            utt.onend = function() {
                curIdx++;
                speakNext();
            };

            utt.onerror = function() {
                curIdx++;
                speakNext();
            };

            window.speechSynthesis.speak(utt);
        }

        speakNext();
    }

    function stopAllSpeech() {
        isSpeaking = false;
        isNarratingSection = false;
        narrationQueue = [];
        narrationIndex = 0;

        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        if (recognition && isListening) {
            recognition.stop();
        }
        updatePlayerUI('idle', 'Listen to AI audio narration in your language');
        updateVoiceStatus('idle', 'Voice Ready • Click Mic or type');
    }

    function stripMarkdownForTTS(md) {
        if (!md) return "";
        let clean = md;
        // Clean code blocks to clear audio markers
        clean = clean.replace(/```[\s\S]*?```/g, " [Code example on screen] ");
        clean = clean.replace(/`([^`]+)`/g, "$1");
        clean = clean.replace(/#{1,6}\s+/g, "");
        clean = clean.replace(/(\*\*|__)(.*?)\1/g, "$2");
        clean = clean.replace(/(\*|_)(.*?)\1/g, "$2");
        clean = clean.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");
        clean = clean.replace(/>\s+/g, "");
        clean = clean.replace(/[-*+]\s+/g, "");
        return clean.trim();
    }

    function escapeQuotesForJS(str) {
        return str
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/"/g, '&quot;')
            .replace(/\n/g, ' ');
    }

    // ── Player Spectrum Canvas Visualizer ──
    let playerSpectrumCanvas = null;
    let playerSpectrumCtx = null;
    let playerSpectrumAnimId = null;

    function initPlayerSpectrum() {
        playerSpectrumCanvas = document.getElementById('player-spectrum-canvas');
        if (!playerSpectrumCanvas) return;
        playerSpectrumCtx = playerSpectrumCanvas.getContext('2d');
        
        let phase = 0;
        const numBars = 32;

        function drawPlayerWave() {
            if (!playerSpectrumCtx || !playerSpectrumCanvas) return;
            const w = playerSpectrumCanvas.width;
            const h = playerSpectrumCanvas.height;
            playerSpectrumCtx.clearRect(0, 0, w, h);

            phase += 0.12;
            const barW = (w / numBars) - 2;

            for (let i = 0; i < numBars; i++) {
                let barH = 3;
                if (isNarratingSection || isSpeaking) {
                    const s1 = Math.sin(phase * 2.8 + i * 0.4);
                    const s2 = Math.cos(phase * 1.5 + i * 0.3);
                    barH = Math.max(4, Math.abs(s1 * s2) * (h - 4));
                    playerSpectrumCtx.fillStyle = '#6366f1'; // Brand Indigo/Violet
                    playerSpectrumCtx.shadowColor = '#818cf8';
                    playerSpectrumCtx.shadowBlur = 4;
                } else {
                    const s = Math.sin(phase * 0.5 + i * 0.2);
                    barH = 3 + Math.abs(s) * 3;
                    playerSpectrumCtx.fillStyle = 'rgba(99, 102, 241, 0.25)';
                    playerSpectrumCtx.shadowBlur = 0;
                }

                const x = i * (barW + 2) + 1;
                const y = (h - barH) / 2;
                playerSpectrumCtx.beginPath();
                playerSpectrumCtx.roundRect(x, y, barW, barH, [2, 2, 2, 2]);
                playerSpectrumCtx.fill();
            }
            playerSpectrumAnimId = requestAnimationFrame(drawPlayerWave);
        }
        drawPlayerWave();
    }

    // ── Code Runner Drawer Controller ──
    let lastDrawerStderr = "";
    let lastDrawerCode = "";

    function toggleRunnerDrawer() {
        const drawer = document.getElementById('runner-drawer');
        const floatingActions = document.getElementById('floating-actions');
        const isClosed = drawer.classList.contains('translate-x-full');
        
        if (isClosed) {
            const tutorDrawer = document.getElementById('tutor-drawer');
            if (!tutorDrawer.classList.contains('translate-x-full')) {
                tutorDrawer.classList.add('translate-x-full');
            }
            drawer.classList.remove('translate-x-full');
            floatingActions.classList.add('opacity-0', 'pointer-events-none', 'translate-x-12');
            
            const editor = document.getElementById('drawer-code-editor');
            if (!editor.value.trim() && sections[activeSecIdx] && sections[activeSecIdx].example) {
                editor.value = cleanCodeSnippet(sections[activeSecIdx].example);
            }
        } else {
            drawer.classList.add('translate-x-full');
            floatingActions.classList.remove('opacity-0', 'pointer-events-none', 'translate-x-12');
        }
        safeCreateIcons();
    }

    function openRunnerWithExample() {
        const sec = sections[activeSecIdx];
        if (!sec || !sec.example) return;

        const editor = document.getElementById('drawer-code-editor');
        editor.value = cleanCodeSnippet(sec.example);

        const domainStr = "[]".toLowerCase();
        const select = document.getElementById('drawer-lang-select');
        
        if (domainStr.includes("python")) select.value = "python";
        else if (domainStr.includes("sql")) select.value = "sql";
        else if (domainStr.includes("rust")) select.value = "rust";
        else if (domainStr.includes("go") || domainStr.includes("golang")) select.value = "go";
        else if (domainStr.includes("c++") || domainStr.includes("cpp")) select.value = "c++";
        else if (domainStr.includes("typescript") || domainStr.includes("ts")) select.value = "typescript";
        else if (domainStr.includes("javascript") || domainStr.includes("js") || domainStr.includes("node") || domainStr.includes("react")) select.value = "javascript";
        else if (domainStr.includes("java")) select.value = "java";
        else if (domainStr.includes(" c ") || domainStr.endsWith(" c")) select.value = "c";

        const drawer = document.getElementById('runner-drawer');
        if (drawer.classList.contains('translate-x-full')) {
            toggleRunnerDrawer();
        }

        runDrawerCode();
    }

    function cleanCodeSnippet(text) {
        if (!text) return "";
        let cleaned = text.trim();
        if (cleaned.startsWith("```")) {
            cleaned = cleaned.replace(/^```[a-zA-Z0-9_-]*\n?/, "");
            cleaned = cleaned.replace(/\n?```$/, "");
        }
        if (cleaned.includes('\\n')) {
            cleaned = cleaned.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\t/g, '\t');
        }
        return cleaned.trim();
    }

    async function runDrawerCode() {
        const lang = document.getElementById('drawer-lang-select').value;
        const code = document.getElementById('drawer-code-editor').value;
        const stdin = document.getElementById('drawer-stdin').value;

        if (!code.trim()) return;

        const btn = document.getElementById('drawer-run-btn');
        const btnText = document.getElementById('drawer-run-text');
        const icon = document.getElementById('drawer-run-icon');
        const outputDiv = document.getElementById('drawer-output');
        const timeBadge = document.getElementById('drawer-time-badge');
        const aiBox = document.getElementById('drawer-ai-error');
        const aiContent = document.getElementById('drawer-ai-explanation');

        btn.disabled = true;
        btnText.innerText = "Running...";
        icon.classList.add("animate-spin");
        outputDiv.innerHTML = '<span class="text-emerald-400 animate-pulse">Executing code on isolated runtime...</span>';
        aiBox.classList.add('hidden');
        aiContent.classList.add('hidden');

        lastDrawerCode = code;

        try {
            const res = await fetch("/compiler/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ language: lang, code: code, stdin: stdin })
            });
            const data = await res.json();

            let outText = "";
            if (data.stdout) outText += data.stdout;
            if (data.stderr) {
                lastDrawerStderr = data.stderr;
                if (outText) outText += "\n";
                outText += data.stderr;
                aiBox.classList.remove('hidden');
            } else {
                lastDrawerStderr = "";
            }

            if (!data.stdout && !data.stderr) {
                outText = "(Program executed successfully with no output)";
            }

            outputDiv.innerText = outText;
            timeBadge.innerText = `${data.executionTimeMs}ms • Exit: ${data.exitCode}`;
        } catch (e) {
            outputDiv.innerText = "Execution failed: " + e.message;
        } finally {
            btn.disabled = false;
            btnText.innerText = "Run";
            icon.classList.remove("animate-spin");
            safeCreateIcons();
        }
    }

    async function explainDrawerError() {
        if (!lastDrawerStderr) return;

        const lang = document.getElementById('drawer-lang-select').value;
        const btn = document.getElementById('drawer-explain-btn');
        const contentDiv = document.getElementById('drawer-ai-explanation');

        btn.disabled = true;
        btn.innerText = "Analyzing error...";

        try {
            const res = await fetch("/compiler/explain", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ language: lang, code: lastDrawerCode, error: lastDrawerStderr })
            });
            const data = await res.json();
            contentDiv.classList.remove('hidden');
            contentDiv.innerHTML = marked.parse(data.explanation || "No explanation available.");
        } catch (e) {
            contentDiv.classList.remove('hidden');
            contentDiv.innerText = "Could not fetch AI explanation.";
        } finally {
            btn.disabled = false;
            btn.innerText = "Explain Error with AI";
        }
    }

    // ── Translation Modal Controller ──
    function openTranslateModal() {
        const modal = document.getElementById('translate-select-modal');
        if (modal) modal.classList.remove('hidden');
        safeCreateIcons();
    }

    function closeTranslateModal() {
        const modal = document.getElementById('translate-select-modal');
        if (modal) modal.classList.add('hidden');
    }

    function selectLanguageAndTranslate(lang) {
        document.cookie = "preferred_language=" + encodeURIComponent(lang) + "; path=/; max-age=31536000";
        closeTranslateModal();
        
        const loadingModal = document.getElementById('translate-loading-modal');
        const subtitle = document.getElementById('translate-modal-subtitle');
        const cfg = INDIAN_LANG_CONFIG[lang] || { label: lang };
        
        if (subtitle) {
            subtitle.innerText = `Diva AI is regenerating all 50-minute syllabus subtopics, code examples, and practice MCQs in ${cfg.label}. Please wait a few seconds...`;
        }
        if (loadingModal) {
            loadingModal.classList.remove('hidden');
        }
        safeCreateIcons();
        window.location.href = "?regenerate=true";
    }
