// State variables
let appLanguage = 'fr';
let priceData = null;
let portfolioChart = null;

// Ticker names map
const tickerDescriptions = {
    "NVDA": { fr: "NVIDIA Corp. (GPU & IA)", en: "NVIDIA Corp. (GPU & AI)" },
    "AMD": { fr: "Advanced Micro Devices (Chips)", en: "Advanced Micro Devices (Chips)" },
    "AVGO": { fr: "Broadcom Inc. (Réseau & Semi)", en: "Broadcom Inc. (Networking & Semi)" },
    "MU": { fr: "Micron Technology (Mémoires)", en: "Micron Technology (Memory Chips)" },
    "QCOM": { fr: "Qualcomm Inc. (Mobile & Edge IA)", en: "Qualcomm Inc. (Mobile & Edge AI)" },
    "INTC": { fr: "Intel Corp. (Fonderie & CPU)", en: "Intel Corp. (Foundry & CPU)" },
    "MSFT": { fr: "Microsoft Corp. (Cloud & OpenAI)", en: "Microsoft Corp. (Cloud & OpenAI)" },
    "GOOGL": { fr: "Alphabet Inc. (Google Search & Gemini)", en: "Alphabet Inc. (Search & Gemini)" },
    "META": { fr: "Meta Platforms (Llama & Réseaux)", en: "Meta Platforms (Llama & Social)" },
    "AMZN": { fr: "Amazon.com Inc. (AWS Cloud & IA)", en: "Amazon.com Inc. (AWS Cloud & AI)" }
};

