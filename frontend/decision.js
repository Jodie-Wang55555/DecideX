// 决策助手页面逻辑

const state = {
    messages: [],
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    apiBaseUrl: 'http://localhost:8123',
    conversationId: null,
    mode: localStorage.getItem('decidex_mode') || 'simple',  // 默认简洁模式
    userProfile: null,
    authToken: localStorage.getItem('decidex_auth_token') || '',
    userEmail: localStorage.getItem('decidex_auth_email') || '',
    isSending: false  // 全局锁，防止重复发送
};

// ── 模式切换 ──────────────────────────────────────────────
function setMode(mode) {
    state.mode = mode;
    localStorage.setItem('decidex_mode', mode);
    document.getElementById('mode-simple').classList.toggle('active', mode === 'simple');
    document.getElementById('mode-detailed').classList.toggle('active', mode === 'detailed');
}

// 页面加载时恢复模式
function initMode() {
    setMode(state.mode);
}

const elements = {
    messagesContainer: document.getElementById('messages-container'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    voiceBtn: document.getElementById('voice-btn'),
    voiceModal: document.getElementById('voice-modal'),
    stopVoiceBtn: document.getElementById('stop-voice-btn'),
    charCount: document.getElementById('char-count'),
    typingIndicator: document.getElementById('typing-indicator'),
    intentStatus:  document.getElementById('intent-status'),
    ragStatus:     document.getElementById('rag-status'),
    costStatus:    document.getElementById('cost-status'),
    riskStatus:    document.getElementById('risk-status'),
    valueStatus:   document.getElementById('value-status'),
    matchStatus:   document.getElementById('match-status'),
    citationStatus:document.getElementById('citation-status'),
    profileEmail: null,
    profileRisk: null,
    profileHorizon: null,
    profileCity: null,
    profilePreference: null,
    saveProfileBtn: null,
    profileHint: null
};

// 初始化
function init() {
    initMode();
    setupEventListeners();
    validateAuthToken();
    loadMessages();
    autoResizeTextarea();
    initProfile();
    updateAnalysisStatus('waiting');
    _renderRecents();     // 渲染历史对话列表
    initPipelineState();  // 恢复流水线折叠状态（默认收起）
}

function setupEventListeners() {
    // 发送消息
    elements.sendBtn.addEventListener('click', sendMessage);
    elements.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // 字符计数
    elements.messageInput.addEventListener('input', () => {
        const count = elements.messageInput.value.length;
        elements.charCount.textContent = count;
        elements.sendBtn.disabled = count === 0;
    });

    // 语音输入
    elements.voiceBtn.addEventListener('click', toggleVoiceRecording);
    elements.stopVoiceBtn.addEventListener('click', stopVoiceRecording);
    if (elements.saveProfileBtn) {
        elements.saveProfileBtn.addEventListener('click', saveUserProfile);
    }

    // 示例问题
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.dataset.question;
            elements.messageInput.value = question;
            elements.charCount.textContent = question.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        });
    });
}

function autoResizeTextarea() {
    elements.messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
}

// ── 槽位系统（Slot Filling）────────────────────────────────────
//
// 设计：SLOTS 是所有槽位的单一定义源，TOPICS 引用槽位 key。
// 好处：槽位定义不重复，改一处生效全局。
//
// 槽位键 → profile 字段的映射：
//   risk         → profile.risk            (conservative/balanced/aggressive)
//   horizon      → profile.horizon         (short/mid/long)
//   city         → profile.city            (string)
//   preference_tags → profile.preference_tags (string[])
//   budget       → profile.budget          (string, 购房专属)
//   purpose      → profile.purpose         (string, 购房专属)
//   cur_salary   → profile.cur_salary      (string, 职业专属)
//   inv_amount   → profile.inv_amount      (string, 投资专属)
//   edu_level    → profile.edu_level       (string, 教育专属)

// ── 槽位定义表（单一数据源，所有话题共享引用）──────────────────
//
// 每个槽位字段说明：
//   label       追问时显示的问题文本
//   type        text / select / tags
//   placeholder text/tags 类型的提示文字
//   options     select 选项显示文字（第0项为空提示）
//   values      select 选项实际存储值（与 options 一一对应）
//
// 槽位 key 与 profile 字段直接对应（存入 localStorage/服务端 profile 对象）

const SLOTS = {
    // ══ 全局槽位（多话题共用）═══════════════════════════════
    risk: {
        label:   '您的风险偏好？',
        type:    'select',
        options: ['', '保守 — 优先保本稳定', '平衡 — 兼顾收益与风险', '激进 — 追求高回报'],
        values:  ['', 'conservative', 'balanced', 'aggressive']
    },
    horizon: {
        label:   '决策/规划周期？',
        type:    'select',
        options: ['', '短期（1 年内）', '中期（1–3 年）', '长期（3 年以上）'],
        values:  ['', 'short', 'mid', 'long']
    },
    city: {
        label:       '您目前所在的城市？',
        type:        'text',
        placeholder: '如 北京、上海、深圳'
    },
    preference_tags: {
        label:       '您最看重什么？（逗号分隔）',
        type:        'tags',
        placeholder: '如 稳定,成长,薪资,现金流,自由度'
    },
    age: {
        label:       '您的年龄段？',
        type:        'select',
        options:     ['', '18–25 岁', '26–30 岁', '31–35 岁', '36–45 岁', '45 岁以上'],
        values:      ['', '18-25', '26-30', '31-35', '36-45', '45+']
    },
    family_status: {
        label:   '您的家庭状况？',
        type:    'select',
        options: ['', '单身', '恋爱中', '已婚无孩', '已婚有孩', '离异'],
        values:  ['', 'single', 'dating', 'married', 'married_kids', 'divorced']
    },
    monthly_income: {
        label:       '您的月收入（税前）？',
        type:        'text',
        placeholder: '如 1.5 万、3 万、5 万'
    },
    current_assets: {
        label:       '目前可动用的存款/资产？',
        type:        'text',
        placeholder: '如 30 万、100 万、200 万'
    },

    // ══ 购房专属槽位 ════════════════════════════════════════
    budget: {
        label:       '您的购房预算？',
        type:        'text',
        placeholder: '如 总价 300 万 / 首付 80 万'
    },
    purpose: {
        label:   '购房目的？',
        type:    'select',
        options: ['', '自住', '投资出租', '自住 + 长期保值'],
        values:  ['', 'live', 'invest', 'both']
    },

    // ══ 职业专属槽位 ════════════════════════════════════════
    cur_salary: {
        label:       '您目前的月薪（税前）？',
        type:        'text',
        placeholder: '如 2 万、3.5 万'
    },
    offer_salary: {
        label:       '新 Offer 的月薪（税前）？',
        type:        'text',
        placeholder: '如 3 万、5 万、8 万'
    },
    offer_equity: {
        label:   '新 Offer 是否有股权 / 期权？',
        type:    'select',
        options: ['', '没有', '有期权（数量不明）', '有明确期权数量', '直接给股票'],
        values:  ['', 'none', 'option_vague', 'option_clear', 'stock']
    },
    company_stage: {
        label:   '初创公司目前的融资阶段？',
        type:    'select',
        options: ['', '天使 / Pre-A', 'A 轮', 'B 轮', 'C 轮及以后', '上市公司', '不清楚'],
        values:  ['', 'angel', 'series_a', 'series_b', 'series_c_plus', 'public', 'unknown']
    },
    work_years: {
        label:   '您的工作年限？',
        type:    'select',
        options: ['', '应届/1 年以内', '1–3 年', '3–5 年', '5–10 年', '10 年以上'],
        values:  ['', 'fresh', '1-3', '3-5', '5-10', '10+']
    },
    job_stability: {
        label:   '您当前工作的稳定性？',
        type:    'select',
        options: ['', '非常稳定', '一般', '有裁员风险', '已经离职'],
        values:  ['', 'stable', 'normal', 'risky', 'unemployed']
    },

    // ══ 投资专属槽位 ════════════════════════════════════════
    inv_amount: {
        label:       '本次计划投入金额？',
        type:        'text',
        placeholder: '如 10 万、50 万'
    },

    // ══ 教育专属槽位 ════════════════════════════════════════
    edu_level: {
        label:   '您目前的学历？',
        type:    'select',
        options: ['', '高中/中专', '专科', '本科', '硕士及以上'],
        values:  ['', 'high_school', 'associate', 'bachelor', 'master']
    },

    // ══ 购车专属槽位 ════════════════════════════════════════
    car_budget: {
        label:       '您的购车预算？',
        type:        'text',
        placeholder: '如 15 万、30 万、50 万'
    },
    car_purpose: {
        label:   '购车主要用途？',
        type:    'select',
        options: ['', '日常通勤', '家庭用车', '商务出行', '偶尔用/代步'],
        values:  ['', 'commute', 'family', 'business', 'casual']
    },
    car_type: {
        label:   '偏好的车辆类型？',
        type:    'select',
        options: ['', '燃油车', '纯电动', '插混/增程', '无所谓'],
        values:  ['', 'fuel', 'ev', 'phev', 'any']
    },

    // ══ 创业/副业专属槽位 ════════════════════════════════════
    startup_capital: {
        label:       '可用于创业/副业的启动资金？',
        type:        'text',
        placeholder: '如 5 万、20 万、100 万'
    },
    industry_experience: {
        label:       '您在目标行业的经验？',
        type:        'select',
        options:     ['', '完全新手', '有所了解', '有 1–3 年经验', '3 年以上深度经验'],
        values:      ['', 'none', 'basic', '1-3y', '3y+']
    },

    // ══ 换城市/移居专属槽位 ══════════════════════════════════
    current_city: {
        label:       '您目前在哪个城市？',
        type:        'text',
        placeholder: '如 北京、武汉'
    },
    target_city: {
        label:       '您考虑迁移到哪个城市？',
        type:        'text',
        placeholder: '如 上海、成都、杭州'
    }
};

// ── 话题定义表（keywords 触发识别，slots 按优先级追问）─────────
//
// slots 顺序即追问优先级；每次只追问当前缺失的槽位
// 最多追问 4 个，避免一次性问太多（体验参考 Claude）

const TOPICS = {
    housing: {
        label:    '购房决策',
        keywords: ['买房','房子','购房','楼盘','房价','首付','贷款','房贷','二手房',
                   '新房','公寓','通州','朝阳','浦东','天河','五环','六环','学区房',
                   '按揭','月供','置业'],
        slots:    ['city', 'budget', 'risk', 'horizon', 'purpose'],
        maxAsk:   4
    },
    offer: {
        label:    'Offer 决策',
        keywords: ['offer','接受offer','要不要去','初创公司','创业公司offer',
                   '要不要接','这个offer','新工作','新公司','换工作','要不要跳',
                   '期权','股权','薪资涨了','涨薪'],
        slots:    ['cur_salary', 'offer_salary', 'offer_equity', 'company_stage',
                   'work_years', 'job_stability', 'risk'],
        maxAsk:   4
    },
    career: {
        label:    '职业决策',
        keywords: ['工作','跳槽','职业','岗位','产品经理','程序员','工程师',
                   '裁员','离职','转行','找工作','晋升','pm',
                   '年终奖','绩效','升职','职场','简历'],
        slots:    ['city', 'cur_salary', 'work_years', 'job_stability', 'horizon', 'preference_tags'],
        maxAsk:   3
    },
    investment: {
        label:    '投资决策',
        keywords: ['投资','股票','基金','股权','理财','回报','收益','炒股',
                   '加密货币','比特币','etf','黄金','债券','p2p','分红',
                   '港股','美股','a股','沪深','指数基金'],
        slots:    ['risk', 'horizon', 'inv_amount', 'current_assets'],
        maxAsk:   3
    },
    education: {
        label:    '教育决策',
        keywords: ['考研','读研','留学','学历','专业','选学校','研究生','出国',
                   '大学','本科','报考','mba','博士','考证','考公','国考','省考'],
        slots:    ['city', 'edu_level', 'horizon', 'preference_tags'],
        maxAsk:   3
    },
    car: {
        label:    '购车决策',
        keywords: ['买车','购车','选车','汽车','新能源','电动车','suv','轿车',
                   '二手车','特斯拉','比亚迪','大众','丰田','本田','车贷','落地价'],
        slots:    ['city', 'car_budget', 'car_purpose', 'car_type'],
        maxAsk:   3
    },
    startup: {
        label:    '创业/副业决策',
        keywords: ['创业','副业','开店','开公司','自己做','接私活','freelance',
                   '做生意','独立开发','自媒体','带货','直播','合伙','加盟'],
        slots:    ['city', 'startup_capital', 'industry_experience', 'risk', 'horizon'],
        maxAsk:   4
    },
    relocation: {
        label:    '换城市/移居决策',
        keywords: ['换城市','移居','搬家','去北京','去上海','去深圳','去成都',
                   '离开北京','逃离北上广','落户','户口','定居','异地'],
        slots:    ['current_city', 'target_city', 'monthly_income', 'family_status', 'horizon'],
        maxAsk:   4
    },
    insurance: {
        label:    '保险决策',
        keywords: ['保险','买保险','重疾险','医疗险','人寿险','年金险','寿险',
                   '意外险','理赔','保障','投保','续保'],
        slots:    ['age', 'family_status', 'monthly_income', 'risk'],
        maxAsk:   3
    },
    consumption: {
        label:    '大额消费决策',
        keywords: ['买手机','买电脑','装修','买家电','买奢侈品','旅游','蜜月',
                   '值不值','要不要买','消费','花钱','换手机','换电脑'],
        slots:    ['budget', 'preference_tags'],
        maxAsk:   2
    },
    health: {
        label:    '医疗健康决策',
        keywords: ['手术','看病','就医','体检','治疗方案','医院','要不要做手术',
                   '用药','减肥','健身','生育','备孕','怀孕'],
        slots:    ['city', 'age', 'family_status'],
        maxAsk:   3
    }
};