// Bilingual dictionary
const i18n = {
    fr: {
        pageTitle: "Testez vos thèses financières sur l'IA. Instantanément.",
        pageSubtitle: "Ajustez vos allocations sur le Top 10 des semi-conducteurs et géants du Cloud US. Visualisez 10 ans de performance historique en temps réel. 100% gratuit, calculé localement.",
        allocationTitle: "Allocation du Portefeuille",
        presetsTitle: "Préréglages Stratégiques",
        presetEqual: "Pondération Égale",
        presetEqualDesc: "Équilibre sectoriel parfait",
        presetAiHard: "Pur Hardware IA",
        presetAiHardDesc: "Concentré sur les puces et infrastructures physiques",
        presetGiants: "Géants du Cloud",
        presetGiantsDesc: "Les leaders du logiciel et des LLMs à l'échelle",
        presetValue: "Value & Fonderie",
        presetValueDesc: "Opportunités industrielles",
        totalAlloc: "Allocation Totale :",
        warnWeights: "⚠️ Le total de votre allocation est de {val}%. Elle sera normalisée à 100% pour le calcul graphique.",
        perfTitle: "Performance Historique (10 Ans - Base 100)",
        statCumul: "Retour Cumulé",
        statCagr: "Rendement Annuel (CAGR)",
        statMdd: "Baisse Max (Drawdown)",
        aiPanelTitle: "Analyse Stratégique de la Thèse (Propulsé par IA Souveraine)",
        btnAnalyze: "Demander une Analyse IA",
        btnAnalyzing: "Analyse en cours...",
        aiEmpty: "Configurez vos curseurs et cliquez sur le bouton ci-dessus pour lancer une analyse financière par votre modèle de langage configuré.",
        reasoningTitle: "Afficher le chemin de pensée de l'IA",
        reasoningHide: "Masquer le chemin de pensée de l'IA",
        btnShare: "Partager ma stratégie",
        toastCopied: "Lien de stratégie copié ! Téléchargement de l'image de partage...",
        footerServer: "Serveur LLM : OpenAI-compatible (configurable via LITELLM_URL)",
        footerModel: "Modèle : configuré via LITELLM_MODEL",
        footerStatus: "Statut : Connecté au serveur LLM",
        errorTitle: "Erreur d'analyse",
        errorServerOffline: "Le serveur d'analyse IA n'a pas répondu. Vérifiez que LITELLM_URL pointe vers un serveur OpenAI-compatible démarré.",
        errorGeneral: "Une erreur est survenue lors de la génération de l'analyse.",
        audioPanelTitle: "Briefing Audio Interactif (Podcast)",
        audioPanelSubtitle: "Dialogue IA bilingue synthétisé sur carte AMD RX 6700 XT",
        btnAudioGenerate: "Générer le briefing audio",
        btnAudioGenerating: "Génération en cours...",
        audioLoadingScript: "Étape 1/2 : Génération du script par DeepSeek...",
        audioLoadingSpeech: "Étape 2/2 : Synthèse vocale par Kokoro sur carte AMD...",
        audioError: "Erreur lors de la génération audio.",
        audioSuccess: "Briefing audio généré avec succès !"
    },
    en: {
        pageTitle: "Test your AI financial theses. Instantly.",
        pageSubtitle: "Tweak your allocations across the Top 10 US Semiconductors & Cloud Giants. Visualize 10 years of historical performance in real-time. 100% free, processed locally.",
        allocationTitle: "Portfolio Allocation",
        presetsTitle: "Strategic Presets",
        presetEqual: "Equal Weight",
        presetEqualDesc: "Perfect sector balance",
        presetAiHard: "Pure AI Hardware",
        presetAiHardDesc: "Focused on chips and physical infrastructure",
        presetGiants: "Cloud Giants",
        presetGiantsDesc: "Hyperscalers leading software and LLMs",
        presetValue: "Value & Foundry",
        presetValueDesc: "Industrial opportunities",
        totalAlloc: "Total Allocation:",
        warnWeights: "⚠️ Your total allocation is {val}%. It will be normalized to 100% for the performance chart.",
        perfTitle: "Historical Performance (10 Years - Base 100)",
        statCumul: "Cumulative Return",
        statCagr: "Annual Return (CAGR)",
        statMdd: "Max Drawdown",
        aiPanelTitle: "Strategic Thesis Analysis (Powered by Sovereign AI)",
        btnAnalyze: "Request AI Analysis",
        btnAnalyzing: "Analyzing...",
        aiEmpty: "Configure your sliders and click the button above to launch an AI financial analysis using your configured language model.",
        reasoningTitle: "Show AI Chain of Thought",
        reasoningHide: "Hide AI Chain of Thought",
        btnShare: "Share my strategy",
        toastCopied: "Strategy link copied! Downloading sharing image...",
        footerServer: "LLM Server: OpenAI-compatible (configurable via LITELLM_URL)",
        footerModel: "Model: configured via LITELLM_MODEL",
        footerStatus: "Status: Connected to LLM server",
        errorTitle: "Analysis Error",
        errorServerOffline: "The AI analysis server did not respond. Check that LITELLM_URL points to a running OpenAI-compatible server.",
        errorGeneral: "An error occurred while generating the analysis.",
        audioPanelTitle: "Interactive Audio Briefing (Podcast)",
        audioPanelSubtitle: "Bilingual AI dialogue synthesized on AMD RX 6700 XT GPU",
        btnAudioGenerate: "Generate Audio Brief",
        btnAudioGenerating: "Generating Audio...",
        audioLoadingScript: "Step 1/2: Generating podcast script with DeepSeek...",
        audioLoadingSpeech: "Step 2/2: Synthesizing voice dialogue with Kokoro on AMD...",
        audioError: "Failed to generate audio briefing.",
        audioSuccess: "Audio briefing generated successfully!"
    }
};

// Initial allocation weights
let allocations = {
    "NVDA": 10, "AMD": 10, "AVGO": 10, "MU": 10, "QCOM": 10,
    "INTC": 10, "MSFT": 10, "GOOGL": 10, "META": 10, "AMZN": 10
};

// Preset Weights definitions
const presets = {
    equal: {
        "NVDA": 10, "AMD": 10, "AVGO": 10, "MU": 10, "QCOM": 10,
        "INTC": 10, "MSFT": 10, "GOOGL": 10, "META": 10, "AMZN": 10
    },
    aiHard: {
        "NVDA": 40, "AMD": 30, "AVGO": 30, "MU": 0, "QCOM": 0,
        "INTC": 0, "MSFT": 0, "GOOGL": 0, "META": 0, "AMZN": 0
    },
    giants: {
        "NVDA": 0, "AMD": 0, "AVGO": 0, "MU": 0, "QCOM": 0,
        "INTC": 0, "MSFT": 25, "GOOGL": 25, "META": 25, "AMZN": 25
    },
    value: {
        "NVDA": 0, "AMD": 0, "AVGO": 0, "MU": 30, "QCOM": 30,
        "INTC": 40, "MSFT": 0, "GOOGL": 0, "META": 0, "AMZN": 0
    }
};