// 检测话题
function _detectTopic(msg) {
    const lower = msg.toLowerCase();
    for (const [topic, cfg] of Object.entries(TOPICS)) {
        if (cfg.keywords.some(k => lower.includes(k))) return topic;
    }
    return null;
}

// ── 从消息中自动提取槽位值 ──────────────────────────────────
// 规则：正则匹配 + 关键词映射，提取到的值直接写入 profile 并持久化
// 只提取高置信度的信息，模糊的不猜
function _extractSlotsFromMessage(msg, profile) {
    const extracted = {};

    // ① 城市识别（主要城市 + 知名区县 → 映射到城市）
    const CITY_MAP = {
        '北京':'北京','上海':'上海','深圳':'深圳','广州':'广州','杭州':'杭州',
        '成都':'成都','武汉':'武汉','南京':'南京','西安':'西安','重庆':'重庆',
        '苏州':'苏州','天津':'天津','长沙':'长沙','郑州':'郑州','青岛':'青岛',
        '厦门':'厦门','宁波':'宁波','合肥':'合肥','济南':'济南','福州':'福州',
        // 区县 → 城市
        '通州':'北京','朝阳':'北京','海淀':'北京','浦东':'上海','徐汇':'上海',
        '天河':'广州','南山':'深圳','福田':'深圳','滨江':'杭州'
    };
    if (!profile.city) {
        for (const [kw, city] of Object.entries(CITY_MAP)) {
            if (msg.includes(kw)) { extracted.city = city; break; }
        }
    }

    // ② 预算/首付（购房、购车）
    if (!profile.budget) {
        // "60万首付" / "首付60万"
        const m1 = msg.match(/首付\s*(\d+[\.\d]*)\s*万/);
        const m2 = msg.match(/(\d+[\.\d]*)\s*万\s*首付/);
        // "300万的房子" / "总价300万"
        const m3 = msg.match(/总价\s*(\d+[\.\d]*)\s*万/);
        const m4 = msg.match(/(\d+[\.\d]*)\s*万的房子/);
        const m5 = msg.match(/买\s*(\d+[\.\d]*)\s*万/);
        const dp  = (m1||m2)?.[1];
        const tot = (m3||m4||m5)?.[1];
        if (dp && tot)      extracted.budget = `总价 ${tot} 万 / 首付 ${dp} 万`;
        else if (dp)        extracted.budget = `首付 ${dp} 万`;
        else if (tot)       extracted.budget = `总价 ${tot} 万`;
    }

    // ③ 当前月薪
    if (!profile.cur_salary) {
        const m = msg.match(/月薪\s*(\d+[\.\d]*)\s*万/) ||
                  msg.match(/现在.*?(\d+[\.\d]*)\s*万.*薪/) ||
                  msg.match(/目前.*?(\d+[\.\d]*)\s*万.*薪/) ||
                  msg.match(/薪资\s*(\d+[\.\d]*)\s*万/) ||
                  msg.match(/(\d+[\.\d]*)\s*万.*月薪/);
        if (m) extracted.cur_salary = `${m[1]} 万`;
    }

    // ③-b 新 Offer 薪资（涨到/给/开）
    if (!profile.offer_salary) {
        const m = msg.match(/(?:涨到|给|开|新offer.*?|offer.*?)\s*(\d+[\.\d]*)\s*万/) ||
                  msg.match(/(\d+[\.\d]*)\s*万.*(?:offer|新工作|跳过去)/) ||
                  msg.match(/薪资.*涨.*?(\d+[\.\d]*)\s*万/) ||
                  msg.match(/offer.*?(\d+[\.\d]*)\s*万/i);
        if (m && m[1] !== (extracted.cur_salary || '').replace(' 万','')) {
            extracted.offer_salary = `${m[1]} 万`;
        }
    }

    // ③-c 公司融资阶段
    if (!profile.company_stage) {
        if (/天使|pre-?a|pre_a/i.test(msg))          extracted.company_stage = 'angel';
        else if (/a轮|A轮|series.?a/i.test(msg))      extracted.company_stage = 'series_a';
        else if (/b轮|B轮|series.?b/i.test(msg))      extracted.company_stage = 'series_b';
        else if (/c轮|C轮|d轮|上市|ipo/i.test(msg))   extracted.company_stage = 'series_c_plus';
        else if (/不清楚|不知道.*融资/.test(msg))       extracted.company_stage = 'unknown';
    }

    // ③-d 期权/股权
    if (!profile.offer_equity) {
        if (/没有.*(?:期权|股权)|不给.*(?:期权|股权)/.test(msg))   extracted.offer_equity = 'none';
        else if (/有期权|给期权|给股权/.test(msg))                  extracted.offer_equity = 'option_vague';
        else if (/直接给股票|rsu|RSU/.test(msg))                    extracted.offer_equity = 'stock';
    }

    // ④ 投资金额
    if (!profile.inv_amount) {
        const m = msg.match(/(\d+[\.\d]*)\s*万.*投/) ||
                  msg.match(/投.*?(\d+[\.\d]*)\s*万/) ||
                  msg.match(/手头有\s*(\d+[\.\d]*)\s*万/);
        // 排除已被 budget 捕获的场景
        if (m && !extracted.budget) extracted.inv_amount = `${m[1]} 万`;
    }

    // ⑤ 购车预算
    if (!profile.car_budget) {
        const m = msg.match(/(\d+[\.\d]*)\s*万.*车/) ||
                  msg.match(/车.*?(\d+[\.\d]*)\s*万/);
        if (m) extracted.car_budget = `${m[1]} 万`;
    }

    // ⑥ 风险偏好词
    if (!profile.risk) {
        if (/保守|稳健|不想亏|低风险/.test(msg))       extracted.risk = 'conservative';
        else if (/激进|高风险|高回报|敢冒险/.test(msg)) extracted.risk = 'aggressive';
        else if (/平衡|中等风险/.test(msg))             extracted.risk = 'balanced';
    }

    // ⑦ 决策周期
    if (!profile.horizon) {
        if (/长期|10年|二十年|养老|退休/.test(msg))    extracted.horizon = 'long';
        else if (/短期|1年|一年内|尽快/.test(msg))      extracted.horizon = 'short';
        else if (/中期|[23]年|三年/.test(msg))          extracted.horizon = 'mid';
    }

    // ⑧ 学历
    if (!profile.edu_level) {
        if (/硕士|研究生|博士/.test(msg))               extracted.edu_level = 'master';
        else if (/本科|211|985|大学/.test(msg))         extracted.edu_level = 'bachelor';
        else if (/专科|大专/.test(msg))                  extracted.edu_level = 'associate';
    }

    // 如果有新提取的值，合并并保存
    if (Object.keys(extracted).length > 0) {
        const updated = { ...profile, ...extracted };
        state.userProfile = updated;
        localStorage.setItem('decidex_user_profile', JSON.stringify(updated));
    }
    return extracted;
}

// 找到该话题下当前画像还缺少的槽位（返回 slot 定义对象，附上 key）
// maxAsk：单次最多追问的槽位数，避免一次性问太多，体验更自然
function _getMissingSlots(topic, profile) {
    if (!topic) return [];
    const cfg = TOPICS[topic];
    const missing = cfg.slots
        .filter(key => {
            const val = profile[key];
            if (val === undefined || val === null || val === '') return true;
            if (Array.isArray(val) && val.length === 0) return true;
            return false;
        })
        .map(key => ({ key, ...SLOTS[key] }));
    // 每次最多追问 maxAsk 个，剩余的下次再问
    return missing.slice(0, cfg.maxAsk ?? 4);
}

// 渲染一个槽位的 HTML 输入控件
function _renderSlotInput(slot) {
    if (slot.type === 'select') {
        const opts = slot.options
            .map((o, j) => `<option value="${slot.values[j]}">${o}</option>`)
            .join('');
        return `<select class="clarify-input" data-key="${slot.key}" data-type="select">${opts}</select>`;
    }
    // text 或 tags 都用 input
    return `<input class="clarify-input" type="text" data-key="${slot.key}"
                data-type="${slot.type}" placeholder="${slot.placeholder || ''}">`;
}

function _showClarifyCard(originalMessage, topic, missingSlots) {
    const topicLabel = TOPICS[topic].label;
    const card = document.createElement('div');
    card.className = 'clarify-card';
    card.dataset.originalMessage = originalMessage;

    const fieldsHtml = missingSlots.map(slot => `
        <div class="clarify-field">
            <label class="clarify-label">${slot.label}</label>
            ${_renderSlotInput(slot)}
        </div>`).join('');

    card.innerHTML = `
        <div class="clarify-header">
            <span class="clarify-icon">💬</span>
            <div>
                <div class="clarify-title">在分析您的${topicLabel}前，我需要了解几点：</div>
                <div class="clarify-sub">填写后自动记忆，下次同类问题不再重复追问</div>
            </div>
        </div>
        <div class="clarify-fields">${fieldsHtml}</div>
        <div class="clarify-actions">
            <button class="clarify-skip-btn" onclick="_skipClarify(this)">跳过，直接分析</button>
            <button class="clarify-submit-btn" onclick="_submitClarify(this)">确认并开始分析 →</button>
        </div>`;

    elements.messagesContainer.appendChild(card);
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}

function _skipClarify(btn) {
    if (state.isSending) return;
    const card = btn.closest('.clarify-card');
    if (!card) return;
    const msg  = card.dataset.originalMessage;
    card.remove();
    _doSendMessage(msg);
}