// Initialize frontend
document.addEventListener("DOMContentLoaded", async () => {
    // 1. Render UI Texts (Default FR)
    updateLanguageUI();
    
    // 2. Fetch prices from FastAPI backend
    try {
        const response = await fetch('/api/prices');
        if (!response.ok) {
            throw new Error("Could not fetch stock prices.");
        }
        priceData = await response.json();
        
        // 2b. Parse query params to rehydrate allocations
        const urlParams = new URLSearchParams(window.location.search);
        let hasValidParams = false;
        
        priceData.tickers.forEach(ticker => {
            const paramKey = urlParams.has(ticker) ? ticker : (urlParams.has(ticker.toLowerCase()) ? ticker.toLowerCase() : null);
            if (paramKey) {
                const val = parseInt(urlParams.get(paramKey));
                if (!isNaN(val) && val >= 0 && val <= 100) {
                    allocations[ticker] = val;
                    hasValidParams = true;
                }
            }
        });
        
        // 3. Initialize Sliders
        initSliders();
        
        // 4. Render initial Chart
        runBacktest();
        
    } catch (err) {
        showError(true, "Could not load stock price database. Please run download_data.py.");
        console.error("Initialization error:", err);
    }
    
    // 5. Setup Language switch button
    document.getElementById("btn-lang-toggle").addEventListener("click", () => {
        appLanguage = appLanguage === 'fr' ? 'en' : 'fr';
        updateLanguageUI();
        // Update Chart Labels if chart exists
        if (portfolioChart) {
            portfolioChart.data.datasets[0].label = appLanguage === 'fr' ? 'Portefeuille Simulé' : 'Simulated Portfolio';
            portfolioChart.options.plugins.title.text = i18n[appLanguage].perfTitle;
            portfolioChart.update();
        }
        // Update sliders label names
        updateSliderLabels();
        // Re-calculate statistics language
        // Re-calculate statistics language
        runBacktest();
    });

    // 6. Setup Presets buttons
    document.getElementById("preset-equal").addEventListener("click", () => applyPreset('equal'));
    document.getElementById("preset-ai-hard").addEventListener("click", () => applyPreset('aiHard'));
    document.getElementById("preset-giants").addEventListener("click", () => applyPreset('giants'));
    document.getElementById("preset-value").addEventListener("click", () => applyPreset('value'));

    // 7. Setup AI Analysis Button
    document.getElementById("btn-ai-analyze").addEventListener("click", triggerAIAnalysis);
    
    // 8. Setup Reasoning Accordion Toggle
    document.getElementById("accordion-header").addEventListener("click", toggleReasoning);

    // 9. Setup Share Button
    document.getElementById("btn-share-strategy").addEventListener("click", generateShareCard);

    // 10. Setup Audio Briefing Button
    document.getElementById("btn-audio-generate").addEventListener("click", triggerAudioOverview);

    // 11. Setup Audio Element listeners for waveform animation
    const audioEl = document.getElementById("audio-element");
    const waveContainer = document.getElementById("waveform-container");
    if (audioEl && waveContainer) {
        audioEl.addEventListener("play", () => waveContainer.classList.add("playing"));
        audioEl.addEventListener("pause", () => waveContainer.classList.remove("playing"));
        audioEl.addEventListener("ended", () => waveContainer.classList.remove("playing"));
    }
});