function _submitClarify(btn) {
    if (state.isSending) return;
    const card   = btn.closest('.clarify-card');
    if (!card) return;
    const msg    = card.dataset.originalMessage;
    const inputs = card.querySelectorAll('.clarify-input');
    const updates = {};
    inputs.forEach(inp => {
        const key  = inp.dataset.key;
        const type = inp.dataset.type;
        const val  = inp.value.trim();
        if (!val) return;
        // tags 类型：分割成数组
        updates[key] = (type === 'tags')
            ? val.split(',').map(x => x.trim()).filter(Boolean)
            : val;
    });
    // 合并到 userProfile 并持久化
    const profile = { ...(state.userProfile || {}), ...updates };
    state.userProfile = profile;
    localStorage.setItem('decidex_user_profile', JSON.stringify(profile));
    // 如果已登录，也同步到服务端
    if (state.authToken) {
        fetch(`${state.apiBaseUrl}/profile`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.authToken}`
            },
            body: JSON.stringify({ profile })
        }).catch(() => {});
    }
    card.remove();
    _doSendMessage(msg);
}

async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message) return;
    if (state.isSending) return;  // 防止重复提交
    // 注意：不在这里设 isSending = true，由 _doSendMessage 统一管理锁

    // 清空输入框
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
    elements.charCount.textContent = '0';
    elements.sendBtn.disabled = true;

    // 移除欢迎消息
    const welcomeMsg = elements.messagesContainer.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();

    // 槽位填充：先从消息自动提取，再检查剩余缺失
    const topic = _detectTopic(message);
    const profile = state.userProfile || {};
    _extractSlotsFromMessage(message, profile);          // 自动提取并更新 profile
    const updatedProfile = state.userProfile || {};      // 取更新后的 profile
    const missing = _getMissingSlots(topic, updatedProfile);

    // 添加用户消息气泡
    addMessage('user', message);
    saveMessages();

    if (missing.length > 0) {
        state.isSending = false; // 等待用户填写 clarify card，暂时释放锁
        _showClarifyCard(message, topic, missing);
        return;
    }

    _doSendMessage(message);
}

async function _doSendMessage(message) {
    if (state.isSending) return;
    state.isSending = true;
    elements.sendBtn.disabled = true;

    // 更新分析状态
    updateAnalysisStatus('analyzing');
    
    // 显示加载状态
    showTypingIndicator();

    try {
        const response = await fetch(`${state.apiBaseUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(state.authToken ? { 'Authorization': `Bearer ${state.authToken}` } : {})
            },
            body: JSON.stringify({
                agent: 'decision',
                message: message,
                conversation_id: state.conversationId || getConversationId(),
                mode: state.mode,
                user_id: getUserId(),
                user_profile: state.userProfile || {}
            })
        });

        if (!response.ok) {
            throw new Error('网络请求失败');
        }

        const data = await response.json();
        
        // 隐藏加载状态
        hideTypingIndicator();
        
        // 更新分析状态
        updateAnalysisStatus('completed');
        
        // 添加助手回复
        const aiText = data.response || data.message || '抱歉，我无法处理您的请求。';
        addMessage('assistant', aiText);
        syncPipelineFromResult(aiText);
        
        // 保存会话ID
        if (data.conversation_id) {
            state.conversationId = data.conversation_id;
        }
        
    } catch (error) {
        console.error('发送消息失败:', error);
        hideTypingIndicator();
        updateAnalysisStatus('error');
        addMessage('assistant', '抱歉，发生了错误。请检查网络连接或确保后端服务正在运行。');
    } finally {
        state.isSending = false;
        elements.sendBtn.disabled = elements.messageInput.value.trim().length === 0;
    }
    
    saveMessages();
}

function addMessage(role, content) {
    // 移除欢迎消息（如果还在）
    const welcomeMsg = elements.messagesContainer.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    if (role === 'assistant') {
        messageContent.innerHTML = renderMarkdown(content);
    } else {
        const p = document.createElement('p');
        p.textContent = content;
        messageContent.appendChild(p);
    }
    
    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = new Date().toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(messageContent);
    messageContent.appendChild(messageTime);
    
    elements.messagesContainer.appendChild(messageDiv);
    
    // 滚动到底部
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
    
    // 保存到状态
    state.messages.push({ role, content, timestamp: Date.now() });
}

function showTypingIndicator() {
    elements.typingIndicator.classList.add('active');
}

function hideTypingIndicator() {
    elements.typingIndicator.classList.remove('active');
}

// 所有状态卡按顺序排列（流水线顺序）
const PIPELINE_STEPS = [
    { key: 'intentStatus',  label: '意图识别' },
    { key: 'ragStatus',     label: 'RAG 检索' },
    { key: 'costStatus',    label: '成本分析' },
    { key: 'riskStatus',    label: '风险评估' },
    { key: 'valueStatus',   label: '价值评估' },
    { key: 'matchStatus',   label: '个人匹配度' },
    { key: 'citationStatus',label: 'Citation 生成' },
];

let _pipelineTimer = null;

function _setStepStatus(el, status) {
    if (!el) return;
    const texts = { waiting: '等待中', analyzing: '分析中...', completed: '已完成', error: '错误', pending_profile: '待完善画像' };
    el.textContent = texts[status] || '等待中';
    let klass = 'analysis-status';
    if (status === 'analyzing') klass += ' active';
    if (status === 'completed') klass += ' done';
    if (status === 'pending_profile') klass += ' pending-profile';
    el.className = klass;
}

function updateAnalysisStatus(status) {
    if (_pipelineTimer) { clearTimeout(_pipelineTimer); _pipelineTimer = null; }

    if (status === 'waiting') {
        // 全部重置为等待中
        PIPELINE_STEPS.forEach(s => _setStepStatus(elements[s.key], 'waiting'));
        if (!state.userProfile || !state.userProfile.email) {
            _setStepStatus(elements.matchStatus, 'pending_profile');
        }
        return;
    }

    if (status === 'error') {
        PIPELINE_STEPS.forEach(s => {
            const el = elements[s.key];
            if (el && el.textContent === '分析中...') _setStepStatus(el, 'error');
        });
        return;
    }

    if (status === 'analyzing') {
        // 逐步动画：每隔 600ms 推进一个步骤
        let i = 0;
        function nextStep() {
            if (i >= PIPELINE_STEPS.length) return;
            // 把上一步改为 completed
            if (i > 0) _setStepStatus(elements[PIPELINE_STEPS[i - 1].key], 'completed');
            // 当前步改为 analyzing
            _setStepStatus(elements[PIPELINE_STEPS[i].key], 'analyzing');
            i++;
            _pipelineTimer = setTimeout(nextStep, 600);
        }
        nextStep();
        return;
    }

    if (status === 'completed') {
        // 全部标为完成
        PIPELINE_STEPS.forEach(s => _setStepStatus(elements[s.key], 'completed'));
    }
}

function syncPipelineFromResult(text) {
    const content = text || '';
    if (/意图识别|intent/i.test(content)) _setStepStatus(elements.intentStatus, 'completed');
    if (/RAG|检索|知识库|召回/i.test(content)) _setStepStatus(elements.ragStatus, 'completed');
    if (/成本分析|成本总览|成本/i.test(content)) _setStepStatus(elements.costStatus, 'completed');
    if (/风险评估|风险/i.test(content)) _setStepStatus(elements.riskStatus, 'completed');
    if (/价值评估|价值/i.test(content)) _setStepStatus(elements.valueStatus, 'completed');

    if (/个人匹配|匹配度|偏好|历史记忆|画像/i.test(content)) {
        _setStepStatus(elements.matchStatus, 'completed');
    } else if (!state.userProfile || !state.userProfile.email) {
        _setStepStatus(elements.matchStatus, 'pending_profile');
    } else {
        _setStepStatus(elements.matchStatus, 'waiting');
    }

    if (/Citation|决策依据|参考|来源|\[\d+\]/i.test(content)) {
        _setStepStatus(elements.citationStatus, 'completed');
    } else {
        _setStepStatus(elements.citationStatus, 'waiting');
    }
}

function initProfile() {
    const raw = localStorage.getItem('decidex_user_profile');
    if (!raw) return;
    try {
        state.userProfile = JSON.parse(raw);
        if (elements.profileEmail) elements.profileEmail.value = state.userProfile.email || '';
        if (elements.profileRisk) elements.profileRisk.value = state.userProfile.risk || '';
        if (elements.profileHorizon) elements.profileHorizon.value = state.userProfile.horizon || '';
        if (elements.profileCity) elements.profileCity.value = state.userProfile.city || '';
        if (elements.profilePreference) elements.profilePreference.value = (state.userProfile.preference_tags || []).join(',');
        if (elements.profileHint) elements.profileHint.textContent = '已加载画像：后续会自动用于个人匹配度分析。';
    } catch (_) {}
    // 画像已在 localStorage，不再自动拉取服务端，避免每次进页面都多一次请求
}

function saveUserProfile() {
    const profile = {
        email: (elements.profileEmail?.value || '').trim(),
        risk: elements.profileRisk?.value || '',
        horizon: elements.profileHorizon?.value || '',
        city: (elements.profileCity?.value || '').trim(),
        preference_tags: (elements.profilePreference?.value || '')
            .split(',')
            .map(x => x.trim())
            .filter(Boolean)
    };
    state.userProfile = profile;
    localStorage.setItem('decidex_user_profile', JSON.stringify(profile));
    if (state.authToken) {
        saveProfileToServer(profile);
    }
    if (elements.profileHint) {
        elements.profileHint.textContent = profile.email
            ? `已保存：${profile.email}（会用于后续记忆）`
            : '已保存本地画像（建议补邮箱用于跨设备记忆）。';
    }
    updateAnalysisStatus('waiting');
}

function getUserId() {
    const email = state.userEmail || state.userProfile?.email || '';
    if (email) return email.toLowerCase();
    return getConversationId();
}