// Update all text labels on the page based on active language
function updateLanguageUI() {
    const langKeys = [
        "pageTitle", "pageSubtitle", "allocationTitle", "presetsTitle", 
        "presetEqual", "presetEqualDesc",
        "presetAiHard", "presetAiHardDesc",
        "presetGiants", "presetGiantsDesc",
        "presetValue", "presetValueDesc",
        "perfTitle", "statCumul", "statCagr", "statMdd",
        "aiPanelTitle", "footerServer", "footerModel", "footerStatus",
        "btnShare", "audioPanelTitle", "audioPanelSubtitle"
    ];
    
    langKeys.forEach(key => {
        const el = document.getElementById(`lbl-${key}`);
        if (el) {
            el.textContent = i18n[appLanguage][key];
        }
    });
    
    // Update Button label
    const btnAi = document.getElementById("btn-ai-analyze");
    if (btnAi && !btnAi.disabled) {
        btnAi.innerHTML = `<svg style="width:1.1rem;height:1.1rem" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg> ${i18n[appLanguage].btnAnalyze}`;
    }
    
    // Update Audio Button label
    const btnAudio = document.getElementById("btn-audio-generate");
    if (btnAudio && !btnAudio.disabled) {
        btnAudio.innerHTML = `<svg style="width:1.1rem;height:1.1rem;margin-right:0.35rem;display:inline-block;vertical-align:middle" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"></path></svg> <span>${i18n[appLanguage].btnAudioGenerate}</span>`;
    }
    
    // Update toggle flag text
    document.getElementById("btn-lang-toggle").innerHTML = appLanguage === 'fr' 
        ? '🇬🇧 EN' 
        : '🇫🇷 FR';
        
    // Update warning text if applicable
    updateWeightsWarning();
}

// Set up sliders dynamically and attach input listeners
function initSliders() {
    const container = document.getElementById("sliders-container");
    container.innerHTML = "";
    
    priceData.tickers.forEach(ticker => {
        const initialVal = allocations[ticker];
        
        const group = document.createElement("div");
        group.className = "slider-group";
        
        const labelRow = document.createElement("div");
        labelRow.className = "slider-label-row";
        
        const descText = tickerDescriptions[ticker][appLanguage];
        labelRow.innerHTML = `
            <div>
                <span class="ticker-name">${ticker}</span>
                <span class="ticker-desc" id="desc-${ticker}">${descText}</span>
            </div>
            <span class="ticker-val" id="val-${ticker}">${initialVal}%</span>
        `;
        
        const range = document.createElement("input");
        range.type = "range";
        range.min = "0";
        range.max = "100";
        range.value = initialVal;
        range.className = "range-input";
        range.id = `slider-${ticker}`;
        
        range.addEventListener("input", (e) => {
            const val = parseInt(e.target.value);
            allocations[ticker] = val;
            document.getElementById(`val-${ticker}`).textContent = `${val}%`;
            
            // Re-run backtest instantly
            updateWeightsWarning();
            runBacktest();
        });
        
        group.appendChild(labelRow);
        group.appendChild(range);
        container.appendChild(group);
    });
}

// Update ticker description translations
function updateSliderLabels() {
    if (!priceData) return;
    priceData.tickers.forEach(ticker => {
        const descEl = document.getElementById(`desc-${ticker}`);
        if (descEl) {
            descEl.textContent = tickerDescriptions[ticker][appLanguage];
        }
    });
}

// Alert the user if sliders do not add up to 100%
function updateWeightsWarning() {
    const total = Object.values(allocations).reduce((a, b) => a + b, 0);
    const badge = document.getElementById("allocation-total-badge");
    badge.textContent = `${total}%`;
    
    const warnBanner = document.getElementById("weights-warn-banner");
    
    if (total !== 100) {
        badge.classList.add("error-state");
        warnBanner.textContent = i18n[appLanguage].warnWeights.replace("{val}", total);
        warnBanner.classList.add("active");
    } else {
        badge.classList.remove("error-state");
        warnBanner.classList.remove("active");
    }
}

// Apply a preset weight allocation
function applyPreset(presetKey) {
    if (!priceData) return;
    
    const targetWeights = presets[presetKey];
    for (const ticker in targetWeights) {
        allocations[ticker] = targetWeights[ticker];
        
        const slider = document.getElementById(`slider-${ticker}`);
        if (slider) {
            slider.value = targetWeights[ticker];
        }
        const valLabel = document.getElementById(`val-${ticker}`);
        if (valLabel) {
            valLabel.textContent = `${targetWeights[ticker]}%`;
        }
    }
    
    updateWeightsWarning();
    runBacktest();
}