async function loadProfileFromServer() {
    if (!state.authToken) return;
    try {
        const res = await fetch(`${state.apiBaseUrl}/profile`, {
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        const profile = data.profile || {};
        if (!profile.email) profile.email = state.userEmail;
        state.userProfile = profile;
        localStorage.setItem('decidex_user_profile', JSON.stringify(profile));
        if (elements.profileEmail) elements.profileEmail.value = profile.email || '';
        if (elements.profileRisk) elements.profileRisk.value = profile.risk || '';
        if (elements.profileHorizon) elements.profileHorizon.value = profile.horizon || '';
        if (elements.profileCity) elements.profileCity.value = profile.city || '';
        if (elements.profilePreference) elements.profilePreference.value = (profile.preference_tags || []).join(',');
        if (elements.profileHint) elements.profileHint.textContent = '已从账号加载画像。';
    } catch (_) {}
}

async function saveProfileToServer(profile) {
    if (!state.authToken) return;
    try {
        await fetch(`${state.apiBaseUrl}/profile`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.authToken}`
            },
            body: JSON.stringify({ profile })
        });
    } catch (_) {}
}

function validateAuthToken() {
    // 只读 localStorage，不发网络请求
    // token 失效时由 /chat 返回 401 再清除，避免每次进页面都多一次请求
    state.authToken = localStorage.getItem('decidex_auth_token') || '';
    state.userEmail = localStorage.getItem('decidex_auth_email') || '';
}

function toggleVoiceRecording() {
    if (state.isRecording) {
        stopVoiceRecording();
    } else {
        startVoiceRecording();
    }
}

async function startVoiceRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.mediaRecorder = new MediaRecorder(stream);
        state.audioChunks = [];
        
        state.mediaRecorder.ondataavailable = (event) => {
            state.audioChunks.push(event.data);
        };
        
        state.mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(state.audioChunks, { type: 'audio/wav' });
            await processAudioInput(audioBlob);
            stream.getTracks().forEach(track => track.stop());
        };
        
        state.mediaRecorder.start();
        state.isRecording = true;
        
        elements.voiceBtn.classList.add('recording');
        elements.voiceModal.classList.add('active');
        
    } catch (error) {
        console.error('无法访问麦克风:', error);
        alert('无法访问麦克风。请检查浏览器权限设置。');
    }
}

function stopVoiceRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.isRecording = false;
        
        elements.voiceBtn.classList.remove('recording');
        elements.voiceModal.classList.remove('active');
    }
}

async function processAudioInput(audioBlob) {
    showTypingIndicator();
    
    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.wav');
        formData.append('agent', 'decision');
        
        const response = await fetch(`${state.apiBaseUrl}/transcribe`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('语音识别失败');
        }
        
        const data = await response.json();
        const transcribedText = data.text || data.transcription;
        
        if (transcribedText) {
            elements.messageInput.value = transcribedText;
            elements.charCount.textContent = transcribedText.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        } else {
            hideTypingIndicator();
            addMessage('assistant', '抱歉，无法识别您的语音。请重试。');
        }
        
    } catch (error) {
        console.error('处理音频失败:', error);
        hideTypingIndicator();
        tryBrowserSpeechRecognition();
    }
}

function tryBrowserSpeechRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        
        recognition.lang = 'zh-CN';
        recognition.continuous = false;
        recognition.interimResults = false;
        
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            elements.messageInput.value = transcript;
            elements.charCount.textContent = transcript.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        };
        
        recognition.onerror = (event) => {
            console.error('语音识别错误:', event.error);
            hideTypingIndicator();
            addMessage('assistant', '语音识别失败，请重试或直接输入文字。');
        };
        
        recognition.start();
    } else {
        hideTypingIndicator();
        addMessage('assistant', '您的浏览器不支持语音识别功能。');
    }
}

function getConversationId() {
    if (!state.conversationId) {
        state.conversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('conversationId', state.conversationId);
    }
    return state.conversationId;
}

// ── 重置用户画像 ──────────────────────────────────────────
// ── 分析流水线折叠 ────────────────────────────────────────
function togglePipeline() {
    const body  = document.getElementById('pipeline-body');
    const arrow = document.getElementById('pipeline-arrow');
    if (!body) return;
    const collapsed = body.classList.toggle('collapsed');
    arrow.classList.toggle('collapsed', collapsed);
    localStorage.setItem('pipeline_collapsed', collapsed ? '1' : '0');
}

// 初始化时恢复折叠状态（默认收起）
function initPipelineState() {
    const saved = localStorage.getItem('pipeline_collapsed');
    const shouldCollapse = saved === null ? true : saved === '1'; // 默认收起
    if (shouldCollapse) {
        const body  = document.getElementById('pipeline-body');
        const arrow = document.getElementById('pipeline-arrow');
        if (body)  body.classList.add('collapsed');
        if (arrow) arrow.classList.add('collapsed');
    }
}

function resetUserProfile() {
    if (!confirm('确定要重置用户画像吗？下次提问时系统会重新收集你的偏好信息。')) return;
    // 清前端缓存
    localStorage.removeItem('decidex_user_profile');
    state.userProfile = null;
    // 清后端SQLite（fire-and-forget）
    if (state.authToken) {
        fetch(`${state.apiBaseUrl}/profile/reset`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        }).catch(() => {});
    }
    alert('✅ 用户画像已重置，下次提问时系统会重新了解你的偏好。');
}

// ── 历史对话管理 ──────────────────────────────────────────
// 数据结构：[{ id, title, messages, createdAt }]
const CONV_HISTORY_KEY = 'decidex_conv_history';
const MAX_HISTORY = 20;  // 最多保留20条历史

function _loadConvHistory() {
    try {
        const raw = JSON.parse(localStorage.getItem(CONV_HISTORY_KEY) || '[]');
        // 按标题去重：相同标题只保留消息最多的那条（清理历史遗留重复数据）
        const seen = new Map(); // title → entry
        for (const c of raw) {
            const prev = seen.get(c.title);
            if (!prev || (c.messages || []).length >= (prev.messages || []).length) {
                seen.set(c.title, c);
            }
        }
        const deduped = [...seen.values()];
        // 如果去重后条数减少了，回写一次修复 localStorage
        if (deduped.length < raw.length) {
            localStorage.setItem(CONV_HISTORY_KEY, JSON.stringify(deduped));
        }
        return deduped;
    }
    catch { return []; }
}

function _saveConvHistory(list) {
    localStorage.setItem(CONV_HISTORY_KEY, JSON.stringify(list));
}

/** 把当前对话存入历史列表（有内容才保存） */
function _archiveCurrentConv() {
    if (!state.messages || state.messages.length === 0) return;
    const firstUserMsg = state.messages.find(m => m.role === 'user');
    if (!firstUserMsg) return;

    const title = firstUserMsg.content.slice(0, 30) + (firstUserMsg.content.length > 30 ? '…' : '');
    // 用 getConversationId() 确保每次都用同一个稳定 ID，不再每次 Date.now() 生成新 ID
    const id = getConversationId();
    const history = _loadConvHistory();

    // 如果已存在同 id，更新；否则插入头部
    const idx = history.findIndex(c => c.id === id);
    const entry = { id, title, messages: [...state.messages], createdAt: Date.now() };
    if (idx >= 0) history[idx] = entry;
    else history.unshift(entry);

    // 超出上限时截断尾部
    _saveConvHistory(history.slice(0, MAX_HISTORY));
    _renderRecents();
}

/** 渲染历史对话列表到侧边栏 */
function _renderRecents() {
    const list = document.getElementById('recents-list');
    const empty = document.getElementById('recents-empty');
    if (!list) return;

    const history = _loadConvHistory();
    list.innerHTML = '';

    if (history.length === 0) {
        if (empty) empty.style.display = 'block';
        return;
    }
    if (empty) empty.style.display = 'none';

    history.forEach(conv => {
        const item = document.createElement('div');
        item.className = 'recent-item' + (conv.id === state.conversationId ? ' active' : '');
        item.innerHTML = `
            <span class="recent-title" title="${conv.title}">${conv.title}</span>
            <button class="recent-delete" title="删除" onclick="event.stopPropagation(); _deleteConv('${conv.id}')">✕</button>`;
        item.addEventListener('click', () => _loadConv(conv.id));
        list.appendChild(item);
    });
}

/** 加载某条历史对话 */
function _loadConv(id) {
    // 先保存当前对话
    _archiveCurrentConv();

    const history = _loadConvHistory();
    const conv = history.find(c => c.id === id);
    if (!conv) return;

    // 切换状态
    state.conversationId = conv.id;
    state.messages = [...conv.messages];
    state.isSending = false;
    localStorage.setItem('conversationId', conv.id);
    localStorage.setItem('decision_messages', JSON.stringify(conv.messages));

    // 重渲染聊天区
    elements.messagesContainer.innerHTML = '';
    conv.messages.forEach(msg => addMessage(msg.role, msg.content));
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;

    updateAnalysisStatus('waiting');
    _renderRecents(); // 更新 active 状态
}

/** 搜索/筛选历史对话 */
function focusSearchChat() {
    const wrap = document.getElementById('chat-search-wrap');
    if (!wrap) return;
    const isVisible = wrap.style.display !== 'none';
    wrap.style.display = isVisible ? 'none' : 'block';
    if (!isVisible) {
        const input = document.getElementById('chat-search-input');
        if (input) { input.value = ''; input.focus(); filterRecents(''); }
    }
}

function filterRecents(keyword) {
    const kw = (keyword || '').trim().toLowerCase();
    const items = document.querySelectorAll('#recents-list .recent-item');
    items.forEach(el => {
        const title = el.querySelector('.recent-title')?.textContent.toLowerCase() || '';
        el.style.display = (!kw || title.includes(kw)) ? '' : 'none';
    });
}

/** 删除某条历史对话 */
function _deleteConv(id) {
    const history = _loadConvHistory().filter(c => c.id !== id);
    _saveConvHistory(history);
    // 如果删的是当前对话，新建一条
    if (id === state.conversationId) _resetChatUI();
    _renderRecents();
}

/** 重置聊天区到欢迎状态（不存档） */
function _resetChatUI() {
    state.messages = [];
    state.conversationId = null;
    state.isSending = false;
    localStorage.removeItem('decision_messages');
    localStorage.removeItem('conversationId');

    elements.messagesContainer.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">🤖</div>
            <h3>欢迎使用 DecideX</h3>
            <p>输入您的决策问题，系统将自动完成：意图识别 → RAG 检索 → Multi-Agent 分析 → Citation 报告</p>
            <div class="example-questions">
                <button class="example-btn" data-question="我在互联网公司做产品经理，有创业公司offer薪资涨30%，我该去吗？">💼 是否接受创业公司 Offer？</button>
                <button class="example-btn" data-question="手里有50万，朋友推荐我买某个创业公司的股权，说有10倍回报，要投吗？">📈 是否投资创业公司股权？</button>
                <button class="example-btn" data-question="北京月薪3万，要不要在通州买300万的房子？手头有60万首付">🏡 是否在通州买房？</button>
                <button class="example-btn" data-question="非211本科，想考研还是直接找工作？目标是互联网产品岗">🎓 考研 vs 直接工作？</button>
            </div>
        </div>`;

    elements.messagesContainer.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.dataset.question;
            elements.messageInput.value = question;
            elements.charCount.textContent = question.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        });
    });

    updateAnalysisStatus('waiting');
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
    elements.charCount.textContent = '0';
    elements.sendBtn.disabled = true;
    if (elements.typingIndicator) elements.typingIndicator.style.display = 'none';
}