// Execute the client-side portfolio historical backtesting math
function runBacktest() {
    if (!priceData) return;
    
    const tickers = priceData.tickers;
    const dates = priceData.dates;
    const N = dates.length;
    
    // Normalize weights dynamically so they sum to 1.0 (100%)
    const rawWeights = tickers.map(ticker => allocations[ticker] || 0);
    const sumWeights = rawWeights.reduce((a, b) => a + b, 0);
    
    let normalizedWeights = [];
    if (sumWeights > 0) {
        normalizedWeights = rawWeights.map(w => w / sumWeights);
    } else {
        // Fallback: Equal Weight if all weights are 0
        normalizedWeights = tickers.map(() => 1.0 / tickers.length);
    }
    
    // Compute daily portfolio returns
    const portfolioValues = new Array(N);
    
    // Set up price normalizers at date 0
    const startingPrices = tickers.map(ticker => priceData.prices[ticker][0]);
    
    for (let t = 0; t < N; t++) {
        let value = 0.0;
        for (let i = 0; i < tickers.length; i++) {
            const ticker = tickers[i];
            const price_t = priceData.prices[ticker][t];
            const price_0 = startingPrices[i];
            // asset performance relative to start date
            const returnRatio = price_0 > 0 ? (price_t / price_0) : 1.0;
            value += normalizedWeights[i] * returnRatio;
        }
        portfolioValues[t] = value * 100; // Base 100
    }
    
    // Compute performance metrics
    const initialVal = portfolioValues[0];
    const finalVal = portfolioValues[N - 1];
    
    // Cumulative return (%)
    const cumulativeReturn = ((finalVal - initialVal) / initialVal) * 100;
    
    // CAGR (Compound Annual Growth Rate)
    const startDate = new Date(dates[0]);
    const endDate = new Date(dates[N - 1]);
    const diffTime = Math.abs(endDate - startDate);
    const diffYears = diffTime / (1000 * 60 * 60 * 24 * 365.25);
    const cagr = (Math.pow((finalVal / initialVal), (1 / diffYears)) - 1) * 100;
    
    // Max Drawdown
    let peak = -Infinity;
    let maxDrawdown = 0;
    for (let t = 0; t < N; t++) {
        if (portfolioValues[t] > peak) {
            peak = portfolioValues[t];
        }
        const drawdown = (peak - portfolioValues[t]) / peak;
        if (drawdown > maxDrawdown) {
            maxDrawdown = drawdown;
        }
    }
    const maxDrawdownPct = maxDrawdown * 100;
    
    // Render Stats to UI
    renderStats(cumulativeReturn, cagr, maxDrawdownPct);
    
    // Update Chart
    renderChart(dates, portfolioValues);
}

// Render statistics elements
function renderStats(cumul, cagr, mdd) {
    const valCumul = document.getElementById("val-stat-cumul");
    const valCagr = document.getElementById("val-stat-cagr");
    const valMdd = document.getElementById("val-stat-mdd");
    
    valCumul.textContent = (cumul >= 0 ? '+' : '') + cumul.toFixed(1) + '%';
    valCumul.className = `stat-value ${cumul >= 0 ? 'up' : 'down'}`;
    
    valCagr.textContent = (cagr >= 0 ? '+' : '') + cagr.toFixed(1) + '%';
    valCagr.className = `stat-value ${cagr >= 0 ? 'up' : 'down'}`;
    
    valMdd.textContent = '-' + mdd.toFixed(1) + '%';
    valMdd.className = 'stat-value down';
}