// ── 新对话 ────────────────────────────────────────────────
function newConversation() {
    _archiveCurrentConv();   // 先存档当前对话
    _resetChatUI();          // 重置 UI
    _renderRecents();        // 刷新列表

    const btn = document.getElementById('new-chat-btn');
    if (btn) {
        btn.classList.add('clicked');
        setTimeout(() => btn.classList.remove('clicked'), 300);
    }
}

function saveMessages() {
    localStorage.setItem('decision_messages', JSON.stringify(state.messages));
    _archiveCurrentConv();   // 每次发消息同步存档
}

function loadMessages() {
    const savedMessages = localStorage.getItem('decision_messages');
    if (savedMessages) {
        try {
            const allMsgs = JSON.parse(savedMessages);
            // 只加载最近 10 条，避免大量历史消息导致页面卡死
            const recent = allMsgs.slice(-10);
            state.messages = recent;
            recent.forEach(msg => {
                addMessage(msg.role, msg.content);
            });
        } catch (error) {
            console.error('加载消息失败:', error);
            // 解析失败则清空，避免反复卡死
            localStorage.removeItem('decision_messages');
        }
    }
    
    const savedConvId = localStorage.getItem('conversationId');
    if (savedConvId) {
        state.conversationId = savedConvId;
    }
}

// ── Markdown 渲染 ────────────────────────────────────────
function renderMarkdown(text) {
    // 超长保护：超过 8000 字符截断，避免渲染卡死
    if (text && text.length > 8000) text = text.slice(0, 8000) + '\n\n…（内容过长，已截断）';
    // 转义 HTML 特殊字符（安全）
    const escape = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

    let html = '';
    const lines = text.split('\n');
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];

        // 空行 → 关闭列表或加段落间距
        if (line.trim() === '') {
            if (inList) { html += '</ul>'; inList = false; }
            html += '<div style="height:0.4rem"></div>';
            continue;
        }

        // ### 标题
        if (line.startsWith('### ')) {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<h4 class="md-h4">${escape(line.slice(4))}</h4>`;
            continue;
        }
        // ## 标题
        if (line.startsWith('## ')) {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<h3 class="md-h3">${escape(line.slice(3))}</h3>`;
            continue;
        }

        // 分割线 ---
        if (/^-{3,}$/.test(line.trim())) {
            if (inList) { html += '</ul>'; inList = false; }
            html += '<hr class="md-hr">';
            continue;
        }

        // 列表项 - 或 数字.
        const listMatch = line.match(/^(\s*[-*]|\s*\d+\.) (.+)/);
        if (listMatch) {
            if (!inList) { html += '<ul class="md-list">'; inList = true; }
            html += `<li>${inlineMarkdown(escape(listMatch[2]))}</li>`;
            continue;
        }

        // 普通段落
        if (inList) { html += '</ul>'; inList = false; }
        html += `<p class="md-p">${inlineMarkdown(escape(line))}</p>`;
    }
    if (inList) html += '</ul>';
    return html;
}

function inlineMarkdown(text) {
    // **加粗**
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // *斜体*
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // `代码`
    text = text.replace(/`(.+?)`/g, '<code class="md-code">$1</code>');
    // [n] 引用标注
    text = text.replace(/\[(\d+)\]/g, '<sup class="md-cite">[$1]</sup>');
    // > 引用块（行内）
    text = text.replace(/^&gt; (.+)/, '<span class="md-quote">$1</span>');
    return text;
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 处理页面可见性变化
document.addEventListener('visibilitychange', () => {
    if (document.hidden && state.isRecording) {
        stopVoiceRecording();
    }
});