// Render or update the Chart.js line graph
function renderChart(labels, dataPoints) {
    const ctx = document.getElementById('portfolio-chart-canvas').getContext('2d');
    
    if (portfolioChart) {
        // Fast update without full chart re-render
        portfolioChart.data.labels = labels;
        portfolioChart.data.datasets[0].data = dataPoints;
        portfolioChart.update('none'); // Update instantly without animation layout lag
        return;
    }
    
    // Create primary color gradient below the line
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.45)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0.01)');
    
    portfolioChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: appLanguage === 'fr' ? 'Portefeuille Simulé' : 'Simulated Portfolio',
                data: dataPoints,
                borderColor: '#6366F1',
                borderWidth: 2.5,
                backgroundColor: gradient,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: '#6366F1',
                pointHoverBorderColor: '#FFFFFF',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#111625',
                    titleColor: '#9CA3AF',
                    bodyColor: '#FFFFFF',
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y.toFixed(1) + ' (Base 100)';
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.02)',
                        drawTicks: false
                    },
                    ticks: {
                        color: '#6B7280',
                        maxTicksLimit: 8
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.02)'
                    },
                    ticks: {
                        color: '#6B7280'
                    }
                }
            }
        }
    });
}

// Request AI Analysis from backend API
async function triggerAIAnalysis() {
    const btn = document.getElementById("btn-ai-analyze");
    const container = document.getElementById("ai-response-container");
    const accordion = document.getElementById("accordion-container");
    const reasoningText = document.getElementById("lbl-reasoning-text");
    
    showError(false); // Clear previous errors
    
    // 1. Update UI loading state
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${i18n[appLanguage].btnAnalyzing}`;
    
    // Render skeleton loading
    container.innerHTML = `
        <div class="pulse-skeleton line-1"></div>
        <div class="pulse-skeleton line-2"></div>
        <div class="pulse-skeleton line-3"></div>
    `;
    
    accordion.style.display = "none";
    reasoningText.textContent = "";
    
    try {
        // 2. Perform POST request to FastAPI
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                weights: allocations,
                lang: appLanguage
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            // Check if there is a localized error details map
            const errMsg = (data && data.detail) 
                ? (typeof data.detail === 'object' ? data.detail[appLanguage] : data.detail)
                : i18n[appLanguage].errorGeneral;
            throw new Error(errMsg);
        }
        
        // 3. Display Results
        container.innerHTML = `<p>${data.analysis}</p>`;
        
        if (data.reasoning) {
            reasoningText.textContent = data.reasoning;
            accordion.style.display = "block";
            
            // Set header label
            document.getElementById("lbl-reasoning-header").textContent = i18n[appLanguage].reasoningTitle;
        } else {
            accordion.style.display = "none";
        }
        
    } catch (err) {
        console.error("AI Analysis failed:", err);
        container.innerHTML = `<p class="ai-empty-message">${i18n[appLanguage].aiEmpty}</p>`;
        showError(true, err.message || i18n[appLanguage].errorGeneral);
    } finally {
        // 4. Restore Button State
        btn.disabled = false;
        btn.innerHTML = `<svg style="width:1.1rem;height:1.1rem" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg> ${i18n[appLanguage].btnAnalyze}`;
    }
}

// Toggle display of AI thoughts/reasoning process
function toggleReasoning() {
    const icon = document.getElementById("accordion-icon");
    const content = document.getElementById("accordion-content");
    const label = document.getElementById("lbl-reasoning-header");
    
    const isActived = content.classList.toggle("active");
    icon.classList.toggle("active", isActived);
    
    if (isActived) {
        label.textContent = i18n[appLanguage].reasoningHide;
    } else {
        label.textContent = i18n[appLanguage].reasoningTitle;
    }
}

// Display error alert banner
function showError(show, message = "") {
    const banner = document.getElementById("error-alert-banner");
    const text = document.getElementById("error-alert-text");
    
    if (show) {
        text.textContent = message;
        banner.classList.add("active");
    } else {
        banner.classList.remove("active");
        text.textContent = "";
    }
}

// Generate sharing image client-side and copy link to clipboard
function generateShareCard() {
    // 1. Copy strategy URL to clipboard
    const params = new URLSearchParams();
    for (const [ticker, val] of Object.entries(allocations)) {
        if (val > 0) {
            params.set(ticker, val.toString());
        }
    }
    const shareUrl = `${window.location.origin}${window.location.pathname}?${params.toString()}`;
    
    navigator.clipboard.writeText(shareUrl)
        .then(() => {
            showToast(i18n[appLanguage].toastCopied);
        })
        .catch(err => {
            console.error('Failed to copy link:', err);
            showToast(appLanguage === 'fr' ? 'Échec de la copie du lien' : 'Failed to copy link');
        });

    // 2. Generate 1200x630 share card
    if (!priceData || !portfolioChart) return;

    const shareCanvas = document.createElement('canvas');
    shareCanvas.width = 1200;
    shareCanvas.height = 630;
    const ctx = shareCanvas.getContext('2d');

    // Draw background
    const bgGradient = ctx.createLinearGradient(0, 0, 1200, 630);
    bgGradient.addColorStop(0, '#0B0F19');
    bgGradient.addColorStop(1, '#080A10');
    ctx.fillStyle = bgGradient;
    ctx.fillRect(0, 0, 1200, 630);

    // Draw glowing spotlight
    const spotlight = ctx.createRadialGradient(250, 200, 50, 250, 200, 600);
    spotlight.addColorStop(0, 'rgba(99, 102, 241, 0.18)');
    spotlight.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = spotlight;
    ctx.fillRect(0, 0, 1200, 630);

    // Draw brand header
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 36px Outfit, sans-serif';
    ctx.fillText(appLanguage === 'fr' ? 'SANDBOX DE THÈSES FINANCIÈRES' : 'FINANCIAL THESIS SANDBOX', 60, 80);

    ctx.fillStyle = '#9CA3AF';
    ctx.font = '20px Inter, sans-serif';
    ctx.fillText(appLanguage === 'fr' ? 'Performance historique & Analyse IA' : 'Historical Performance & AI Analysis', 60, 115);

    // Draw stats card background
    ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    roundRect(ctx, 60, 150, 340, 310, 8, true, true);

    // Stats values from elements
    const cumulVal = document.getElementById('val-stat-cumul').textContent;
    const cagrVal = document.getElementById('val-stat-cagr').textContent;
    const mddVal = document.getElementById('val-stat-mdd').textContent;

    // Draw stats texts
    ctx.fillStyle = '#9CA3AF';
    ctx.font = '12px Inter, sans-serif';
    ctx.fillText(i18n[appLanguage].statCumul.toUpperCase(), 80, 185);
    ctx.fillStyle = cumulVal.startsWith('+') ? '#10B981' : '#EF4444';
    ctx.font = 'bold 38px Outfit, sans-serif';
    ctx.fillText(cumulVal, 80, 228);

    ctx.fillStyle = '#9CA3AF';
    ctx.font = '12px Inter, sans-serif';
    ctx.fillText(i18n[appLanguage].statCagr.toUpperCase(), 80, 280);
    ctx.fillStyle = cagrVal.startsWith('+') ? '#10B981' : '#EF4444';
    ctx.font = 'bold 30px Outfit, sans-serif';
    ctx.fillText(cagrVal, 80, 318);

    ctx.fillStyle = '#9CA3AF';
    ctx.font = '12px Inter, sans-serif';
    ctx.fillText(i18n[appLanguage].statMdd.toUpperCase(), 80, 370);
    ctx.fillStyle = '#EF4444';
    ctx.font = 'bold 30px Outfit, sans-serif';
    ctx.fillText(mddVal, 80, 408);

    // Draw allocations section
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 16px Inter, sans-serif';
    ctx.fillText(appLanguage === 'fr' ? 'ALLOCATION DU PORTEFEUILLE' : 'PORTFOLIO ALLOCATION', 60, 495);

    ctx.font = '14px monospace';
    ctx.fillStyle = '#E5E7EB';
    const activeTickers = Object.entries(allocations).filter(([_, val]) => val > 0);
    activeTickers.forEach(([ticker, val], idx) => {
        const col = idx >= 5 ? 1 : 0;
        const row = idx % 5;
        const x = 60 + col * 170;
        const y = 525 + row * 20;
        ctx.fillText(`- ${ticker}: ${val}%`, x, y);
    });

    // Draw chart image on the right
    const chartImg = new Image();
    chartImg.src = portfolioChart.toBase64Image();
    chartImg.onload = () => {
        ctx.drawImage(chartImg, 430, 140, 710, 420);

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1;
        ctx.strokeRect(0, 0, 1200, 630);

        // Download PNG
        const link = document.createElement('a');
        link.download = `thesis-strategy-${appLanguage}.png`;
        link.href = shareCanvas.toDataURL('image/png');
        link.click();
    };
}

// Draw rounded rectangle helper
function roundRect(ctx, x, y, width, height, radius, fill, stroke) {
    if (typeof radius === 'number') {
        radius = {tl: radius, tr: radius, br: radius, bl: radius};
    } else {
        var defaultRadius = {tl: 0, tr: 0, br: 0, bl: 0};
        for (var side in defaultRadius) {
            radius[side] = radius[side] || defaultRadius[side];
        }
    }
    ctx.beginPath();
    ctx.moveTo(x + radius.tl, y);
    ctx.lineTo(x + width - radius.tr, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius.tr);
    ctx.lineTo(x + width, y + height - radius.br);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius.br, y + height);
    ctx.lineTo(x + radius.bl, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius.bl);
    ctx.lineTo(x, y + radius.tl);
    ctx.quadraticCurveTo(x, y, x + radius.tl, y);
    ctx.closePath();
    if (fill) {
        ctx.fill();
    }
    if (stroke) {
        ctx.stroke();
    }
}

// Show feedback Toast message
function showToast(message) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "toast-message";
    
    toast.innerHTML = `
        <svg style="width:1.25rem;height:1.25rem;color:#A5B4FC;flex-shrink:0" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 002 2h2a2 2 0 002-2"></path>
        </svg>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

async function triggerAudioOverview() {
    const btn = document.getElementById("btn-audio-generate");
    const loadingContainer = document.getElementById("audio-loading-container");
    const loadingStatus = document.getElementById("audio-loading-status");
    const playerContainer = document.getElementById("audio-player-container");
    const audioElement = document.getElementById("audio-element");
    const waveContainer = document.getElementById("waveform-container");

    showError(false); // Clear general analysis error

    // 1. Set loading UI states
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" style="display:inline-block;vertical-align:middle;margin-right:0.35rem"></span> <span>${i18n[appLanguage].btnAudioGenerating}</span>`;
    
    loadingContainer.style.display = "flex";
    loadingStatus.textContent = i18n[appLanguage].audioLoadingScript;
    
    playerContainer.style.display = "none";
    waveContainer.style.display = "none";
    audioElement.src = "";

    // Set a timer to simulate status progression
    const progressTimer = setTimeout(() => {
        loadingStatus.textContent = i18n[appLanguage].audioLoadingSpeech;
    }, 4500);

    try {
        // 2. Perform POST request to FastAPI audio overview endpoint
        const response = await fetch('/api/audio-overview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                weights: allocations,
                lang: appLanguage
            })
        });

        const data = await response.json();

        if (!response.ok) {
            const errMsg = (data && data.detail) 
                ? (typeof data.detail === 'object' ? data.detail[appLanguage] : data.detail)
                : i18n[appLanguage].audioError;
            throw new Error(errMsg);
        }

        // 3. Play generated audio
        audioElement.src = data.audio_url;
        playerContainer.style.display = "block";
        waveContainer.style.display = "flex";
        
        showToast(i18n[appLanguage].audioSuccess);
        
        // Auto-play the audio
        audioElement.play().catch(pErr => console.log("Auto-play blocked:", pErr));

    } catch (err) {
        console.error("Audio generation failed:", err);
        showToast(err.message || i18n[appLanguage].audioError);
    } finally {
        clearTimeout(progressTimer);
        // Restore Button state
        btn.disabled = false;
        btn.innerHTML = `<svg style="width:1.1rem;height:1.1rem;margin-right:0.35rem;display:inline-block;vertical-align:middle" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"></path></svg> <span>${i18n[appLanguage].btnAudioGenerate}</span>`;
        loadingContainer.style.display = "none";
    }
}
